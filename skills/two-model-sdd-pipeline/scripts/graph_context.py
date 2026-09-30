"""Prepare and query the run-scoped, script-owned R4 graph context cache."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import sqlite3
import sys
import tempfile
from contextlib import closing
from typing import Any


SCHEMA_VERSION = 1
_HASH = re.compile(r"^[0-9a-f]{64}$")
_SAFE_PATH = re.compile(r"^[^\\\x00]+$")

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import gate_evidence  # noqa: E402
import pathclass  # noqa: E402
import test_dependency_graph  # noqa: E402


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_path(value: Any) -> str:
    if (not isinstance(value, str) or not value or not _SAFE_PATH.fullmatch(value)
            or pathlib.PurePosixPath(value).is_absolute()
            or any(part in ("", ".", "..") for part in value.split("/"))
            or re.match(r"^[A-Za-z]:", value)):
        raise ValueError("graph context contains an unsafe repository path")
    return value


def _tree_identity(repository: pathlib.Path, source_commit: str) -> tuple[str, str]:
    commit = gate_evidence._git(repository, "rev-parse", "--verify", source_commit + "^{commit}")
    tree = gate_evidence._git(repository, "rev-parse", "--verify", commit + "^{tree}")
    if not re.fullmatch(r"[0-9a-f]{40,64}", commit) or not re.fullmatch(r"[0-9a-f]{40,64}", tree):
        raise ValueError("run-start source identity is malformed")
    return commit, tree


def _expected_version() -> tuple[str, str]:
    policy_bytes = test_dependency_graph.RULES_PATH.read_bytes()
    policy = json.loads(policy_bytes.decode("utf-8"))
    graph_policy = policy.get("graphify", {}) if isinstance(policy, dict) else {}
    versions = graph_policy.get("version_allowlist") if isinstance(graph_policy, dict) else None
    if not isinstance(versions, list) or len(versions) != 1 or not isinstance(versions[0], str):
        raise ValueError("Graphify version policy is missing or ambiguous")
    return versions[0], hashlib.sha256(policy_bytes).hexdigest()


def _run_identity(workspace: pathlib.Path) -> str:
    path = workspace / ".pipeline-identity.json"
    if not path.is_file():
        return "workspace:" + _digest(str(workspace.resolve()))
    value = json.loads(path.read_text(encoding="utf-8"))
    identity = value.get("identity") if isinstance(value, dict) else None
    if not isinstance(identity, str) or not _HASH.fullmatch(identity):
        raise ValueError("pipeline run identity is missing or malformed")
    return identity


def _read_meta(connection: sqlite3.Connection) -> dict[str, str]:
    return dict(connection.execute("SELECT key, value FROM metadata"))


def _cache_matches(path: pathlib.Path, repository: pathlib.Path, commit: str,
                   tree: str, version: str, policy_hash: str, run_identity: str) -> bool:
    if not path.is_file():
        return False
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            meta = _read_meta(db)
        return (meta.get("schema_version") == str(SCHEMA_VERSION)
                and meta.get("repository") == str(repository.resolve())
                and meta.get("source_commit") == commit
                and meta.get("source_tree") == tree
                and meta.get("run_identity") == run_identity
                and meta.get("graphify_version") == version
                and meta.get("policy_hash") == policy_hash
                and bool(_HASH.fullmatch(meta.get("graph_digest", ""))))
    except (OSError, sqlite3.Error, ValueError):
        return False


def _reachable(starts: list[str], adjacency: dict[str, list[str]]) -> list[str]:
    visited = set(starts)
    found: set[str] = set()
    pending = list(starts)
    while pending:
        current = pending.pop()
        for neighbor in adjacency.get(current, []):
            neighbor = _safe_path(neighbor)
            if neighbor in visited:
                continue
            visited.add(neighbor)
            found.add(neighbor)
            pending.append(neighbor)
    return sorted(found)


def _task_record(task: dict[str, Any], forward: dict[str, list[str]],
                 reverse: dict[str, list[str]]) -> dict[str, Any]:
    task_id = task.get("id")
    touches = task.get("touches", [])
    if isinstance(task_id, bool) or not isinstance(task_id, (str, int)):
        raise ValueError("plan task id is malformed")
    if not isinstance(touches, list) or not all(isinstance(path, str) for path in touches):
        raise ValueError("task touches must be a string array")
    normalized = sorted({_safe_path(path) for path in touches})
    dependencies = _reachable(normalized, forward)
    consumers = _reachable(normalized, reverse)
    tests = sorted(path for path in consumers if pathclass.is_test_path(path))
    return {
        "task_id": str(task_id),
        "touches": normalized,
        "touches_hash": _digest(normalized),
        "dependencies": dependencies,
        "consumers": consumers,
        "tests": tests,
    }


def _write_cache(path: pathlib.Path, metadata: dict[str, str],
                 forward: dict[str, list[str]], reverse: dict[str, list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="graph-context-", suffix=".sqlite3", dir=path.parent)
    os.close(fd)
    temp_path = pathlib.Path(temp_name)
    try:
        with closing(sqlite3.connect(str(temp_path))) as db:
            db.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("CREATE TABLE edges (relation TEXT NOT NULL, source TEXT NOT NULL, target TEXT NOT NULL, PRIMARY KEY (relation, source, target))")
            db.execute("CREATE INDEX edges_by_source ON edges (relation, source)")
            db.execute("CREATE INDEX edges_by_target ON edges (relation, target)")
            db.executemany("INSERT INTO metadata (key, value) VALUES (?, ?)", sorted(metadata.items()))
            rows = [("imports", source, target)
                    for source, targets in sorted(forward.items()) for target in sorted(targets)]
            db.executemany("INSERT INTO edges (relation, source, target) VALUES (?, ?, ?)", rows)
            db.commit()
        os.replace(temp_path, path)
    except Exception:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


def _write_status(workspace: pathlib.Path, complete: bool, diagnostics: list[str],
                  graph_digest: str = "") -> None:
    path = workspace / "graph-context-status.json"
    temporary = path.with_suffix(".json.tmp")
    value = {"schema_version": SCHEMA_VERSION, "complete": complete,
             "graph_digest": graph_digest, "diagnostics": list(diagnostics)}
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                         encoding="utf-8")
    os.replace(temporary, path)


def _task_metadata_path(directory: pathlib.Path, task_id: Any) -> pathlib.Path:
    if isinstance(task_id, bool) or not isinstance(task_id, (str, int)):
        raise ValueError("plan task id is malformed")
    identifier = str(task_id)
    if not re.fullmatch(r"[1-9][0-9]*", identifier):
        raise ValueError("plan task id is malformed")
    return directory / (identifier + ".json")


def _write_task_record(directory: pathlib.Path, plan: dict[str, Any],
                       graph: dict[str, Any], record: dict[str, Any]) -> pathlib.Path:
    directory.mkdir(parents=True, exist_ok=True)
    task_id = record.get("task_id")
    path = _task_metadata_path(directory, task_id)
    value = {
        "schema_version": SCHEMA_VERSION,
        "plan_hash": _digest(plan),
        "source_commit": graph.get("source_commit", ""),
        "source_tree": graph.get("source_tree", ""),
        "run_identity": graph.get("run_identity", ""),
        "graph_digest": graph.get("graph_digest", ""),
        "complete": graph.get("complete") is True and record.get("complete") is not False,
        "diagnostics": graph.get("diagnostics", []),
        "task": record,
    }
    value["metadata_hash"] = _digest(value)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)
    return path


def _write_task_metadata(directory: pathlib.Path, plan: dict[str, Any],
                         graph: dict[str, Any], forward: dict[str, list[str]],
                         reverse: dict[str, list[str]]) -> bool:
    all_valid = True
    for task in plan.get("tasks", []):
        try:
            record = _task_record(task, forward, reverse) if graph.get("complete") is True else {
                "task_id": str(task.get("id")), "touches": [], "touches_hash": "",
                "dependencies": [], "consumers": [], "tests": [], "complete": False,
                "requires_full_suite": True,
                "diagnostics": list(graph.get("diagnostics", [])),
            }
            record["complete"] = graph.get("complete") is True
            record["requires_full_suite"] = graph.get("complete") is not True
            record["diagnostics"] = list(graph.get("diagnostics", []))
            _write_task_record(directory, plan, graph, record)
        except (TypeError, ValueError, OSError):
            all_valid = False
    return all_valid


def _create_snapshot(repository: pathlib.Path, source_commit: str,
                     snapshot: pathlib.Path) -> None:
    files = gate_evidence._git_tree_files(repository, source_commit)
    blobs = gate_evidence._git_blob_map(repository, sorted({blob for _mode, blob, _path in files}))
    gate_evidence._make_snapshot(snapshot, files, [], False, blobs, repository)


def prepare(workspace: pathlib.Path, repository: pathlib.Path,
            plan_path: pathlib.Path, source_commit: str) -> dict[str, Any]:
    """Refresh one run-start AST graph and make its compact index reusable."""
    workspace = pathlib.Path(workspace).resolve()
    repository = pathlib.Path(repository).resolve()
    plan_path = pathlib.Path(plan_path).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    _write_status(workspace, False, ["run-start graph preparation is incomplete"])
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict) or not isinstance(plan.get("tasks"), list):
        raise ValueError("canonical plan must contain a tasks array")
    commit, tree = _tree_identity(repository, source_commit)
    run_identity = _run_identity(workspace)
    version, policy_hash = _expected_version()
    cache_path = workspace / "graph-context.sqlite3"
    task_path = workspace / "graph-task-context"
    if _cache_matches(cache_path, repository, commit, tree, version, policy_hash, run_identity):
        result = _refresh_task_metadata(workspace, plan_path, plan, cache_path, task_path)
        _write_status(workspace, result.get("complete") is True,
                      list(result.get("diagnostics", [])), result.get("graph_digest", ""))
        return result

    graph = {
        "complete": False,
        "forward_edges": {},
        "reverse_edges": {},
        "graphify_version": version,
        "graph_digest": "",
        "source_inventory_hash": "",
        "diagnostics": [],
        "source_commit": commit,
        "source_tree": tree,
        "run_identity": run_identity,
    }
    try:
        with tempfile.TemporaryDirectory(prefix="r4-graph-context-") as temporary:
            snapshot = pathlib.Path(temporary) / "source"
            _create_snapshot(repository, commit, snapshot)
            extracted = test_dependency_graph.build(snapshot, version)
        if extracted.get("complete") is True:
            forward = extracted.get("forward_edges")
            reverse = extracted.get("reverse_edges")
            digest = extracted.get("graph_digest")
            if (not isinstance(forward, dict) or not isinstance(reverse, dict)
                    or not isinstance(digest, str) or not _HASH.fullmatch(digest)):
                graph["diagnostics"] = ["Graphify dependency index is malformed"]
            else:
                graph.update(complete=True, forward_edges=forward, reverse_edges=reverse,
                             graph_digest=digest,
                             source_inventory_hash=extracted.get("source_inventory_hash", ""),
                             diagnostics=extracted.get("diagnostics", []))
        else:
            graph["diagnostics"] = extracted.get("diagnostics", ["Graphify dependency extraction is incomplete"])
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
        graph["diagnostics"] = ["Graph context preparation unavailable: " + str(exc)]

    forward = graph["forward_edges"] if graph["complete"] else {}
    reverse = graph["reverse_edges"] if graph["complete"] else {}
    metadata = {
        "schema_version": str(SCHEMA_VERSION),
        "repository": str(repository),
        "run_identity": run_identity,
        "source_commit": commit,
        "source_tree": tree,
        "graphify_version": version,
        "policy_hash": policy_hash,
        "graph_digest": graph["graph_digest"] or _digest({"commit": commit, "complete": False}),
        "source_inventory_hash": graph["source_inventory_hash"],
        "complete": "true" if graph["complete"] else "false",
        "diagnostics": json.dumps(graph["diagnostics"], ensure_ascii=False),
    }
    _write_cache(cache_path, metadata, forward, reverse)
    graph["graph_digest"] = metadata["graph_digest"]
    all_valid = _write_task_metadata(task_path, plan, graph, forward, reverse)
    if not all_valid:
        graph["complete"] = False
        graph["diagnostics"] = list(graph.get("diagnostics", [])) + [
            "one or more task graph slices could not be validated"]
    result = {**graph, "cache_path": str(cache_path), "task_metadata_path": str(task_path)}
    _write_status(workspace, result.get("complete") is True,
                  list(result.get("diagnostics", [])), result.get("graph_digest", ""))
    return result


def _refresh_task_metadata(workspace: pathlib.Path, plan_path: pathlib.Path,
                           plan: dict[str, Any], cache_path: pathlib.Path,
                           task_path: pathlib.Path) -> dict[str, Any]:
    with closing(sqlite3.connect(cache_path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        meta = _read_meta(db)
        graph = {
            "complete": meta.get("complete") == "true",
            "graphify_version": meta.get("graphify_version"),
            "graph_digest": meta.get("graph_digest", ""),
            "source_inventory_hash": meta.get("source_inventory_hash", ""),
            "diagnostics": json.loads(meta.get("diagnostics", "[]")),
            "source_commit": meta.get("source_commit", ""),
            "source_tree": meta.get("source_tree", ""),
            "run_identity": meta.get("run_identity", ""),
        }
        task_path.mkdir(parents=True, exist_ok=True)
        all_valid = True
        for task in plan.get("tasks", []):
            try:
                record = _task_record_from_db(db, task) if graph["complete"] else {
                    "task_id": str(task.get("id")), "touches": [], "touches_hash": "",
                    "dependencies": [], "consumers": [], "tests": [], "complete": False,
                    "requires_full_suite": True,
                    "diagnostics": list(graph["diagnostics"]),
                }
                record["complete"] = graph["complete"]
                record["requires_full_suite"] = not graph["complete"]
                record["diagnostics"] = list(graph["diagnostics"])
                _write_task_record(task_path, plan, graph, record)
            except (TypeError, ValueError, OSError):
                all_valid = False
    task_path.mkdir(parents=True, exist_ok=True)
    graph["complete"] = graph["complete"] and all_valid
    if not all_valid:
        graph["diagnostics"] = list(graph.get("diagnostics", [])) + [
            "one or more task graph slices could not be refreshed"]
    return {**graph, "cache_path": str(cache_path), "task_metadata_path": str(task_path)}


def _load_edges(db: sqlite3.Connection) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    forward: dict[str, list[str]] = {}
    reverse: dict[str, list[str]] = {}
    for relation, source, target in db.execute(
            "SELECT relation, source, target FROM edges ORDER BY source, target"):
        source = _safe_path(source)
        target = _safe_path(target)
        forward.setdefault(source, []).append(target)
        reverse.setdefault(target, []).append(source)
    return forward, reverse


def _neighbors(db: sqlite3.Connection, path: str, reverse: bool) -> list[str]:
    field = "source" if reverse else "target"
    match = "target" if reverse else "source"
    rows = db.execute("SELECT %s FROM edges WHERE relation = 'imports' AND %s = ? ORDER BY %s" %
                      (field, match, field), (path,))
    return [_safe_path(row[0]) for row in rows]


def _reachable_db(db: sqlite3.Connection, starts: list[str], reverse: bool) -> list[str]:
    visited = set(starts)
    found: set[str] = set()
    pending = list(starts)
    while pending:
        current = pending.pop()
        for neighbor in _neighbors(db, current, reverse):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            found.add(neighbor)
            pending.append(neighbor)
    return sorted(found)


def _task_record_from_db(db: sqlite3.Connection, task: dict[str, Any]) -> dict[str, Any]:
    task_id = task.get("id")
    touches = task.get("touches", [])
    if isinstance(task_id, bool) or not isinstance(task_id, (str, int)):
        raise ValueError("plan task id is malformed")
    if not isinstance(touches, list) or not all(isinstance(path, str) for path in touches):
        raise ValueError("task touches must be a string array")
    normalized = sorted({_safe_path(path) for path in touches})
    consumers = _reachable_db(db, normalized, reverse=True)
    return {
        "task_id": str(task_id), "touches": normalized,
        "touches_hash": _digest(normalized),
        "dependencies": _reachable_db(db, normalized, reverse=False),
        "consumers": consumers,
        "tests": sorted(path for path in consumers if pathclass.is_test_path(path)),
    }


def impact_reverse_edges(db: sqlite3.Connection, changed_paths: list[str]) -> dict[str, list[str]]:
    """Return only the reverse dependency neighborhood reachable from changes."""
    pending = [_safe_path(path) for path in changed_paths]
    visited: set[str] = set()
    result: dict[str, list[str]] = {}
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        consumers = _neighbors(db, current, reverse=True)
        if consumers:
            result[current] = consumers
            pending.extend(path for path in consumers if path not in visited)
    return {key: result[key] for key in sorted(result)}


def load_task_context(workspace: pathlib.Path, task: dict[str, Any]) -> dict[str, Any]:
    """Read only the task's cached slice, never the raw Graphify graph."""
    workspace = pathlib.Path(workspace)
    task_id = str(task.get("id"))
    metadata_dir = workspace / "graph-task-context"
    cache_path = workspace / "graph-context.sqlite3"
    status_path = workspace / "graph-context-status.json"
    if status_path.is_file():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
            if (not isinstance(status, dict) or status.get("schema_version") != SCHEMA_VERSION
                    or status.get("complete") is not True):
                return _empty_task(task_id, status.get("diagnostics", [])
                                   if isinstance(status, dict) else ["run-start graph context is unavailable"])
        except (OSError, ValueError, TypeError):
            return _empty_task(task_id, ["run-start graph context status is malformed"])
    try:
        metadata_path = _task_metadata_path(metadata_dir, task.get("id"))
    except ValueError as exc:
        return _empty_task(task_id, [str(exc)])
    if not cache_path.is_file():
        return _empty_task(task_id, ["run-start graph context is unavailable"])
    try:
        with closing(sqlite3.connect(cache_path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            meta = _read_meta(db)
            if (meta.get("schema_version") != str(SCHEMA_VERSION)
                    or not _HASH.fullmatch(meta.get("graph_digest", ""))):
                return _empty_task(task_id, ["task graph cache is malformed"])
            if meta.get("complete") != "true":
                return _empty_task(task_id, json.loads(meta.get("diagnostics", "[]")))
            if metadata_path.is_file():
                data = json.loads(metadata_path.read_text(encoding="utf-8"))
                metadata_hash = data.pop("metadata_hash", None)
                if (isinstance(data, dict) and data.get("schema_version") == SCHEMA_VERSION
                        and isinstance(metadata_hash, str) and _digest(data) == metadata_hash
                        and data.get("complete") is True
                        and data.get("graph_digest") == meta.get("graph_digest")
                        and data.get("source_commit") == meta.get("source_commit")
                        and data.get("source_tree") == meta.get("source_tree")
                        and data.get("run_identity") == meta.get("run_identity")):
                    record = data.get("task")
                    touches = task.get("touches", [])
                    normalized = sorted({_safe_path(path) for path in touches}) if isinstance(touches, list) else []
                    if (isinstance(record, dict) and record.get("touches_hash") == _digest(normalized)
                            and record.get("touches") == normalized):
                        return {**record, "complete": True, "requires_full_suite": False,
                                "graph_digest": data["graph_digest"],
                                "source_commit": data["source_commit"],
                                "source_tree": data["source_tree"], "diagnostics": []}
            record = _task_record_from_db(db, task)
            record["complete"] = True
            record["requires_full_suite"] = False
            record["diagnostics"] = []
            data = {"schema_version": SCHEMA_VERSION, "plan_hash": "",
                    "source_commit": meta["source_commit"], "source_tree": meta["source_tree"],
                    "graph_digest": meta["graph_digest"], "complete": True,
                    "diagnostics": [], "task": record}
            _write_task_record(metadata_dir, {"tasks": []}, {
                "source_commit": data["source_commit"], "source_tree": data["source_tree"],
                "run_identity": meta.get("run_identity", ""),
                "graph_digest": data["graph_digest"], "complete": True, "diagnostics": []}, record)
            return {**record, "graph_digest": data["graph_digest"],
                    "source_commit": data["source_commit"], "source_tree": data["source_tree"]}
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error, json.JSONDecodeError) as exc:
        return _empty_task(task_id, ["task graph context unavailable: " + str(exc)])


def _empty_task(task_id: str, diagnostics: list[str]) -> dict[str, Any]:
    return {"task_id": task_id, "touches": [], "touches_hash": "", "dependencies": [],
            "consumers": [], "tests": [], "complete": False, "requires_full_suite": True,
            "diagnostics": sorted(set(str(item) for item in diagnostics))}
