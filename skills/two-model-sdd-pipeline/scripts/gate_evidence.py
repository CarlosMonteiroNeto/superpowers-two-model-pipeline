"""Candidate-bound impact manifests and gate evidence matching."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import sqlite3
import subprocess
import sys
import tempfile
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
    provenance = evidence.get("graph_provenance")
    if not isinstance(provenance, dict) or not isinstance(provenance.get("complete"), bool):
        raise ValueError("impact manifest graph provenance is missing")
    if provenance["complete"]:
        if provenance.get("kind") == "run_start":
            if (not isinstance(provenance.get("run_start_commit"), str)
                    or not _COMMIT.fullmatch(provenance["run_start_commit"])
                    or not isinstance(provenance.get("run_start_tree_hash"), str)
                    or not isinstance(provenance.get("graphify_version"), str)
                    or not isinstance(provenance.get("graph_digest"), str)
                    or not _HASH.fullmatch(provenance["graph_digest"])):
                raise ValueError("impact manifest has incomplete run-start graph provenance")
        else:
            if (provenance.get("base_commit") != identity.get("base_commit")
                    or provenance.get("candidate_commit") != identity.get("head_commit")
                    or provenance.get("candidate_tree_hash") != identity.get("tree_hash")
                    or not isinstance(provenance.get("graphify_version"), str)):
                raise ValueError("impact manifest graph provenance does not match its candidate")
            for side in ("base", "candidate"):
                item = provenance.get(side)
                if (not isinstance(item, dict) or item.get("complete") is not True
                        or not isinstance(item.get("graph_digest"), str) or not _HASH.fullmatch(item["graph_digest"])
                        or not isinstance(item.get("source_inventory_hash"), str)
                        or not _HASH.fullmatch(item["source_inventory_hash"])):
                    raise ValueError("impact manifest has incomplete %s graph provenance" % side)
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


def _safe_repo_path(value: str) -> pathlib.PurePosixPath:
    path = pathlib.PurePosixPath(value)
    if (path.is_absolute() or not value or "\\" in value
            or re.match(r"^[A-Za-z]:", value)
            or any(part in ("", ".", "..") for part in value.split("/"))):
        raise ValueError("unsafe path in Git snapshot: " + repr(value))
    return path


def _git_tree_files(root: pathlib.Path, commit: str) -> list[tuple[str, str, str]]:
    raw = _git(root, "ls-tree", "-rz", "--full-tree", commit, binary=True)
    records = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, name = record.split(b"\t", 1)
        mode, kind, blob = metadata.decode("ascii").split(" ")
        path = name.decode("utf-8", "strict")
        _safe_repo_path(path)
        if kind != "blob" or mode not in ("100644", "100755"):
            raise ValueError("Git snapshot contains a non-regular source path")
        records.append((mode, blob, path))
    return records


def _write_snapshot_file(root: pathlib.Path, relative: str, content: bytes) -> None:
    rel = _safe_repo_path(relative)
    target = root.joinpath(*rel.parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def _git_blob_map(root: pathlib.Path, object_ids: list[str]) -> dict[str, bytes]:
    if not object_ids:
        return {}
    result = subprocess.run(["git", "-C", str(root), "cat-file", "--batch"],
                            input=("\n".join(object_ids) + "\n").encode("ascii"),
                            capture_output=True, check=True)
    data = result.stdout
    cursor = 0
    blobs: dict[str, bytes] = {}
    for expected in object_ids:
        end = data.find(b"\n", cursor)
        if end < 0:
            raise ValueError("Git returned a truncated object header")
        fields = data[cursor:end].decode("ascii").split(" ")
        if len(fields) != 3 or fields[0] != expected or fields[1] != "blob":
            raise ValueError("Git returned a non-blob snapshot object")
        size = int(fields[2])
        cursor = end + 1
        blob_end = cursor + size
        if blob_end >= len(data) or data[blob_end:blob_end + 1] != b"\n":
            raise ValueError("Git returned a truncated blob")
        blobs[expected] = data[cursor:blob_end]
        cursor = blob_end + 1
    if cursor != len(data):
        raise ValueError("Git returned unexpected snapshot object data")
    return blobs


def _make_snapshot(snapshot: pathlib.Path, base_files: list[tuple[str, str, str]],
                   changes: list[dict[str, str]], candidate: bool,
                   blobs: dict[str, bytes], root: pathlib.Path) -> None:
    snapshot.mkdir(parents=True)
    if not candidate:
        for _mode, blob, path in base_files:
            _write_snapshot_file(snapshot, path, blobs[blob])
        return
    removed = set()
    added = set()
    for item in changes:
        status = item["status"]
        if status == "deleted":
            removed.add(item["path"])
        elif status == "renamed":
            removed.add(item["old_path"])
            added.add(item["new_path"])
        else:
            added.add(item["path"])
    for _mode, blob, path in base_files:
        if path in removed or path in added:
            continue
        _write_snapshot_file(snapshot, path, blobs[blob])
    for relative in sorted(added):
        rel = _safe_repo_path(relative)
        source = root.joinpath(*rel.parts)
        if not source.is_file() or source.is_symlink():
            raise ValueError("candidate snapshot has a missing or non-regular changed path: " + relative)
        _write_snapshot_file(snapshot, relative, source.read_bytes())


def _graph_evidence(root: pathlib.Path, base_commit: str, base_tree: str, head: str,
                    tree_id: str, files: list[dict[str, str]], policy: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    scripts = pathlib.Path(__file__).resolve().parent
    sys.path.insert(0, str(scripts))
    import test_dependency_graph

    graph_policy = policy.get("graphify") if isinstance(policy, dict) else None
    versions = graph_policy.get("version_allowlist") if isinstance(graph_policy, dict) else None
    if not isinstance(versions, list) or len(versions) != 1 or not isinstance(versions[0], str):
        return None, {"complete": False, "diagnostics": ["Graphify version policy is missing or ambiguous"]}
    provenance: dict[str, Any] = {"graphify_version": versions[0], "base": {}, "candidate": {}}
    try:
        base_files = _git_tree_files(root, base_commit)
        blobs = _git_blob_map(root, sorted({blob for _mode, blob, _path in base_files}))
        with tempfile.TemporaryDirectory(prefix="r4-impact-") as temporary:
            temp = pathlib.Path(temporary)
            base_snapshot, candidate_snapshot = temp / "base", temp / "candidate"
            _make_snapshot(base_snapshot, base_files, files, False, blobs, root)
            _make_snapshot(candidate_snapshot, base_files, files, True, blobs, root)
            base = test_dependency_graph.build(base_snapshot, versions[0])
            candidate = test_dependency_graph.build(candidate_snapshot, versions[0])
            for name, result in (("base", base), ("candidate", candidate)):
                provenance[name] = {
                    "complete": result.get("complete") is True,
                    "graph_digest": result.get("graph_digest"),
                    "source_inventory_hash": result.get("source_inventory_hash"),
                    "graphify_version": result.get("graphify_version"),
                    "diagnostics": result.get("diagnostics", []),
                }
            valid = all(result.get("complete") is True
                        and result.get("graphify_version") == versions[0]
                        and isinstance(result.get("graph_digest"), str)
                        and _HASH.fullmatch(result["graph_digest"])
                        and isinstance(result.get("source_inventory_hash"), str)
                        and _HASH.fullmatch(result["source_inventory_hash"])
                        and isinstance(result.get("reverse_edges"), dict)
                        for result in (base, candidate))
            if not valid:
                provenance["complete"] = False
                return None, provenance
            edges: dict[str, set[str]] = {}
            for result in (base, candidate):
                for source, targets in result["reverse_edges"].items():
                    edges.setdefault(source, set()).update(targets)
            graph = {"version": 1, "base_commit": base_commit,
                     "base_tree_hash": "commit:%s+sha256:%s" % (base_commit, _digest(base_tree)),
                     "reverse_edges": {key: sorted(value) for key, value in sorted(edges.items())},
                     "provenance": provenance}
            provenance["complete"] = True
            provenance["base_commit"] = base_commit
            provenance["base_tree_hash"] = "commit:%s+sha256:%s" % (base_commit, _digest(base_tree))
            provenance["candidate_commit"] = head
            provenance["candidate_tree_hash"] = tree_id
            graph["provenance"] = provenance
            return graph, provenance
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        provenance["complete"] = False
        provenance["diagnostics"] = ["Graphify snapshots unavailable: " + str(exc)]
        return None, provenance


def _run_start_graph(workspace: pathlib.Path, changed_paths: list[str],
                     fallback_commit: str, policy: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Query the run-start SQLite index for only paths reachable from this diff."""
    scripts = pathlib.Path(__file__).resolve().parent
    sys.path.insert(0, str(scripts))
    import graph_context

    provenance: dict[str, Any] = {"kind": "run_start", "complete": False,
                                  "diagnostics": ["run-start graph cache is unavailable"]}
    cache_path = workspace / "graph-context.sqlite3"
    if not cache_path.is_file():
        return None, provenance
    try:
        status_path = workspace / "graph-context-status.json"
        status = None
        if status_path.is_file():
            status = json.loads(status_path.read_text(encoding="utf-8"))
            if not isinstance(status, dict) or status.get("complete") is not True:
                diagnostics = status.get("diagnostics", []) if isinstance(status, dict) else []
                return None, {"kind": "run_start", "complete": False,
                              "diagnostics": diagnostics or ["run-start graph refresh is incomplete"]}
        graph_policy = policy.get("graphify", {})
        versions = graph_policy.get("version_allowlist") if isinstance(graph_policy, dict) else None
        if not isinstance(versions, list) or len(versions) != 1 or not isinstance(versions[0], str):
            raise ValueError("Graphify version policy is missing or ambiguous")
        source_commit = fallback_commit
        base_path = workspace / "base-commit.txt"
        if base_path.is_file():
            source_commit = base_path.read_text(encoding="utf-8").strip()
        _, source_tree = graph_context._tree_identity(workspace, source_commit)
        run_identity = graph_context._run_identity(workspace)
        _, policy_hash = graph_context._expected_version()
        with graph_context.closing(graph_context.sqlite3.connect(
                cache_path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            meta = graph_context._read_meta(db)
            diagnostics = json.loads(meta.get("diagnostics", "[]"))
            provenance = {"kind": "run_start", "complete": False,
                          "run_start_commit": meta.get("source_commit", ""),
                          "run_start_tree": meta.get("source_tree", ""),
                          "graph_digest": meta.get("graph_digest", ""),
                          "graphify_version": meta.get("graphify_version", ""),
                          "diagnostics": diagnostics}
            if (meta.get("schema_version") != str(graph_context.SCHEMA_VERSION)
                    or meta.get("complete") != "true"
                    or meta.get("source_commit") != source_commit
                    or meta.get("source_tree") != source_tree
                    or meta.get("run_identity") != run_identity
                    or meta.get("policy_hash") != policy_hash
                    or meta.get("graphify_version") != versions[0]
                    or (status is not None and status.get("graph_digest") != meta.get("graph_digest"))
                    or not _HASH.fullmatch(meta.get("graph_digest", ""))):
                provenance["diagnostics"] = diagnostics or ["run-start graph cache identity is stale or incomplete"]
                return None, provenance
            repository = pathlib.Path(meta.get("repository", ""))
            if not repository.is_absolute() or not repository.is_dir():
                raise ValueError("run-start graph repository is unavailable")
            # Linked task worktrees share the repository, but have different roots.
            cached_common = pathlib.Path(_git(repository, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
            current_common = pathlib.Path(_git(workspace, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
            if cached_common != current_common:
                raise ValueError("run-start graph belongs to another repository")
            reverse = graph_context.impact_reverse_edges(db, changed_paths)
        run_tree_hash = "commit:%s+sha256:%s" % (
            source_commit, _digest(provenance["run_start_tree"]))
        provenance.update(complete=True, run_start_tree_hash=run_tree_hash,
                          diagnostics=[])
        return ({"version": 1, "base_commit": source_commit,
                 "base_tree_hash": run_tree_hash, "reverse_edges": reverse,
                 "provenance": provenance}, provenance)
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error, json.JSONDecodeError) as exc:
        provenance["diagnostics"] = ["run-start graph cache unavailable: " + str(exc)]
        return None, provenance


def _file_hash(root: pathlib.Path, relative: str) -> str | None:
    pure = pathlib.PurePosixPath(relative) if isinstance(relative, str) else None
    if (pure is None or not relative or "\\" in relative or pure.is_absolute()
            or re.match(r"^[A-Za-z]:", relative)
            or any(part in ("", ".", "..") for part in relative.split("/"))):
        return None
    path = root.joinpath(*pure.parts)
    try:
        if not path.is_file() or path.is_symlink():
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _green_inputs(workspace: pathlib.Path, tests: list[str]) -> dict[str, dict[str, str]]:
    """Capture each test plus its run-start imported files for later validation."""
    scripts = pathlib.Path(__file__).resolve().parent
    sys.path.insert(0, str(scripts))
    import graph_context

    cache = workspace / "graph-context.sqlite3"
    if not cache.is_file():
        return {}
    root_value = _git(workspace, "rev-parse", "--show-toplevel")
    root = pathlib.Path(root_value)
    result: dict[str, dict[str, str]] = {}
    with graph_context.closing(graph_context.sqlite3.connect(
            cache.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        meta = graph_context._read_meta(db)
        if meta.get("complete") != "true":
            return {}
        for test in tests:
            paths = sorted({test, *graph_context._reachable_db(db, [test], reverse=False)})
            hashes = {path: value for path in paths
                      if (value := _file_hash(root, path)) is not None}
            if len(hashes) == len(paths):
                result[test] = hashes
    return result


def record_green_evidence(workspace: str | pathlib.Path, task_id: str,
                          manifest: dict[str, Any]) -> pathlib.Path | None:
    """Persist exact task Green test and input evidence for integration subtraction."""
    provenance = manifest.get("evidence", {}).get("graph_provenance", {})
    if not provenance.get("complete") or provenance.get("kind") != "run_start":
        return None
    by_toolchain: dict[str, dict[str, Any]] = {}
    all_tests: set[str] = set()
    for command in manifest.get("commands", []):
        tests = command.get("tests", []) if command.get("full_suite") is False else []
        if not tests:
            continue
        identity = command.get("toolchain_id")
        if not isinstance(identity, str) or not identity:
            raise ValueError("Green evidence has an invalid toolchain identity")
        by_toolchain[identity] = {"tests": sorted(set(tests)), "language": command.get("language")}
        all_tests.update(tests)
    if not all_tests:
        return None
    inputs = _green_inputs(pathlib.Path(workspace), sorted(all_tests))
    for value in by_toolchain.values():
        value["inputs"] = {test: inputs[test] for test in value["tests"] if test in inputs}
        value["tests"] = sorted(value["inputs"])
    by_toolchain = {key: value for key, value in by_toolchain.items() if value["tests"]}
    if not by_toolchain:
        return None
    identity = manifest["identity"]
    evidence = {
        "schema_version": 1, "task_id": str(task_id),
        "candidate_commit": identity["head_commit"], "tree_hash": identity["tree_hash"],
        "config_hash": identity["config_hash"], "environment_hash": identity["environment_hash"],
        "toolchains_hash": manifest["evidence"]["toolchains_hash"],
        "run_start_commit": provenance["run_start_commit"],
        "graph_digest": provenance["graph_digest"], "toolchains": by_toolchain,
    }
    evidence["evidence_hash"] = _digest(evidence)
    directory = pathlib.Path(workspace) / "green-evidence"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / ("task-%s.json" % task_id)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                         encoding="utf-8")
    os.replace(temporary, destination)
    return destination


def _valid_green_tests(workspace: pathlib.Path, root: pathlib.Path,
                       manifest: dict[str, Any]) -> dict[str, set[str]]:
    provenance = manifest.get("evidence", {}).get("graph_provenance", {})
    if not provenance.get("complete") or provenance.get("kind") != "run_start":
        return {}
    output: dict[str, set[str]] = {}
    directory = workspace / "green-evidence"
    if not directory.is_dir():
        return output
    for path in sorted(directory.glob("task-*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            signature = record.pop("evidence_hash", None)
            if (record.get("schema_version") != 1 or not isinstance(signature, str)
                    or _digest(record) != signature
                    or not isinstance(record.get("candidate_commit"), str)
                    or not _COMMIT.fullmatch(record["candidate_commit"])
                    or not isinstance(record.get("tree_hash"), str)
                    or not (re.fullmatch(r"[0-9a-f]{64}", record["tree_hash"])
                            or re.fullmatch(r"commit:[0-9a-f]{7,64}\+sha256:[0-9a-f]{64}", record["tree_hash"]))
                    or record.get("config_hash") != manifest["identity"]["config_hash"]
                    or record.get("environment_hash") != manifest["identity"]["environment_hash"]
                    or record.get("toolchains_hash") != manifest["evidence"]["toolchains_hash"]
                    or record.get("run_start_commit") != provenance.get("run_start_commit")
                    or record.get("graph_digest") != provenance.get("graph_digest")):
                continue
            toolchains = record.get("toolchains")
            if not isinstance(toolchains, dict):
                continue
            for identifier, item in toolchains.items():
                tests = item.get("tests") if isinstance(item, dict) else None
                inputs = item.get("inputs") if isinstance(item, dict) else None
                if not isinstance(tests, list) or not isinstance(inputs, dict):
                    continue
                for test in tests:
                    expected = inputs.get(test)
                    if (not isinstance(expected, dict) or not expected
                            or any(_file_hash(root, source) != digest
                                   for source, digest in expected.items())):
                        continue
                    output.setdefault(identifier, set()).add(test)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return output


def _subtract_green_tests(workspace: pathlib.Path, root: pathlib.Path,
                          manifest: dict[str, Any], descriptors: list[dict[str, Any]]) -> list[dict[str, str]]:
    green = _valid_green_tests(workspace, root, manifest)
    if not green:
        return []
    import test_impact
    by_id = {str(item["id"]): item for item in descriptors}
    removed: list[dict[str, str]] = []
    tests_left: set[str] = set()
    for command in manifest["commands"]:
        identifier = command["toolchain_id"]
        descriptor = by_id.get(identifier, {})
        command_tests = command.get("tests", [])
        eligible = green.get(identifier, set())
        subtract = sorted(set(command_tests) & eligible) if command.get("full_suite") is False else []
        if not subtract:
            tests_left.update(command_tests)
            continue
        remaining = sorted(set(command_tests) - set(subtract))
        command["tests"] = remaining
        if remaining:
            command["argv"] = test_impact.affected_argv(
                descriptor.get("commands", {}).get("test", {}).get("argv", []),
                descriptor.get("red_adapter"), remaining)
            tests_left.update(remaining)
        else:
            command["skip_tests"] = True
            command["argv"] = []
        removed.extend({"toolchain_id": identifier, "test": test} for test in subtract)
    manifest["tests"] = sorted(tests_left)
    return removed


def create_workspace_manifest(workspace: str, selection: list[str], mode: str) -> dict[str, Any]:
    """Create a conservative manifest from current Git state and ledger commands.

    Dependency evidence is extracted only from disposable Git base/candidate
    snapshots. A caller cannot supply a graph or test path list to this function.
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
        try:
            toolchain_ids = list(dict.fromkeys(toolchain_gate.task_toolchain_id(workspace, task) for task in selection))
        except toolchain_gate.GateContractError as exc:
            legacy_entries = toolchain_gate.load_gate_entries(workspace)
            if ("no explicit toolchain_id" not in str(exc) or len(legacy_entries) != 1
                    or "toolchain_descriptor" in legacy_entries[0]):
                raise
            entries = legacy_entries
            toolchain_ids = [str(entries[0].get("toolchain_id") or entries[0].get("lang") or "legacy")]
            mode = "legacy-task"
        scope = sorted({path for task_id in selection for task in plan["tasks"]
                        if isinstance(task, dict) and str(task.get("id")) == str(task_id)
                        for path in task.get("touches", []) if isinstance(path, str)})
    elif mode == "toolchains":
        toolchain_ids = list(dict.fromkeys(selection))
        required_ids = sorted({toolchain_gate.task_toolchain_id(workspace, str(task.get("id")))
                               for task in plan.get("tasks", []) if isinstance(task, dict)
                               and task.get("id") is not None})
        if sorted(toolchain_ids) != required_ids:
            raise ValueError("--toolchains must cover every toolchain in the supervisor-owned plan; use --tasks for task scope")
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
        if mode in ("legacy", "legacy-task"):
            entry = entries[0]
        else:
            entry = toolchain_gate.gate_for_toolchain(workspace, identifier)
        descriptor = toolchain_gate._descriptor(entry)
        commands = {name: toolchain_gate.command_spec(entry, name)
                    for name in ("test", "analyze", "format")}
        commands = {name: ({**command, "cwd": command.get("cwd") or str(root)}) if command else None
                    for name, command in commands.items()}
        test = commands["test"]
        if test is None:
            raise ValueError("toolchain %s has no configured test command" % identifier)
        language = descriptor.get("language") or entry.get("lang")
        descriptors.append({"id": identifier, "descriptor": descriptor,
                            "language": language, "red_adapter": descriptor.get("red_adapter"),
                            "commands": commands})

    head = _git(root, "rev-parse", "HEAD")
    requested_base = os.environ.get("PIPELINE_IMPACT_BASE_COMMIT") or head
    base = _git(root, "rev-parse", "--verify", requested_base + "^{commit}")
    _git(root, "merge-base", "--is-ancestor", base, head)
    base_tree = _git(root, "rev-parse", base + "^{tree}")
    raw = _git(root, "diff", "--name-status", "-z", base, binary=True).split(b"\0")
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
    tree_digest.update(_git(root, "diff", "--binary", base, binary=True))
    for item in sorted(files, key=lambda value: (value.get("path", value.get("old_path", "")), value["status"])):
        for name in (item.get("path"), item.get("new_path")):
            if name and (root / pathlib.PurePosixPath(name)).is_file():
                tree_digest.update(name.encode("utf-8"))
                tree_digest.update((root / pathlib.PurePosixPath(name)).read_bytes())
    tree_id = "commit:%s+sha256:%s" % (head, tree_digest.hexdigest())
    policy_path = scripts.parent / "toolchains" / "test-impact-rules.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    config_hash = _digest({"manifest_version": "r4-impact-gates-2", "plan": plan,
                           "toolchains": descriptors, "policy": policy})
    environment_hash = _digest({"python": sys.version, "platform": sys.platform,
                                 "path": os.environ.get("PATH", "")})
    diff = {"base_commit": base, "head_commit": head,
            "base_tree_hash": "commit:%s+sha256:%s" % (base, _digest(base_tree)),
            "tree_hash": tree_id, "config_hash": config_hash,
            "environment_hash": environment_hash, "task_scope": scope,
            "test_paths": [path for path in test_paths if "test" in pathlib.PurePosixPath(path).name.lower()],
            "files": files}
    run_start_commit = base
    run_start_path = pathlib.Path(workspace) / "base-commit.txt"
    if run_start_path.is_file():
        run_start_commit = run_start_path.read_text(encoding="utf-8").strip()
    diff["run_start_commit"] = run_start_commit
    phase = os.environ.get("PIPELINE_GATE_PHASE", "task")
    if phase in ("baseline", "closing"):
        graph, graph_provenance = None, {"complete": False,
            "diagnostics": ["full test suites are required in %s phase" % phase]}
    else:
        changed_paths = sorted({path for item in files
                                for path in (item.get("path"), item.get("old_path"), item.get("new_path"))
                                if path})
        graph, graph_provenance = _run_start_graph(pathlib.Path(workspace),
                                                    changed_paths,
                                                    run_start_commit, policy)
        if graph is not None:
            diff["run_start_tree_hash"] = graph["base_tree_hash"]
    manifest = test_impact.select(diff, graph, descriptors, policy)
    manifest["evidence"]["graph_provenance"] = graph_provenance
    green_subtractions: list[dict[str, str]] = []
    if phase == "integration" and graph is not None:
        green_subtractions = _subtract_green_tests(pathlib.Path(workspace), root,
                                                   manifest, descriptors)
    manifest["evidence"]["green_subtractions"] = green_subtractions
    manifest["selection_hash"] = _digest({key: value for key, value in manifest.items()
                                           if key != "selection_hash"})
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
