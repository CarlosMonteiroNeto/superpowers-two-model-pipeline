"""Candidate-bound impact manifests and gate evidence matching."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
from typing import Any


_HASH = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Reject malformed or tampered test-impact selector output."""
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("impact manifest has an unsupported schema")
    required = {"schema_version", "mode", "scope_paths", "tests", "commands",
                "reasons", "reasons_detail", "gaps", "identity", "evidence",
                "selection_hash"}
    if set(manifest) != required:
        raise ValueError("impact manifest fields do not match the selector contract")
    identity = manifest.get("identity")
    evidence = manifest.get("evidence")
    if not isinstance(identity, dict) or not isinstance(evidence, dict):
        raise ValueError("impact manifest identity and evidence are required")
    for field in ("base_commit", "head_commit"):
        if not isinstance(identity.get(field), str) or not _COMMIT.fullmatch(identity[field]):
            raise ValueError("impact manifest has an invalid %s" % field)
    for field in ("base_tree_hash", "tree_hash", "config_hash", "environment_hash"):
        if not isinstance(identity.get(field), str) or not _HASH.fullmatch(identity[field]):
            # test_impact also accepts explicit tree identity wrappers.
            value = identity.get(field)
            valid_wrapped = isinstance(value, str) and (
                (value.startswith("tree:sha256:") and _HASH.fullmatch(value[len("tree:sha256:"):]))
                or (re.fullmatch(r"commit:[0-9a-f]{7,64}\+sha256:[0-9a-f]{64}", value) is not None)
            )
            if field not in ("base_tree_hash", "tree_hash") or not valid_wrapped:
                raise ValueError("impact manifest has an invalid %s" % field)
    if not isinstance(identity.get("policy_version"), str) or not identity["policy_version"]:
        raise ValueError("impact manifest policy version is missing")
    for field in ("diff_hash", "graph_hash", "toolchains_hash", "policy_hash"):
        if not isinstance(evidence.get(field), str) or not _HASH.fullmatch(evidence[field]):
            raise ValueError("impact manifest has invalid %s" % field)
    for field in ("scope_paths", "tests", "commands", "reasons", "reasons_detail", "gaps"):
        if not isinstance(manifest.get(field), list):
            raise ValueError("impact manifest %s must be an array" % field)
    selection = {key: value for key, value in manifest.items() if key != "selection_hash"}
    if not isinstance(manifest.get("selection_hash"), str) or not _HASH.fullmatch(manifest["selection_hash"]):
        raise ValueError("impact manifest selection hash is malformed")
    if _digest(selection) != manifest["selection_hash"]:
        raise ValueError("impact manifest selection hash does not match its contents")
    return manifest


def matches(record: dict[str, Any], candidate: dict[str, Any]) -> bool:
    """Return whether gate evidence proves this exact tree/config/impact set."""
    if not isinstance(record, dict) or not isinstance(candidate, dict):
        return False
    manifest = candidate.get("impact_manifest")
    try:
        validate_manifest(manifest)
    except (TypeError, ValueError):
        return False
    identity = manifest["identity"]
    expected = {
        "candidate_commit": candidate.get("commit"),
        "tree_hash": candidate.get("tree_hash"),
        "config_hash": candidate.get("config_hash"),
        "environment_hash": candidate.get("environment_hash"),
        "impact_selection_hash": manifest["selection_hash"],
    }
    if (identity["head_commit"] != expected["candidate_commit"]
            or identity["tree_hash"] != expected["tree_hash"]
            or identity["config_hash"] != expected["config_hash"]
            or identity["environment_hash"] != expected["environment_hash"]):
        return False
    return all(record.get(key) == value for key, value in expected.items())


def _git(root: pathlib.Path, *args: str, binary: bool = False):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if result.returncode:
        raise ValueError("cannot derive impact from repository state: " + result.stderr.decode("utf-8", "replace").strip())
    return result.stdout if binary else result.stdout.decode("utf-8", "replace").strip()


def create_workspace_manifest(workspace: str, selection: list[str], mode: str) -> dict[str, Any]:
    """Create a conservative manifest from current Git state and ledger commands.

    Dependency graphs are not accepted from gate callers. Until a trusted graph
    source is configured, test_impact's missing-graph fallback selects complete
    suites. A coder cannot supply a test path list to this function.
    """
    scripts = pathlib.Path(__file__).resolve().parent
    sys.path.insert(0, str(scripts))
    import test_impact
    import toolchain_gate

    try:
        root_value = _git(pathlib.Path(workspace).resolve(), "rev-parse", "--show-toplevel")
    except ValueError:
        # Pipeline workspaces can be explicitly placed outside the checkout
        # (legacy/test layouts). The running gate's cwd is the supervisor's
        # active candidate checkout, so use it as the source of Git identity.
        root_value = _git(pathlib.Path.cwd(), "rev-parse", "--show-toplevel")
    root = pathlib.Path(root_value).resolve()
    plan_path = pathlib.Path(workspace) / "plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.is_file() else {"tasks": []}
    if mode == "tasks":
        toolchain_ids = list(dict.fromkeys(toolchain_gate.task_toolchain_id(workspace, task) for task in selection))
        scope = sorted({path for task_id in selection for task in plan["tasks"]
                        if isinstance(task, dict) and str(task.get("id")) == str(task_id)
                        for path in task.get("touches", []) if isinstance(path, str)})
    elif mode == "toolchains":
        toolchain_ids = list(dict.fromkeys(selection))
        scope = sorted({path for task in plan.get("tasks", []) if isinstance(task, dict)
                        and task.get("toolchain_id") in toolchain_ids
                        for path in task.get("touches", []) if isinstance(path, str)})
    else:
        entries = toolchain_gate.load_gate_entries(workspace)
        if len(entries) != 1:
            raise ValueError("legacy impact requires exactly one gate entry")
        toolchain_ids = [str(entries[0].get("toolchain_id") or entries[0].get("lang") or "legacy")]
        scope = []

    descriptors = []
    for identifier in toolchain_ids:
        if mode == "legacy":
            entry = entries[0]
        else:
            entry = toolchain_gate.gate_for_toolchain(workspace, identifier)
        descriptor = toolchain_gate._descriptor(entry)
        test = toolchain_gate.command_spec(entry, "test")
        if test is None:
            raise ValueError("toolchain %s has no configured test command" % identifier)
        language = descriptor.get("language") or entry.get("lang")
        descriptors.append({"id": identifier, "language": language,
                            "red_adapter": descriptor.get("red_adapter"),
                            "commands": {"test": test}})

    head = _git(root, "rev-parse", "HEAD")
    base_tree = _git(root, "rev-parse", "HEAD^{tree}")
    raw = _git(root, "diff", "--name-status", "-z", "HEAD", binary=True).split(b"\0")
    files: list[dict[str, str]] = []
    index = 0
    while index < len(raw) and raw[index]:
        status = raw[index].decode("ascii", "strict")
        index += 1
        if status.startswith("R") or status.startswith("C"):
            if index + 1 >= len(raw):
                raise ValueError("malformed Git rename/copy status")
            old_path, new_path = raw[index].decode("utf-8"), raw[index + 1].decode("utf-8")
            index += 2
            if status.startswith("R"):
                files.append({"status": "renamed", "old_path": old_path, "new_path": new_path})
            else:
                files.extend(({"status": "deleted", "path": old_path}, {"status": "added", "path": new_path}))
        else:
            if index >= len(raw):
                raise ValueError("malformed Git name-status output")
            path = raw[index].decode("utf-8")
            index += 1
            state = {"A": "added", "M": "modified", "D": "deleted", "T": "modified"}.get(status[:1])
            if state is None:
                raise ValueError("unknown Git change status: %s" % status)
            files.append({"status": state, "path": path})
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z", binary=True).split(b"\0")
    for raw_path in untracked:
        if raw_path:
            files.append({"status": "added", "path": raw_path.decode("utf-8")})
    tracked_paths = _git(root, "ls-files", "-z", binary=True).split(b"\0")
    test_paths = sorted({path.decode("utf-8") for path in tracked_paths if path}
                        | {item["path"] for item in files if item.get("status") != "deleted"}
                        | {item["new_path"] for item in files if item.get("status") == "renamed"})
    tree_digest = hashlib.sha256()
    tree_digest.update(_git(root, "diff", "--binary", "HEAD", binary=True))
    for item in sorted(files, key=lambda value: (value.get("path", value.get("old_path", "")), value["status"])):
        for name in (item.get("path"), item.get("new_path")):
            if name and (root / pathlib.PurePosixPath(name)).is_file():
                tree_digest.update(name.encode("utf-8"))
                tree_digest.update((root / pathlib.PurePosixPath(name)).read_bytes())
    tree_id = "commit:%s+sha256:%s" % (head, tree_digest.hexdigest())
    policy_path = scripts.parent / "toolchains" / "test-impact-rules.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    config_hash = _digest({"plan": plan, "toolchains": descriptors, "policy": policy})
    environment_hash = _digest({"python": sys.version, "platform": sys.platform,
                                 "path": os.environ.get("PATH", "")})
    diff = {"base_commit": head, "head_commit": head,
            "base_tree_hash": "commit:%s+sha256:%s" % (head, _digest(base_tree)),
            "tree_hash": tree_id, "config_hash": config_hash,
            "environment_hash": environment_hash, "task_scope": scope,
            "test_paths": [path for path in test_paths if "test" in pathlib.PurePosixPath(path).name.lower()],
            "files": files}
    manifest = test_impact.select(diff, None, descriptors, policy)
    manifest = validate_manifest(manifest)
    destination = pathlib.Path(workspace) / "impact-manifest.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, destination)
    candidate = {"commit": head, "tree_hash": tree_id, "config_hash": config_hash,
                 "environment_hash": environment_hash, "impact_manifest": manifest}
    record = {"candidate_commit": head, "tree_hash": tree_id, "config_hash": config_hash,
              "environment_hash": environment_hash, "impact_selection_hash": manifest["selection_hash"]}
    if not matches(record, candidate):
        raise ValueError("generated impact manifest does not match its candidate")
    return manifest
