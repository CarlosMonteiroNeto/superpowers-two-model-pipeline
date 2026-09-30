"""Evidence-bound affected-test selection with conservative full-suite fallback."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from collections import deque
from typing import Any


_COMMIT = re.compile(r"^[0-9a-fA-F]{7,64}$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_TREE_IDENTITY = re.compile(
    r"^(?:[0-9a-fA-F]{64}|tree:sha256:[0-9a-fA-F]{64}|commit:[0-9a-fA-F]{7,64}\+sha256:[0-9a-fA-F]{64})$"
)
_ALLOWED_STATUS = {"added", "modified", "deleted", "renamed"}
def _fail(message: str) -> None:
    raise ValueError("invalid test impact input: " + message)


def _canonical_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        _fail("%s must be a nonempty repository-relative path" % label)
    if "\\" in value or value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        _fail("%s must use a relative POSIX path: %s" % (label, value))
    parts = value.split("/")
    if any(part in ("", ".", "..") or part.startswith("-") for part in parts):
        _fail("%s contains an unsafe path selector: %s" % (label, value))
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        _fail("%s contains a control character" % label)
    return value


def _paths(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        _fail("%s must be a list" % label)
    result = [_canonical_path(item, label) for item in value]
    if len(result) != len(set(result)):
        _fail("%s contains duplicate paths" % label)
    return sorted(result)


def _valid_commit(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _COMMIT.fullmatch(value):
        _fail("%s must be a hexadecimal commit identity" % label)
    return value.lower()


def _valid_hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        _fail("%s must be a SHA-256 identity" % label)
    return value.lower()


def _valid_tree_identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _TREE_IDENTITY.fullmatch(value):
        _fail("%s must be a tree SHA-256 or R3 source-snapshot identity" % label)
    return value.lower()


def _digest_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _globs(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        _fail("%s must be a list of path globs" % label)
    for pattern in value:
        if ("\\" in pattern or pattern.startswith("/") or re.match(r"^[A-Za-z]:", pattern)
                or "\x00" in pattern or any(part in ("", ".", "..") for part in pattern.split("/"))):
            _fail("%s contains an unsafe path glob: %s" % (label, pattern))
    return value


def _read_diff(diff: Any) -> tuple[dict[str, Any], list[dict[str, str]], list[str], list[str]]:
    if not isinstance(diff, dict):
        _fail("diff must be an object")
    normalized = dict(diff)
    normalized["base_commit"] = _valid_commit(diff.get("base_commit"), "diff.base_commit")
    normalized["head_commit"] = _valid_commit(diff.get("head_commit"), "diff.head_commit")
    normalized["base_tree_hash"] = _valid_tree_identity(diff.get("base_tree_hash"), "diff.base_tree_hash")
    normalized["tree_hash"] = _valid_tree_identity(diff.get("tree_hash"), "diff.tree_hash")
    normalized["config_hash"] = _valid_hash(diff.get("config_hash"), "diff.config_hash")
    normalized["environment_hash"] = _valid_hash(diff.get("environment_hash"), "diff.environment_hash")
    task_scope = _paths(diff.get("task_scope"), "diff.task_scope")
    test_paths = _paths(diff.get("test_paths"), "diff.test_paths")
    raw_files = diff.get("files")
    if not isinstance(raw_files, list):
        _fail("diff.files must contain the actual base/head changes")
    files: list[dict[str, str]] = []
    for index, item in enumerate(raw_files):
        label = "diff.files[%d]" % index
        if not isinstance(item, dict) or item.get("status") not in _ALLOWED_STATUS:
            _fail("%s has an unsupported change status" % label)
        status = item["status"]
        if status == "renamed":
            old_path = _canonical_path(item.get("old_path"), label + ".old_path")
            new_path = _canonical_path(item.get("new_path"), label + ".new_path")
            if old_path == new_path:
                _fail("%s rename must change its path" % label)
            files.append({"status": status, "old_path": old_path, "new_path": new_path})
        else:
            path = _canonical_path(item.get("path"), label + ".path")
            files.append({"status": status, "path": path})
    files.sort(key=lambda item: (item.get("old_path", item.get("path", "")), item.get("new_path", ""), item["status"]))
    normalized["task_scope"] = task_scope
    normalized["test_paths"] = test_paths
    normalized["files"] = files
    return normalized, files, task_scope, test_paths


def _read_graph(graph: Any) -> tuple[dict[str, list[str]] | None, str | None]:
    if graph is None:
        return None, "dependency graph is missing"
    if not isinstance(graph, dict):
        _fail("graph must be an object or null")
    if graph.get("base_commit") is not None:
        _valid_commit(graph["base_commit"], "graph.base_commit")
    if graph.get("base_tree_hash") is not None:
        _valid_tree_identity(graph["base_tree_hash"], "graph.base_tree_hash")
    raw_edges = graph.get("reverse_edges")
    if not isinstance(raw_edges, dict):
        _fail("graph.reverse_edges must be an object")
    edges: dict[str, list[str]] = {}
    for source, targets in raw_edges.items():
        source_path = _canonical_path(source, "graph.reverse_edges key")
        if not isinstance(targets, list):
            _fail("graph.reverse_edges[%s] must be a list" % source_path)
        target_paths = [_canonical_path(target, "graph.reverse_edges target") for target in targets]
        if len(target_paths) != len(set(target_paths)):
            _fail("graph.reverse_edges[%s] contains duplicate targets" % source_path)
        edges[source_path] = sorted(target_paths)
    return edges, None


def _command(toolchain: Any, index: int) -> tuple[str, str, str | None, list[str], str, dict[str, str]]:
    label = "toolchains[%d]" % index
    if not isinstance(toolchain, dict):
        _fail("%s must be an object" % label)
    identifier = toolchain.get("id")
    language = toolchain.get("language")
    adapter = toolchain.get("red_adapter")
    if not isinstance(identifier, str) or not identifier.strip() or "\x00" in identifier:
        _fail("%s.id must be a nonempty string" % label)
    if not isinstance(language, str) or not language.strip():
        _fail("%s.language must be a nonempty string" % label)
    commands = toolchain.get("commands")
    test = commands.get("test") if isinstance(commands, dict) else None
    if not isinstance(test, dict):
        _fail("%s.commands.test must be an executable descriptor" % label)
    argv = test.get("argv")
    if not isinstance(argv, list) or not argv or not all(
        isinstance(part, str) and part and "\x00" not in part for part in argv
    ):
        _fail("%s.commands.test.argv must be a nonempty string array" % label)
    if any(part == "{test_paths}" for part in argv) and argv.count("{test_paths}") != 1:
        _fail("%s commands may include {test_paths} only once" % label)
    if any("{test_paths}" in part and part != "{test_paths}" for part in argv):
        _fail("%s uses an unsafe embedded path selector" % label)
    cwd = test.get("cwd", ".")
    if not isinstance(cwd, str) or not cwd or "\x00" in cwd:
        _fail("%s.commands.test.cwd must be a string" % label)
    env = test.get("env", test.get("environment", {}))
    if not isinstance(env, dict) or any(
        not isinstance(key, str) or not key or not isinstance(value, str)
        or "\x00" in key or "\x00" in value for key, value in env.items()
    ):
        _fail("%s.commands.test.env must map strings to strings" % label)
    return identifier, language.lower(), adapter if isinstance(adapter, str) else None, list(argv), cwd, dict(sorted(env.items()))


def _rule_for(language: str, policy: dict[str, Any]) -> dict[str, Any] | None:
    rules = policy.get("languages")
    if not isinstance(rules, dict):
        _fail("policy.languages must be an object")
    value = rules.get(language)
    return value if isinstance(value, dict) else None


def _fallback_glob_groups(policy: dict[str, Any], rule: dict[str, Any] | None = None) -> dict[str, list[str]]:
    globals_ = policy.get("fallback_globs", {})
    if not isinstance(globals_, dict):
        _fail("policy.fallback_globs must be an object")
    config_globs = list(_globs(globals_.get("configuration", []), "policy.fallback_globs.configuration"))
    if rule is not None:
        config_globs.extend(_globs(rule.get("configuration_globs", []), "language.configuration_globs"))
    return {
        "configuration": config_globs,
        "shared_infrastructure": _globs(globals_.get("shared_infrastructure", []), "policy.fallback_globs.shared_infrastructure"),
        "generated_contracts": _globs(globals_.get("generated_contracts", []), "policy.fallback_globs.generated_contracts"),
    }


def _full_suite_reason(changes: list[dict[str, str]], policy: dict[str, Any], rule: dict[str, Any]) -> str | None:
    groups = _fallback_glob_groups(policy, rule)
    for change in changes:
        paths = [change.get("old_path", change.get("path")), change.get("new_path")]
        paths = [path for path in paths if path]
        if any(_matches(path, groups["shared_infrastructure"]) for path in paths):
            return "changed shared infrastructure requires complete suite"
        if any(_matches(path, groups["generated_contracts"]) for path in paths):
            return "changed generated contract requires complete suite"
        if any(_matches(path, groups["configuration"]) for path in paths):
            return "changed dependency, build, or test configuration requires complete suite"
    return None


def _unclassified_changes(changed: list[tuple[str, str]], declared_tests: list[str],
                          descriptors: list[tuple[str, str, str | None, list[str], str, dict[str, str]]],
                          policy: dict[str, Any]) -> list[str]:
    """Find changed paths no configured toolchain rule can classify safely."""
    global_groups = _fallback_glob_groups(policy)
    unclassified: list[str] = []
    for path, _kind in changed:
        if any(_matches(path, patterns) for patterns in global_groups.values()):
            continue
        classified = False
        for identifier, language, adapter, _argv, _cwd, _env in descriptors:
            rule = _rule_for(language, policy)
            if rule is None or rule.get("supported") is not True or adapter not in rule.get("adapters", []):
                continue
            test_globs = _globs(rule.get("test_globs", []), "policy language %s test_globs" % language)
            source_globs = _globs(rule.get("source_globs", []), "policy language %s source_globs" % language)
            config_globs = _globs(rule.get("configuration_globs", []), "language.configuration_globs")
            extensions = rule.get("test_extensions", [])
            if not isinstance(extensions, list) or not all(
                isinstance(item, str) and item.startswith(".") and "/" not in item and "\\" not in item
                for item in extensions
            ):
                _fail("policy language %s has invalid test_extensions" % language)
            declared_for_language = path in declared_tests and any(path.endswith(ext) for ext in extensions)
            if (_matches(path, test_globs) or _matches(path, source_globs)
                    or _matches(path, config_globs) or declared_for_language):
                classified = True
                break
        if not classified:
            unclassified.append(path)
    return sorted(set(unclassified))


def _changed_paths(files: list[dict[str, str]]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for item in files:
        if item["status"] == "renamed":
            result.append((item["old_path"], "renamed source"))
            result.append((item["new_path"], "renamed target"))
        else:
            result.append((item["path"], item["status"] + " source"))
    return sorted(set(result))


def _reachable(start: str, edges: dict[str, list[str]]) -> tuple[set[str], list[str]]:
    visited = {start}
    queue = deque([start])
    order: list[str] = []
    while queue:
        current = queue.popleft()
        for target in edges.get(current, []):
            if target not in visited:
                visited.add(target)
                queue.append(target)
                order.append(target)
    return visited, order


def _route(start: str, target: str, edges: dict[str, list[str]]) -> list[str]:
    """Return one deterministic shortest dependency path for the explanation."""
    parents: dict[str, str | None] = {start: None}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        if current == target:
            break
        for node in edges.get(current, []):
            if node not in parents:
                parents[node] = current
                queue.append(node)
    if target not in parents:
        return [start, target]
    result: list[str] = []
    current: str | None = target
    while current is not None:
        result.append(current)
        current = parents[current]
    return list(reversed(result))


def _unittest_module(path: str) -> str:
    return path[:-3].replace("/", ".") if path.endswith(".py") else path.replace("/", ".")


def _affected_argv(argv: list[str], adapter: str, paths: list[str]) -> list[str]:
    selectors = [_unittest_module(path) for path in paths] if adapter == "unittest" else list(paths)
    if "{test_paths}" in argv:
        output: list[str] = []
        for part in argv:
            output.extend(selectors if part == "{test_paths}" else [part])
        return output
    if adapter == "unittest":
        try:
            marker = argv.index("discover")
            return argv[:marker] + selectors
        except ValueError:
            return argv + selectors
    return argv + selectors


def select(diff: dict, graph: dict, toolchains: list, policy: dict) -> dict:
    """Select impacted test paths and commands from base/head evidence.

    ``graph.reverse_edges`` points from a changed node to its direct consumers.
    Graph metadata must identify the exact diff base. Any missing/stale evidence
    broadens selection to each descriptor's complete test command.
    """
    normalized, files, task_scope, declared_tests = _read_diff(diff)
    edges, graph_error = _read_graph(graph)
    if not isinstance(policy, dict) or not isinstance(policy.get("version"), str) or not policy["version"]:
        _fail("policy.version is required")
    if not isinstance(toolchains, list) or not toolchains:
        _fail("toolchains must be a nonempty list")
    if edges is not None:
        if isinstance(graph.get("version"), bool) or graph.get("version") != 1:
            graph_error = "dependency graph version is missing or unsupported"
        elif ((graph.get("base_commit") or "").lower() != normalized["base_commit"]
              or (graph.get("base_tree_hash") or "").lower() != normalized["base_tree_hash"]):
            graph_error = "dependency graph is stale for the selected base commit/tree"

    parsed_toolchains = [
        (raw, _command(raw, index)) for index, raw in enumerate(toolchains)
    ]
    changed = _changed_paths(files)
    unclassified = _unclassified_changes(changed, declared_tests,
                                         [item[1] for item in parsed_toolchains], policy)
    commands: list[dict[str, Any]] = []
    details: list[dict[str, str]] = []
    selected_tests: set[str] = set()
    gaps: set[str] = set(unclassified)
    seen_ids: set[str] = set()
    toolchain_evidence: list[dict[str, Any]] = []

    for raw, descriptor in parsed_toolchains:
        identifier, language, adapter, full_argv, cwd, env = descriptor
        if identifier in seen_ids:
            _fail("duplicate toolchain id: %s" % identifier)
        seen_ids.add(identifier)
        toolchain_evidence.append({"id": identifier, "language": language, "red_adapter": adapter,
                                   "test": {"argv": full_argv, "cwd": cwd, "env": env}})
        rule = _rule_for(language, policy)
        full_reason = graph_error
        if rule is None:
            full_reason = "unsupported language %s has no tested impact adapter" % language
        elif rule.get("supported") is not True or adapter not in rule.get("adapters", []):
            full_reason = "unsupported adapter for %s; retain its complete suite" % language
        if full_reason is None and rule is not None:
            full_reason = _full_suite_reason(files, policy, rule)

        impacted: set[str] = set()
        local_gaps: set[str] = set()
        local_details: list[dict[str, str]] = []
        for path in unclassified:
            local_details.append({"toolchain_id": identifier, "path": path,
                                  "reason": "change is outside every configured toolchain source/test/configuration rule"})
        if unclassified and full_reason is None:
            full_reason = "unclassified changes require complete suite"
        if full_reason is None and rule is not None and edges is not None:
            test_globs = _globs(rule.get("test_globs", []), "policy language %s test_globs" % language)
            source_globs = _globs(rule.get("source_globs", []), "policy language %s source_globs" % language)
            test_extensions = rule.get("test_extensions", [])
            if not isinstance(test_extensions, list) or not all(
                isinstance(item, str) and item.startswith(".") and "/" not in item and "\\" not in item
                for item in test_extensions
            ):
                _fail("policy language %s has invalid test_extensions" % language)
            declared_for_language = {
                path for path in declared_tests
                if _matches(path, test_globs) or any(path.endswith(extension) for extension in test_extensions)
            }
            changed_test_deletions = {
                path for path, kind in changed
                if kind == "deleted source" and _matches(path, test_globs)
            }
            if changed_test_deletions:
                full_reason = "deleted test cannot be executed: " + ", ".join(sorted(changed_test_deletions))
            else:
                for path, kind in changed:
                    if path in declared_for_language:
                        impacted.add(path)
                        local_details.append({"toolchain_id": identifier, "path": path,
                                              "reason": "changed test selected directly (%s)" % kind})
                    if not _matches(path, source_globs) or _matches(path, test_globs):
                        continue
                    _, traversal = _reachable(path, edges)
                    reached_tests = sorted(node for node in traversal if (
                        _matches(node, test_globs) or node in declared_for_language
                    ))
                    usable = [node for node in reached_tests if node in declared_for_language]
                    impacted.update(usable)
                    for node in usable:
                        route = " -> ".join(_route(path, node, edges))
                        local_details.append({"toolchain_id": identifier, "path": node,
                                              "reason": "affected consumer through reverse dependency edges: " + route})
                    missing = [node for node in reached_tests if node not in declared_for_language]
                    if missing:
                        local_gaps.add(path)
                        local_details.append({"toolchain_id": identifier, "path": path,
                                              "reason": "dependency graph references tests missing from test_paths: " + ", ".join(missing)})
                    if not usable:
                        local_gaps.add(path)
                        local_details.append({"toolchain_id": identifier, "path": path,
                                              "reason": "production change has no test mapping"})
                if local_gaps:
                    full_reason = "impact graph has uncovered production changes; complete suite required"
            if full_reason is None and adapter == "unittest":
                invalid = sorted(path for path in impacted if any(
                    not segment.isidentifier() for segment in _unittest_module(path).split(".")
                ))
                if invalid:
                    full_reason = "invalid unittest module path cannot be selected safely: " + ", ".join(invalid)
        if full_reason is not None:
            local_details.append({"toolchain_id": identifier, "path": "", "reason": full_reason})
            commands.append({"toolchain_id": identifier, "language": language, "full_suite": True,
                             "tests": [], "argv": full_argv, "cwd": cwd, "env": env})
        else:
            selected = sorted(impacted)
            selected_tests.update(selected)
            commands.append({"toolchain_id": identifier, "language": language, "full_suite": False,
                             "tests": selected, "argv": _affected_argv(full_argv, adapter or "", selected),
                             "cwd": cwd, "env": env})
        details.extend(local_details)
        gaps.update(local_gaps)

    commands.sort(key=lambda item: item["toolchain_id"])
    details.sort(key=lambda item: (item["toolchain_id"], item["path"], item["reason"]))
    gaps_list = sorted(gaps)
    reasons = sorted({item["reason"] for item in details})
    modes = {item["full_suite"] for item in commands}
    mode = "mixed" if len(modes) > 1 else ("full_suite" if True in modes else "affected")
    identity = {
        "base_commit": normalized["base_commit"],
        "head_commit": normalized["head_commit"],
        "base_tree_hash": normalized["base_tree_hash"],
        "tree_hash": normalized["tree_hash"],
        "config_hash": normalized["config_hash"],
        "environment_hash": normalized["environment_hash"],
        "policy_version": policy["version"],
    }
    evidence = {
        "diff_hash": _digest_json(normalized),
        "graph_hash": _digest_json(None if graph is None else {
            "version": graph.get("version"),
            "base_commit": graph.get("base_commit").lower() if graph.get("base_commit") else None,
            "base_tree_hash": graph.get("base_tree_hash").lower() if graph.get("base_tree_hash") else None,
            "reverse_edges": edges,
            "provenance": graph.get("provenance"),
        }),
        "toolchains_hash": _digest_json(sorted(toolchain_evidence, key=lambda item: item["id"])),
        "policy_hash": _digest_json(policy),
    }
    result = {
        "schema_version": 1,
        "mode": mode,
        "scope_paths": task_scope,
        "tests": sorted(selected_tests),
        "commands": commands,
        "reasons": reasons,
        "reasons_detail": details,
        "gaps": gaps_list,
        "identity": identity,
        "evidence": evidence,
    }
    return {
        **result,
        "selection_hash": _digest_json(result),
    }
