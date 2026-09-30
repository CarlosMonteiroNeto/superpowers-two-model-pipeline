"""Private, integrity-checked cache for normalized dependency evidence."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shutil
import tempfile
import uuid
from typing import Any, Callable


SCHEMA_VERSION = 1
_HASH = re.compile(r"^[0-9a-f]{64}$")
_CACHE_PREFIX = "superpowers-impact-cache-"
_OWNER_MARKER = ".superpowers-impact-cache-owner.json"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _repo_path(value: Any) -> str:
    if (not isinstance(value, str) or not value or "\\" in value or value.startswith("/")
            or re.match(r"^[A-Za-z]:", value) or "\x00" in value
            or any(part in ("", ".", "..") or part.startswith("-") for part in value.split("/"))):
        raise ValueError("dependency cache contains an unsafe repository path")
    return value


def make_key(inputs: dict) -> str:
    """Hash the complete extraction inputs, independent of their ordering."""
    if not isinstance(inputs, dict):
        raise ValueError("dependency cache key inputs must be an object")
    required = ("repository_namespace", "snapshot_inventory", "resolution_inputs",
                "extractor_identity", "adapter_identity", "policy_identity")
    if any(field not in inputs for field in required):
        raise ValueError("dependency cache key is missing required identity inputs")
    namespace = inputs["repository_namespace"]
    if not isinstance(namespace, str) or not namespace.strip():
        raise ValueError("dependency cache repository namespace is required")
    inventory = inputs["snapshot_inventory"]
    if not isinstance(inventory, list):
        raise ValueError("dependency cache snapshot inventory must be an array")
    normalized = []
    seen = set()
    for item in inventory:
        if not isinstance(item, dict):
            raise ValueError("dependency cache inventory entries must be objects")
        path = _repo_path(item.get("path"))
        digest = item.get("sha256")
        if not isinstance(digest, str) or not _HASH.fullmatch(digest):
            raise ValueError("dependency cache inventory requires SHA-256 content digests")
        if path in seen:
            raise ValueError("dependency cache inventory contains duplicate paths")
        seen.add(path)
        mode = item.get("mode")
        if isinstance(mode, bool) or not isinstance(mode, (int, str)):
            raise ValueError("dependency cache inventory requires file mode/type identity")
        normalized.append({"path": path, "sha256": digest, "mode": mode,
                           "link_target": item.get("link_target")})
    normalized.sort(key=lambda item: item["path"])
    if not isinstance(inputs["resolution_inputs"], (dict, list)):
        raise ValueError("dependency cache resolution inputs must be an object or array")
    if not isinstance(inputs["extractor_identity"], dict) or not inputs["extractor_identity"]:
        raise ValueError("dependency cache extractor identity must be a nonempty object")
    adapter = inputs["adapter_identity"]
    if not isinstance(adapter, str) or not adapter:
        raise ValueError("dependency cache adapter identity is required")
    policy_identity = inputs["policy_identity"]
    if not isinstance(policy_identity, (dict, str)) or not policy_identity:
        raise ValueError("dependency cache policy identity is required")
    identity = {
        "repository_namespace": namespace,
        "snapshot_inventory": normalized,
        "resolution_inputs": inputs["resolution_inputs"],
        "extractor_identity": inputs["extractor_identity"],
        "adapter_identity": adapter,
        "policy_identity": policy_identity,
    }
    try:
        return _digest(identity)
    except (TypeError, ValueError) as exc:
        raise ValueError("dependency cache key inputs are not canonical JSON") from exc


def _normalize_edges(value: Any, label: str) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        raise ValueError("dependency evidence %s must be an object" % label)
    result = {}
    for source, targets in value.items():
        source = _repo_path(source)
        if not isinstance(targets, list):
            raise ValueError("dependency evidence %s values must be arrays" % label)
        normalized = sorted({_repo_path(target) for target in targets})
        result[source] = normalized
    return {path: result[path] for path in sorted(result)}


def _normalize_evidence(value: Any, *, require_complete: bool) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("complete"), bool):
        raise ValueError("dependency evidence is malformed")
    if not value["complete"]:
        if require_complete:
            raise ValueError("dependency evidence is incomplete")
        diagnostics = value.get("diagnostics", [])
        if not isinstance(diagnostics, list) or not all(isinstance(item, str) for item in diagnostics):
            raise ValueError("incomplete dependency evidence diagnostics are malformed")
        return dict(value)
    version = value.get("graphify_version")
    graph_digest = value.get("graph_digest")
    inventory_digest = value.get("source_inventory_hash")
    diagnostics = value.get("diagnostics", [])
    if (not isinstance(version, str) or not version
            or not isinstance(graph_digest, str) or not _HASH.fullmatch(graph_digest)
            or not isinstance(inventory_digest, str) or not _HASH.fullmatch(inventory_digest)
            or not isinstance(diagnostics, list) or diagnostics
            or not all(isinstance(item, str) for item in diagnostics)):
        raise ValueError("complete dependency evidence is missing validated provenance")
    return {
        "complete": True,
        "forward_edges": _normalize_edges(value.get("forward_edges"), "forward_edges"),
        "reverse_edges": _normalize_edges(value.get("reverse_edges"), "reverse_edges"),
        "graphify_version": version,
        "graph_digest": graph_digest,
        "source_inventory_hash": inventory_digest,
        "diagnostics": [],
    }


def _entry_path(root: pathlib.Path, key: str) -> pathlib.Path:
    if not isinstance(key, str) or not _HASH.fullmatch(key):
        raise ValueError("dependency cache key must be a lowercase SHA-256 digest")
    return root / (key + ".json")


def _read_entry(path: pathlib.Path, key: str) -> dict[str, Any] | None:
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(entry, dict) or entry.get("schema_version") != SCHEMA_VERSION
                or entry.get("key") != key or set(entry) != {
                    "schema_version", "key", "evidence", "payload_digest"}):
            return None
        evidence = _normalize_evidence(entry["evidence"], require_complete=True)
        payload = {"schema_version": SCHEMA_VERSION, "key": key, "evidence": evidence}
        if entry.get("payload_digest") != _digest(payload):
            return None
        return evidence
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _publish(root: pathlib.Path, key: str, evidence: dict[str, Any]) -> None:
    payload = {"schema_version": SCHEMA_VERSION, "key": key, "evidence": evidence}
    entry = {**payload, "payload_digest": _digest(payload)}
    descriptor, temporary_name = tempfile.mkstemp(prefix="." + key + ".", suffix=".tmp", dir=root)
    temporary = pathlib.Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(entry, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, root / (key + ".json"))
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def get_or_build(cache_root: pathlib.Path, key: str, builder: Callable[[], dict],
                 diagnostics: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return complete cached evidence or build it; write failures are nonfatal."""
    root = pathlib.Path(cache_root)
    entry = _entry_path(root, key)
    details = diagnostics if diagnostics is not None else {}
    cached = _read_entry(entry, key)
    if cached is not None:
        details.update(cache_hit=True, cache_miss=False, cache_write_failed=False)
        return cached
    details.update(cache_hit=False, cache_miss=True, cache_write_failed=False)
    fresh = builder()
    if not isinstance(fresh, dict):
        raise ValueError("dependency graph builder returned a non-object result")
    if fresh.get("complete") is not True:
        return _normalize_evidence(fresh, require_complete=False)
    normalized = _normalize_evidence(fresh, require_complete=True)
    try:
        root.mkdir(parents=True, exist_ok=True)
        _publish(root, key, normalized)
    except OSError:
        details["cache_write_failed"] = True
    return normalized


def is_owned_root(path: pathlib.Path) -> bool:
    root = pathlib.Path(path)
    temp_root = pathlib.Path(tempfile.gettempdir()).resolve()
    try:
        if (root.is_symlink() or root.name.startswith(_CACHE_PREFIX) is False
                or root.parent.resolve() != temp_root or root.resolve().parent != temp_root):
            return False
        marker = json.loads((root / _OWNER_MARKER).read_text(encoding="utf-8"))
        return (isinstance(marker, dict) and marker.get("schema_version") == 1
                and marker.get("created_by") == "test_dependency_cache"
                and isinstance(marker.get("token"), str) and len(marker["token"]) == 32)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return False


def create_owned_root() -> pathlib.Path:
    """Create a marked external temporary root owned by this run."""
    root = pathlib.Path(tempfile.mkdtemp(prefix=_CACHE_PREFIX, dir=tempfile.gettempdir()))
    marker = {"schema_version": 1, "created_by": "test_dependency_cache", "token": uuid.uuid4().hex}
    (root / _OWNER_MARKER).write_text(json.dumps(marker, sort_keys=True), encoding="utf-8")
    return root


def cleanup_owned_root(path: pathlib.Path) -> bool:
    """Remove only a marked run root created under the system temp directory."""
    root = pathlib.Path(path)
    if not is_owned_root(root):
        return False
    shutil.rmtree(root)
    return True
