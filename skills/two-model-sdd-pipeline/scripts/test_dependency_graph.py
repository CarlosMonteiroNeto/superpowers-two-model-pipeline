"""Build a complete, isolated AST import graph for R4 test selection.

Graphify is deliberately used as an extractor only. The gate supplies a fresh
snapshot; this module rejects stale output and never writes outside it.
"""

from __future__ import annotations

import configparser
import hashlib
import importlib.util
import json
import pathlib
import re
import subprocess
import sys
from typing import Any


SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
RULES_PATH = SCRIPT_DIR.parent / "toolchains" / "test-impact-rules.json"
_IMPORT_RELATIONS = {"imports", "imports_from"}
_CODE_SUFFIXES = {".py", ".dart"}
_PY_REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9_.-]+)")
_PACKAGE_URI = re.compile(r"^package:([A-Za-z0-9_]+)/(.+)$")


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _empty(version: str | None, diagnostics: list[str], inventory_hash: str = "") -> dict[str, Any]:
    return {
        "complete": False,
        "reverse_edges": {},
        "graphify_version": version,
        "graph_digest": "",
        "source_inventory_hash": inventory_hash,
        "diagnostics": sorted(set(diagnostics)),
    }


def _repo_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        return None
    path = pathlib.PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        return None
    return path.as_posix()


def _source_inventory(root: pathlib.Path) -> tuple[list[str], str]:
    paths: list[str] = []
    records: list[dict[str, str]] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _CODE_SUFFIXES:
            continue
        relative = path.relative_to(root).as_posix()
        if any(part.startswith(".") or part in {"graphify-out", "__pycache__", ".dart_tool", "build"}
               for part in pathlib.PurePosixPath(relative).parts):
            continue
        content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        paths.append(relative)
        records.append({"path": relative, "sha256": content_hash})
    paths.sort()
    records.sort(key=lambda item: item["path"])
    return paths, _digest(records)


def _yaml_unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _dart_manifests(root: pathlib.Path) -> tuple[dict[str, pathlib.Path], dict[pathlib.Path, set[str]], list[str]]:
    packages: dict[str, pathlib.Path] = {}
    external_by_root: dict[pathlib.Path, set[str]] = {}
    errors: list[str] = []
    for manifest in sorted(root.rglob("pubspec.yaml")):
        if any(part.startswith(".") or part in {"graphify-out", "build", ".dart_tool"}
               for part in manifest.relative_to(root).parts):
            continue
        package_name: str | None = None
        section: str | None = None
        dependencies: set[str] = set()
        try:
            lines = manifest.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            errors.append("cannot read Dart package manifest %s: %s" % (manifest.relative_to(root).as_posix(), exc))
            continue
        for line_no, line in enumerate(lines, 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if "\t" in line:
                errors.append("tab indentation in Dart package manifest %s:%d" % (manifest.relative_to(root).as_posix(), line_no))
                continue
            if not line.startswith(" "):
                match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s*(.*))?$", line)
                if not match:
                    errors.append("unsupported Dart package manifest syntax %s:%d" % (manifest.relative_to(root).as_posix(), line_no))
                    section = None
                    continue
                key, raw = match.group(1), (match.group(2) or "").strip()
                if key == "name":
                    name = _yaml_unquote(raw.split(" #", 1)[0])
                    if re.fullmatch(r"[A-Za-z0-9_]+", name):
                        package_name = name
                    else:
                        errors.append("invalid Dart package name in %s" % manifest.relative_to(root).as_posix())
                section = key if key in {"dependencies", "dev_dependencies", "dependency_overrides"} else None
                continue
            if section is None:
                continue
            if not line.startswith("  ") or line.startswith("   "):
                continue
            match = re.match(r"^  ([A-Za-z0-9_][A-Za-z0-9_-]*):(?:\s*(.*))?$", line)
            if not match:
                errors.append("unsupported dependency declaration %s:%d" % (manifest.relative_to(root).as_posix(), line_no))
                continue
            dependencies.add(match.group(1))
        package_root = manifest.parent.resolve()
        external_by_root[package_root] = dependencies
        if package_name is None:
            errors.append("Dart package manifest has no valid name: %s" % manifest.relative_to(root).as_posix())
        elif package_name in packages and packages[package_name] != package_root:
            errors.append("Dart package name is ambiguous: %s" % package_name)
        else:
            packages[package_name] = package_root
    return packages, external_by_root, errors


def _python_external_names(root: pathlib.Path) -> tuple[set[str], list[str]]:
    names: set[str] = set()
    errors: list[str] = []
    manifests = sorted(set(root.rglob("pyproject.toml")) | set(root.rglob("requirements*.txt"))
                       | set(root.rglob("setup.cfg")) | set(root.rglob("Pipfile")))
    for manifest in manifests:
        rel = manifest.relative_to(root)
        if any(part.startswith(".") or part in {"graphify-out", "build", "dist", ".venv", "venv"}
               for part in rel.parts):
            continue
        try:
            text = manifest.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append("cannot read Python dependency manifest %s: %s" % (rel.as_posix(), exc))
            continue
        if manifest.name == "pyproject.toml":
            try:
                import tomllib
                data = tomllib.loads(text)
            except (ImportError, ValueError) as exc:
                errors.append("cannot safely parse pyproject.toml %s: %s" % (rel.as_posix(), exc))
                continue
            project = data.get("project", {})
            values: list[Any] = project.get("dependencies", []) if isinstance(project, dict) else []
            optional = project.get("optional-dependencies", {}) if isinstance(project, dict) else {}
            if isinstance(optional, dict):
                values.extend(item for group in optional.values() if isinstance(group, list) for item in group)
            poetry = data.get("tool", {}).get("poetry", {}) if isinstance(data.get("tool"), dict) else {}
            poetry_deps = poetry.get("dependencies", {}) if isinstance(poetry, dict) else {}
            if isinstance(poetry_deps, dict):
                values.extend(poetry_deps.keys())
            for value in values:
                if isinstance(value, str):
                    match = _PY_REQUIREMENT.match(value)
                    if match:
                        names.add(match.group(1).lower().replace("-", "_").replace(".", "_"))
        elif manifest.name.startswith("requirements"):
            for line_no, line in enumerate(text.splitlines(), 1):
                value = line.split(";", 1)[0].strip()
                if not value or value.startswith("#"):
                    continue
                if value.startswith(("-r ", "--requirement ")):
                    include = value.split(None, 1)[1].strip()
                    include_path = (manifest.parent / include).resolve()
                    if not include_path.is_relative_to(root.resolve()) or not include_path.is_file():
                        errors.append("unsafe or missing requirements include %s:%d" % (rel.as_posix(), line_no))
                    else:
                        try:
                            nested = include_path.read_text(encoding="utf-8")
                        except (OSError, UnicodeError):
                            errors.append("cannot read requirements include %s" % include_path.relative_to(root).as_posix())
                            continue
                        for nested_line in nested.splitlines():
                            match = _PY_REQUIREMENT.match(nested_line.split(";", 1)[0])
                            if match and not nested_line.lstrip().startswith("#"):
                                names.add(match.group(1).lower().replace("-", "_").replace(".", "_"))
                    continue
                if value.startswith("-"):
                    errors.append("unsupported requirements option %s:%d" % (rel.as_posix(), line_no))
                    continue
                match = _PY_REQUIREMENT.match(value)
                if match:
                    names.add(match.group(1).lower().replace("-", "_").replace(".", "_"))
        elif manifest.name == "setup.cfg":
            parser = configparser.ConfigParser()
            try:
                parser.read_string(text)
                raw = parser.get("options", "install_requires", fallback="")
                values = raw.splitlines()
                for value in values:
                    match = _PY_REQUIREMENT.match(value)
                    if match:
                        names.add(match.group(1).lower().replace("-", "_").replace(".", "_"))
            except configparser.Error as exc:
                errors.append("cannot safely parse setup.cfg %s: %s" % (rel.as_posix(), exc))
        else:
            try:
                import tomllib
                data = tomllib.loads(text)
            except (ImportError, ValueError) as exc:
                errors.append("cannot safely parse Pipfile %s: %s" % (rel.as_posix(), exc))
                continue
            for section in ("packages", "dev-packages"):
                values = data.get(section, {})
                if isinstance(values, dict):
                    names.update(str(name).lower().replace("-", "_").replace(".", "_") for name in values)
    return names, errors


def _python_modules(paths: list[str]) -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
    for path in paths:
        if not path.endswith(".py"):
            continue
        parts = list(pathlib.PurePosixPath(path).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        if not parts:
            continue
        forms = {".".join(parts), "_".join(parts), parts[-1]}
        for name in forms:
            aliases.setdefault(name, set()).add(path)
    return aliases


def _inside_inventory(root: pathlib.Path, value: str, inventory: set[str]) -> str | None:
    rel = _repo_path(value)
    if rel is None or rel not in inventory:
        return None
    path = (root / pathlib.PurePosixPath(rel)).resolve()
    if not path.is_relative_to(root.resolve()):
        return None
    return rel


def _nearest(root: pathlib.Path, relative: str, manifests: dict[pathlib.Path, set[str]]) -> pathlib.Path | None:
    source = (root / pathlib.PurePosixPath(relative)).resolve()
    parents = [source.parent, *source.parent.parents]
    return next((parent for parent in parents if parent in manifests), None)


def _resolve_python(target: str, target_node: dict[str, Any] | None, root: pathlib.Path,
                    inventory: set[str], modules: dict[str, set[str]], external: set[str]) -> tuple[str | None, bool]:
    if target_node is not None and target_node.get("source_file"):
        path = _inside_inventory(root, target_node.get("source_file"), inventory)
        return path, path is None
    candidate_names = [target]
    if target_node and isinstance(target_node.get("label"), str):
        candidate_names.insert(0, target_node["label"])
    for name in candidate_names:
        clean = name.removesuffix(".py")
        paths = modules.get(clean, set())
        if len(paths) == 1:
            return next(iter(paths)), False
        if len(paths) > 1:
            return None, True
    top = target.split(".", 1)[0].lower().replace("-", "_").replace(".", "_")
    stdlib = getattr(sys, "stdlib_module_names", frozenset())
    if top in stdlib or top in external:
        return None, False
    return None, True


def _resolve_dart(target: str, target_node: dict[str, Any] | None, source_file: str,
                  root: pathlib.Path, inventory: set[str], packages: dict[str, pathlib.Path],
                  external_by_root: dict[pathlib.Path, set[str]]) -> tuple[str | None, bool]:
    if target_node is not None and target_node.get("source_file"):
        path = _inside_inventory(root, target_node.get("source_file"), inventory)
        return path, path is None
    label = target_node.get("label") if target_node and isinstance(target_node.get("label"), str) else target
    uri = _PACKAGE_URI.fullmatch(label)
    if uri:
        package, suffix = uri.groups()
        if any(part in {"", ".", ".."} for part in pathlib.PurePosixPath(suffix).parts):
            return None, True
        package_root = packages.get(package)
        if package_root is not None:
            relative_root = package_root.relative_to(root.resolve()).as_posix()
            path = (pathlib.PurePosixPath(relative_root) / "lib" / suffix).as_posix()
            resolved = _inside_inventory(root, path, inventory)
            return resolved, resolved is None
        owner = _nearest(root, source_file, external_by_root)
        if owner is not None and package in external_by_root[owner]:
            return None, False
        return None, True
    source_parent = pathlib.PurePosixPath(source_file).parent
    candidate = pathlib.PurePosixPath(label)
    if candidate.is_absolute() or "\\" in label:
        return None, True
    normalized = pathlib.PurePosixPath(source_parent, candidate)
    stack: list[str] = []
    for part in normalized.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not stack:
                return None, True
            stack.pop()
        else:
            stack.append(part)
    relative = "/".join(stack)
    resolved = _inside_inventory(root, relative, inventory)
    return resolved, resolved is None


def _read_graphify_graph(root: pathlib.Path, output_root: pathlib.Path) -> dict[str, Any]:
    graph_path = output_root / "graphify-out" / "graph.json"
    resolved_root = root.resolve()
    if (not output_root.resolve().is_relative_to(resolved_root)
            or not graph_path.resolve().is_relative_to(output_root.resolve())):
        raise ValueError("Graphify output path escapes the disposable snapshot")
    return json.loads(graph_path.read_text(encoding="utf-8"))


def build(snapshot: pathlib.Path, expected_version: str) -> dict[str, Any]:
    """Return trusted reverse import edges, or incomplete evidence with no edges."""
    diagnostics: list[str] = []
    observed_version: str | None = None
    try:
        root = pathlib.Path(snapshot).resolve(strict=True)
        if not root.is_dir():
            return _empty(None, ["source snapshot is not a directory"])
        output_root = root / ".r4-graphify-output"
        if output_root.exists():
            return _empty(None, ["snapshot already contains Graphify output; refusing stale graph"])
        policy = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        graphify_policy = policy.get("graphify", {})
        allowed = graphify_policy.get("version_allowlist", [])
        if not isinstance(expected_version, str) or expected_version not in allowed:
            return _empty(None, ["requested Graphify version is not allowlisted"])
        if (graphify_policy.get("schema_version") != 1
                or graphify_policy.get("command") != "extract"
                or graphify_policy.get("code_only") is not True
                or graphify_policy.get("no_cluster") is not True
                or graphify_policy.get("raw_edges_key") != "edges"
                or graphify_policy.get("node_origin") != "ast"
                or graphify_policy.get("accepted_relations") != ["imports", "imports_from"]
                or graphify_policy.get("require_edge_source_file_match") is not True):
            return _empty(None, ["Graphify policy schema is missing or unsupported"])
        version_result = subprocess.run(
            ["graphify", "--version"], cwd=str(root), shell=False,
            capture_output=True, text=True, timeout=30,
        )
        match = re.search(r"\bgraphify\s+(\d+\.\d+\.\d+)\b", version_result.stdout or "", re.IGNORECASE)
        if version_result.returncode != 0 or match is None:
            return _empty(None, ["Graphify version command failed or returned an unsupported value"])
        observed_version = match.group(1)
        if observed_version != expected_version:
            return _empty(observed_version, ["installed Graphify version does not match the allowlisted version"])
        inventory_paths, inventory_hash = _source_inventory(root)
        if not inventory_paths:
            return _empty(observed_version, ["snapshot has no supported Python or Dart source files"], inventory_hash)
        output_root.mkdir()
        extract = subprocess.run(
            ["graphify", "extract", str(root), "--code-only", "--no-cluster", "--out", str(output_root)],
            cwd=str(root), shell=False,
            capture_output=True, text=True, timeout=600,
        )
        if extract.returncode != 0:
            return _empty(observed_version, ["Graphify AST extraction failed: " + (extract.stderr or "nonzero exit")], inventory_hash)
        graph = _read_graphify_graph(root, output_root)
        graph_digest = _digest(graph)
        raw_edges_key = graphify_policy["raw_edges_key"]
        failed_sources = graph.get("failed_sources") if isinstance(graph, dict) else None
        if (not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list)
                or not isinstance(graph.get(raw_edges_key), list)
                or not isinstance(graph.get("hyperedges"), list)
                or (failed_sources is not None and not isinstance(failed_sources, list))):
            return _empty(observed_version, ["Graphify graph schema is unsupported"], inventory_hash)
        if failed_sources:
            return _empty(observed_version, ["Graphify reported failed sources"], inventory_hash)
        inventory = set(inventory_paths)
        source_nodes: dict[str, dict[str, Any]] = {}
        for node in graph["nodes"]:
            if not isinstance(node, dict) or not isinstance(node.get("id"), str):
                return _empty(observed_version, ["Graphify graph contains a malformed node"], inventory_hash)
            source_file = node.get("source_file")
            if source_file is None:
                continue
            raw_source_path = _repo_path(source_file)
            if (node.get("type") == "package" and raw_source_path is not None
                    and pathlib.PurePosixPath(raw_source_path).name in {"pyproject.toml", "pubspec.yaml"}
                    and (root / pathlib.PurePosixPath(raw_source_path)).is_file()
                    and node.get("_origin") == graphify_policy["node_origin"]):
                # Graphify indexes package manifests as code nodes; they are
                # metadata, not missing Python/Dart source inventory entries.
                continue
            normalized = _inside_inventory(root, source_file, inventory)
            if normalized is None or node.get("_origin") != graphify_policy["node_origin"]:
                return _empty(observed_version, ["Graphify source node is outside the complete AST inventory"], inventory_hash)
            if normalized in source_nodes:
                # Multiple AST entities in one file are valid; keep the module node below.
                if node.get("label") == pathlib.PurePosixPath(normalized).name:
                    source_nodes[normalized] = node
            else:
                source_nodes[normalized] = node
        if set(source_nodes) != inventory:
            missing = sorted(inventory - set(source_nodes))
            return _empty(observed_version, ["Graphify omitted supported source files: " + ", ".join(missing[:10])], inventory_hash)
        nodes_by_id = {node["id"]: node for node in graph["nodes"]}
        if len(nodes_by_id) != len(graph["nodes"]):
            return _empty(observed_version, ["Graphify graph contains duplicate node ids"], inventory_hash)
        py_modules = _python_modules(inventory_paths)
        py_external, py_errors = _python_external_names(root)
        packages, dart_external, dart_errors = _dart_manifests(root)
        diagnostics.extend(py_errors)
        diagnostics.extend(dart_errors)
        if diagnostics:
            return _empty(observed_version, diagnostics, inventory_hash)
        reverse: dict[str, set[str]] = {}
        for edge in graph[raw_edges_key]:
            if not isinstance(edge, dict):
                return _empty(observed_version, ["Graphify graph contains a malformed edge"], inventory_hash)
            relation = edge.get("relation")
            if relation == "dynamic_import":
                return _empty(observed_version, ["Graphify found a dynamic import"], inventory_hash)
            if relation not in graphify_policy.get("accepted_relations", []):
                continue
            if edge.get("_origin") != graphify_policy["node_origin"]:
                return _empty(observed_version, ["Graphify import edge is not AST-origin"], inventory_hash)
            source_file = _inside_inventory(root, edge.get("source_file"), inventory)
            if source_file is None:
                return _empty(observed_version, ["Graphify import edge has no valid source file"], inventory_hash)
            source_id = edge.get("source")
            source_node = nodes_by_id.get(source_id) if isinstance(source_id, str) else None
            source_node_file = (_inside_inventory(root, source_node.get("source_file"), inventory)
                                if source_node is not None else None)
            if (source_node is None or source_node.get("_origin") != graphify_policy["node_origin"]
                    or source_node_file != source_file):
                return _empty(observed_version, ["Graphify import source node does not match source_file"], inventory_hash)
            target_id = edge.get("target")
            if not isinstance(target_id, str):
                return _empty(observed_version, ["Graphify import edge has no valid target"], inventory_hash)
            target_node = nodes_by_id.get(target_id)
            if source_file.endswith(".py"):
                target_path, unresolved = _resolve_python(target_id, target_node, root, inventory, py_modules, py_external)
            elif source_file.endswith(".dart"):
                target_path, unresolved = _resolve_dart(target_id, target_node, source_file, root, inventory, packages, dart_external)
            else:
                return _empty(observed_version, ["Graphify import edge uses an unsupported source language"], inventory_hash)
            if unresolved:
                target_label = target_node.get("label") if target_node and isinstance(target_node.get("label"), str) else target_id
                return _empty(observed_version, ["unresolved or ambiguous import target: " + target_label], inventory_hash)
            if target_path is not None:
                reverse.setdefault(target_path, set()).add(source_file)
        return {
            "complete": True,
            "reverse_edges": {key: sorted(values) for key, values in sorted(reverse.items())},
            "graphify_version": observed_version,
            "graph_digest": graph_digest,
            "source_inventory_hash": inventory_hash,
            "diagnostics": [],
        }
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        diagnostics.append("Graphify dependency evidence unavailable: " + str(exc))
        return _empty(observed_version, diagnostics)
