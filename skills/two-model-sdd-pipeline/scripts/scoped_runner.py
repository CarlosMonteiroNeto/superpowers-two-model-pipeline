"""Execute only task-declared toolchain commands through the shared cmd gate."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from red_evidence import classify_raw
from toolchain_contract import ADAPTER_LANGUAGES, resolve_toolchain
import scope_grants


SCRIPT_DIR = Path(__file__).resolve().parent
MODES = {"red", "test", "analyze", "format"}
INFRASTRUCTURE_EXIT = 3


class RunnerError(ValueError):
    """The requested scoped command cannot be safely resolved."""


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                         encoding="utf-8")
    os.replace(temporary, path)


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RunnerError("cannot read %s: %s" % (label, exc)) from exc
    if not isinstance(value, dict):
        raise RunnerError("%s must contain a JSON object" % label)
    return value


def _find_task(plan: dict[str, Any], task_id: str) -> dict[str, Any]:
    matches = [task for task in plan.get("tasks", [])
               if isinstance(task, dict) and str(task.get("id")) == task_id]
    if len(matches) != 1:
        raise RunnerError("task %s is missing or ambiguous in plan" % task_id)
    return matches[0]


def _validate_path_syntax(raw: str) -> PurePosixPath:
    if not raw or "\x00" in raw or "\\" in raw:
        raise RunnerError("test path is not canonical: %s" % raw)
    win = PureWindowsPath(raw)
    path = PurePosixPath(raw)
    if path.is_absolute() or win.is_absolute() or win.drive:
        raise RunnerError("test path must be relative to the project root: %s" % raw)
    if any(part in ("", ".", "..") for part in raw.split("/")):
        raise RunnerError("test path escapes or is not canonical: %s" % raw)
    if path.as_posix() != raw:
        raise RunnerError("test path is not canonical: %s" % raw)
    return path


def _validated_test_paths(raw_paths: list[str], project_root: Path | None = None) -> list[str]:
    paths = []
    for raw in raw_paths:
        rel = _validate_path_syntax(raw)
        if project_root is not None:
            root = project_root.resolve()
            target = (root / Path(*rel.parts)).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise RunnerError("test path escapes the project root: %s" % raw) from exc
            if not target.is_file():
                raise RunnerError("test path is not an existing file in the project root: %s" % raw)
        paths.append(rel.as_posix())
    return paths


def _read_gate(workspace: Path, toolchain_id: str) -> dict[str, Any]:
    ledger = workspace / "ledger.jsonl"
    try:
        lines = ledger.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RunnerError("cannot read toolchain ledger: %s" % exc) from exc
    matches = []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("type") == "gate" and entry.get("toolchain_id") == toolchain_id:
            matches.append(entry)
    if len(matches) != 1:
        reason = "missing" if not matches else "ambiguous"
        raise RunnerError("%s exact gate record for toolchain_id %s" % (reason, toolchain_id))
    descriptor = matches[0].get("toolchain_descriptor")
    if isinstance(descriptor, str):
        try:
            descriptor = json.loads(descriptor)
        except ValueError as exc:
            raise RunnerError("toolchain descriptor is malformed JSON") from exc
    if not isinstance(descriptor, dict):
        raise RunnerError("exact gate record has no executable toolchain descriptor")
    return descriptor


def _project_root(task: dict[str, Any], plan: dict[str, Any], descriptor: dict[str, Any]) -> Path:
    current = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True)
    if current.returncode == 0 and current.stdout.strip():
        checkout = Path(current.stdout.strip()).resolve()
        # Gate descriptors are resolved before worktrees are allocated. Map
        # their repository-relative project root into the worker's checkout.
        candidates = (
            os.environ.get("PIPELINE_PROJECT_ROOT"), descriptor.get("project_root"),
            task.get("project_root"), plan.get("project_root"), plan.get("repository_root"),
        )
        for candidate in candidates:
            if not candidate:
                continue
            configured = Path(str(candidate)).resolve()
            source = subprocess.run(["git", "-C", str(configured), "rev-parse", "--show-toplevel"],
                                    capture_output=True, text=True)
            if source.returncode != 0 or not source.stdout.strip():
                continue
            source_root = Path(source.stdout.strip()).resolve()
            try:
                relative = configured.relative_to(source_root)
            except ValueError:
                continue
            mapped = (checkout / relative).resolve()
            if mapped.is_dir():
                return mapped
        return checkout

    candidates = (
        descriptor.get("project_root"), task.get("project_root"),
        plan.get("project_root"), plan.get("repository_root"),
        os.environ.get("PIPELINE_PROJECT_ROOT"),
    )
    for candidate in candidates:
        if candidate:
            root = Path(str(candidate)).resolve()
            if root.is_dir():
                return root
    result = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                            capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        root = Path(result.stdout.strip()).resolve()
        if root.is_dir():
            return root
    raise RunnerError("cannot resolve the task project root")


def _relocate_descriptor(descriptor: dict[str, Any], project_root: Path) -> dict[str, Any]:
    """Rebase pre-worktree absolute command cwd values into this checkout."""
    relocated = copy.deepcopy(descriptor)
    source_value = descriptor.get("project_root")
    if not source_value:
        relocated["project_root"] = str(project_root)
        return relocated
    source_root = Path(str(source_value)).resolve()
    commands = relocated.get("commands")
    if isinstance(commands, dict):
        for command in commands.values():
            if not isinstance(command, dict):
                continue
            cwd = command.get("cwd")
            if not isinstance(cwd, str) or not cwd:
                continue
            configured = Path(cwd)
            if not configured.is_absolute():
                continue
            try:
                relative = configured.resolve().relative_to(source_root)
            except ValueError:
                continue
            command["cwd"] = relative.as_posix() if relative.parts else "."
    relocated["project_root"] = str(project_root)
    return relocated


def _source_snapshot(root: Path) -> str:
    revision = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
                              capture_output=True, text=True)
    if revision.returncode == 0:
        digest = hashlib.sha256()
        diff = subprocess.run(["git", "-C", str(root), "diff", "--binary", "HEAD"],
                              capture_output=True)
        if diff.returncode != 0:
            raise RunnerError("cannot capture tracked source snapshot")
        digest.update(diff.stdout)
        untracked = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"],
            capture_output=True, text=True,
        )
        if untracked.returncode != 0:
            raise RunnerError("cannot capture untracked source snapshot")
        for name in sorted(item for item in untracked.stdout.splitlines() if item):
            path = (root / name).resolve()
            try:
                path.relative_to(root.resolve())
                payload = path.read_bytes()
            except (ValueError, OSError) as exc:
                raise RunnerError("cannot include untracked source path %s: %s" % (name, exc)) from exc
            digest.update(name.replace("\\", "/").encode("utf-8"))
            digest.update(b"\x00")
            digest.update(payload)
        return "commit:%s+sha256:%s" % (revision.stdout.strip(), digest.hexdigest())
    digest = hashlib.sha256()
    ignored = {".git", ".venv", "venv", "node_modules", "build", ".dart_tool", "__pycache__"}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in ignored for part in path.relative_to(root).parts):
            continue
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(path.read_bytes())
    return "tree:sha256:%s" % digest.hexdigest()


def _module_name(path: str) -> str:
    value = path[:-3] if path.endswith(".py") else path
    return value.replace("/", ".")


def _expand_argv(command: dict[str, Any], adapter: str, mode: str,
                 test_paths: list[str], evidence_path: Path) -> list[str]:
    original = list(command["argv"])
    effective_paths = list(test_paths)
    if adapter == "go_test_json" and mode == "red" and not effective_paths:
        effective_paths = ["./..."]
    if adapter == "unittest" and mode in ("red", "test") and test_paths:
        try:
            module_index = original.index("-m")
        except ValueError:
            raise RunnerError("unittest adapter requires a configured Python -m unittest command")
        if original[module_index + 1:module_index + 2] != ["unittest"]:
            raise RunnerError("unittest adapter requires a configured Python -m unittest command")
        prefix = original[:module_index + 2]
        # A suite-wide discover target cannot be combined safely with explicit
        # file paths; replace it with the exact module names requested.
        rest = original[module_index + 2:]
        if rest and rest[0] == "discover":
            rest = []
        argv = prefix + [_module_name(path) for path in test_paths]
        if mode == "red":
            argv.append("-v")
    else:
        expanded = []
        for part in original:
            if part == "{test_paths}":
                expanded.extend(effective_paths)
            elif "{evidence_path}" in part:
                expanded.append(part.replace("{evidence_path}", str(evidence_path)))
            else:
                expanded.append(part)
        argv = expanded
        if test_paths and not any(part == "{test_paths}" for part in original):
            argv.extend(test_paths)
        if adapter == "unittest" and mode == "red" and "-v" not in argv and "--verbose" not in argv:
            argv.append("-v")
    return argv


def _parse_unittest(text: str) -> tuple[int, list[str], list[str], list[str]]:
    tests_run = 0
    summary = re.search(r"^Ran\s+(\d+)\s+tests?\s+in\s+[^\r\n]+", text, re.MULTILINE)
    if summary:
        tests_run = int(summary.group(1))
    executed: list[str] = []
    failures: list[str] = []
    errors: list[str] = []
    for match in re.finditer(r"^(.+?)\s+\.\.\.\s+(ok|FAIL|ERROR|skipped|expected failure|unexpected success)\b",
                            text, re.MULTILINE | re.IGNORECASE):
        test_id = match.group(1).strip()
        # Ignore unittest loader placeholders: no test body actually ran.
        if "_FailedTest" in test_id:
            continue
        executed.append(test_id)
        outcome = match.group(2).lower()
        if outcome == "fail":
            failures.append(test_id)
        elif outcome == "error":
            errors.append(test_id)
    for match in re.finditer(r"^(FAIL|ERROR):\s*(.+?)\s*$", text, re.MULTILINE):
        target = match.group(2).strip()
        if "_FailedTest" in target:
            continue
        (failures if match.group(1) == "FAIL" else errors).append(target)
        if target not in executed:
            executed.append(target)
    return tests_run, sorted(set(executed)), sorted(set(failures)), sorted(set(errors))


def _write_attempt(workspace: Path, task_id: str, identity: dict[str, Any]) -> None:
    _atomic_json(workspace / ("task-%s-attempt.json" % task_id), identity)


def _command_output_argument(full_output: Path, command_cwd: str) -> str:
    output = full_output.resolve()
    cwd = Path(command_cwd).resolve()
    try:
        return output.relative_to(cwd).as_posix()
    except ValueError:
        return str(full_output)


def _run(argv: list[str], command: dict[str, Any], full_output: Path) -> int:
    bash = os.environ.get("BASH_BIN") or shutil.which("bash")
    if not bash:
        raise RunnerError("Bash is required to invoke the shared cmd output runner")
    env = dict(os.environ)
    env.update(command.get("env", command.get("environment", {})))
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd_script = SCRIPT_DIR / "cmd"
    process = subprocess.run(
        [bash, str(cmd_script), "--full-file",
         _command_output_argument(full_output, command["cwd"]), "--", *argv],
        cwd=command["cwd"], env=env,
    )
    return process.returncode


_CAPABILITY_REQUEST_KEYS = {"mode", "toolchain_id", "paths", "selector"}
_CAPABILITY_FORBIDDEN_KEYS = {"command", "argv", "shell", "flags", "cwd",
                              "env", "environment"}
_CAPABILITY_ADAPTERS = {"unittest"}
_TEST_CASE = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)+$")
_SHELL_METACHARS = set(";|&<>`$(){}[]!'\"*?~#")


def _capability_scope(policy: dict[str, Any]) -> dict[str, Any]:
    scope = policy.get("scope")
    if not isinstance(scope, dict):
        return {"mode": "legacy", "roots": [], "exact_paths": []}
    roots = scope.get("roots", [])
    exact = scope.get("exact_paths", [])
    if scope.get("mode") != "areas" or not isinstance(roots, list):
        return {"mode": "legacy", "roots": [], "exact_paths": []}
    return {"mode": "areas",
            "roots": [item for item in roots if isinstance(item, str) and item],
            "exact_paths": [item for item in exact
                            if isinstance(item, str) and item]}


def _in_scope_roots(roots: list, rel: str) -> bool:
    folded = os.path.normcase(rel.replace("/", os.sep))
    for root in roots:
        if not isinstance(root, str) or not root:
            continue
        if root == ".":
            return True
        folded_root = os.path.normcase(root.replace("/", os.sep))
        if folded == folded_root or folded.startswith(folded_root + os.sep):
            return True
    return False


def _capability_paths(request: dict[str, Any], policy: dict[str, Any],
                      project_root: Path) -> list[str]:
    raw_paths = request.get("paths", [])
    if not isinstance(raw_paths, list) or not all(
            isinstance(item, str) for item in raw_paths):
        raise RunnerError("capability request paths must be a string list")
    selector = request.get("selector")
    if selector is not None:
        if not isinstance(selector, dict):
            raise RunnerError("capability selector must be an object")
        kind = selector.get("kind")
        if kind == "file":
            value = selector.get("value")
            if not isinstance(value, str):
                raise RunnerError("file selector needs a string path")
            raw_paths = list(raw_paths) + [value]
        elif kind != "test_case":
            raise RunnerError("unsupported capability selector: %r" % (kind,))
    checked = []
    for raw in raw_paths:
        if any(char in _SHELL_METACHARS for char in raw):
            raise RunnerError(
                "capability path carries shell syntax: %s" % raw)
        rel = _validate_path_syntax(raw)
        checked.append(rel.as_posix())
    scope = _capability_scope(policy)
    if scope["mode"] == "areas":
        roots = scope["roots"]
        for rel in checked:
            if not _in_scope_roots(roots, rel):
                raise RunnerError(
                    "capability path is outside the reserved areas: %s" % rel)
    protected = policy.get("protected_paths", [])
    if not isinstance(protected, list):
        raise RunnerError("capability policy protected paths are invalid")
    for rel in checked:
        if rel in protected or any(
                rel == item or rel.startswith(str(item).rstrip("/") + "/")
                for item in protected if isinstance(item, str)):
            raise RunnerError(
                "capability path is protected: %s" % rel)
        if scope_grants.is_protected(rel):
            raise RunnerError(
                "capability path is protected: %s" % rel)
    resolved_root = project_root.resolve()
    for rel in checked:
        target = (resolved_root / Path(*PurePosixPath(rel).parts))
        try:
            target.resolve().relative_to(resolved_root)
        except (ValueError, OSError) as exc:
            raise RunnerError(
                "capability path escapes the project root: %s" % rel) from exc
        if not target.is_file():
            raise RunnerError(
                "capability path is not an existing file: %s" % rel)
    return checked


def resolve_capability(request: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """Resolve a worker check request to trusted execution inputs.

    The worker describes WHAT (mode, toolchain, paths, an optional
    adapter-supported selector); only configured toolchain commands become
    argv. Worker-supplied command strings, flags, and shell syntax are
    rejected. Returns argv, cwd, an evidence destination, and identity.
    Nothing is executed.
    """
    if not isinstance(request, dict) or not isinstance(policy, dict):
        raise RunnerError("capability request and policy must be objects")
    forbidden = sorted(set(request) & _CAPABILITY_FORBIDDEN_KEYS)
    if forbidden:
        raise RunnerError(
            "capability request must not carry commands: %s"
            % ",".join(forbidden))
    mode = request.get("mode")
    if mode not in MODES:
        raise RunnerError("unsupported capability mode: %r" % (mode,))
    toolchain_id = request.get("toolchain_id")
    if not isinstance(toolchain_id, str) or not toolchain_id.strip():
        raise RunnerError("capability toolchain_id is required")
    toolchains = policy.get("toolchains")
    if not isinstance(toolchains, dict) or toolchain_id not in toolchains:
        raise RunnerError(
            "capability toolchain is not configured: %s" % toolchain_id)
    toolchain = toolchains[toolchain_id]
    if not isinstance(toolchain, dict):
        raise RunnerError("capability toolchain descriptor is invalid")
    adapter = toolchain.get("adapter")
    if adapter not in _CAPABILITY_ADAPTERS:
        raise RunnerError(
            "unsupported capability adapter: %r" % (adapter,))
    commands = toolchain.get("commands")
    if not isinstance(commands, dict) or mode not in commands:
        raise RunnerError(
            "toolchain %s has no configured %s command"
            % (toolchain_id, mode))
    command = commands[mode]
    if (not isinstance(command, dict) or not isinstance(command.get("argv"), list)
            or not command["argv"]
            or not all(isinstance(part, str) and part for part in command["argv"])):
        raise RunnerError("capability command descriptor is invalid")
    project_root = policy.get("project_root")
    if not project_root or not Path(str(project_root)).is_dir():
        raise RunnerError("capability policy project root is invalid")
    root = Path(str(project_root)).resolve()
    evidence_dir = policy.get("evidence_dir")
    if not evidence_dir:
        raise RunnerError("capability policy evidence directory is invalid")
    if mode in ("analyze", "format") and (request.get("paths") or request.get("selector")):
        raise RunnerError(
            "unexpected test path argument for %s mode" % mode)
    paths = _capability_paths(request, policy, root)
    evidence_path = Path(str(evidence_dir)) / ("%s-%s.txt" % (toolchain_id, mode))
    report_path = evidence_path.with_suffix(".report.json")
    argv = _expand_argv(command, adapter, mode, paths, report_path)
    selector = request.get("selector")
    if isinstance(selector, dict) and selector.get("kind") == "test_case":
        dotted = selector.get("value")
        if not isinstance(dotted, str) or not _TEST_CASE.match(dotted):
            raise RunnerError("capability test case selector is invalid")
        argv = list(argv) + [dotted]
        if mode == "red" and "-v" not in argv and "--verbose" not in argv:
            argv.append("-v")
    cwd_value = command.get("cwd") or "."
    cwd = (root / str(cwd_value)).resolve() if not os.path.isabs(str(cwd_value)) else Path(str(cwd_value)).resolve()
    try:
        cwd.relative_to(root)
    except ValueError as exc:
        raise RunnerError("capability command cwd escapes the project root") from exc
    if not cwd.is_dir():
        raise RunnerError("capability command cwd is not a directory")
    scope = _capability_scope(policy)
    return {
        "argv": argv,
        "cwd": str(cwd),
        "evidence_path": str(evidence_path),
        "identity": {"toolchain_id": toolchain_id, "mode": mode,
                     "adapter": adapter,
                     "scope": scope["roots"] if scope["mode"] == "areas" else "legacy"},
    }


def describe_capabilities(policy: dict[str, Any]) -> str:
    """Render the enforced local capabilities for prompts and briefs."""
    if not isinstance(policy, dict):
        raise RunnerError("capability policy must be an object")
    lines = ["Supported local checks (no worker command strings):",
             "modes: %s." % ", ".join(sorted(MODES))]
    toolchains = policy.get("toolchains")
    if isinstance(toolchains, dict):
        for toolchain_id in sorted(toolchains):
            toolchain = toolchains[toolchain_id]
            adapter = toolchain.get("adapter") if isinstance(toolchain, dict) else None
            commands = toolchain.get("commands") if isinstance(toolchain, dict) else None
            modes = sorted(commands) if isinstance(commands, dict) else []
            selectors = "file paths"
            if adapter == "unittest":
                selectors += ", test_case (dotted names, unittest only)"
            lines.append("- %s (%s): modes %s; selectors: %s."
                         % (toolchain_id, adapter,
                            ", ".join(modes) if modes else "none", selectors))
    scope = _capability_scope(policy)
    if scope["mode"] == "areas":
        lines.append("Reserved areas: %s." % ", ".join(scope["roots"]))
    else:
        lines.append("Legacy exact-path authority (no opted-in areas).")
    protected = policy.get("protected_paths", [])
    names = sorted(str(item) for item in protected) if isinstance(
        protected, list) else []
    lines.append("%d protected paths (%s) plus manifests and lockfiles "
                 "are rejected." % (len(names), ", ".join(names)))
    return "\n".join(lines)


def run_scoped(workspace_value: str, task_id: str, mode: str, raw_paths: list[str]) -> int:
    workspace = Path(workspace_value).resolve()
    if mode not in MODES:
        raise RunnerError("invalid mode %s; expected red, test, analyze, or format" % mode)
    if mode in ("analyze", "format") and raw_paths:
        raise RunnerError("unexpected test path argument for %s mode" % mode)
    if any(value == "--" or value.startswith("-") for value in raw_paths):
        raise RunnerError("unexpected argument; scoped-run accepts paths, not commands")
    paths = _validated_test_paths(raw_paths)
    plan = _load_json(workspace / "plan.json", "task plan")
    task = _find_task(plan, task_id)
    toolchain_id = task.get("toolchain_id")
    if not isinstance(toolchain_id, str) or not toolchain_id.strip():
        raise RunnerError("task %s has no explicit toolchain_id" % task_id)
    descriptor = _read_gate(workspace, toolchain_id)
    root = _project_root(task, plan, descriptor)
    descriptor = _relocate_descriptor(descriptor, root)
    paths = _validated_test_paths(raw_paths, root)
    areas = task.get("working_areas")
    if isinstance(areas, list) and areas:
        import working_areas
        try:
            scope = working_areas.normalize(task, str(root))
        except ValueError as exc:
            raise RunnerError(
                "task working areas are invalid: %s" % exc) from exc
        for rel in paths:
            if not _in_scope_roots(scope["roots"], rel):
                raise RunnerError(
                    "scoped path is outside the reserved areas: %s" % rel)
    resolved = resolve_toolchain(
        {"toolchain_id": toolchain_id}, {"toolchains": {toolchain_id: descriptor}}, str(root)
    )
    if not resolved.get("available"):
        raise RunnerError("toolchain preflight failed: %s" % resolved.get("error", "unknown error"))
    adapter = resolved["red_adapter"]
    if adapter not in ADAPTER_LANGUAGES:
        raise RunnerError("unsupported RED adapter: %s" % adapter)
    if mode == "red" and adapter not in ADAPTER_LANGUAGES:
        raise RunnerError("unsupported RED adapter: %s" % adapter)
    commands = resolved["commands"]
    if mode not in commands:
        raise RunnerError("toolchain %s has no configured %s command" % (toolchain_id, mode))

    command = commands[mode]
    evidence_path = workspace / ("task-%s-red.txt" % task_id)
    raw_output = workspace / ("task-%s-%s-output.txt" % (task_id, mode)) if mode == "red" else workspace / ("task-%s-%s.txt" % (task_id, mode))
    argv = _expand_argv(command, adapter, mode, paths, evidence_path.with_suffix(".report.json"))
    source_snapshot = _source_snapshot(root) if mode == "red" else ""
    attempt_id = (os.environ.get("PIPELINE_ATTEMPT_ID") or task.get("attempt_id")
                  or uuid.uuid4().hex)
    identity = {
        "task_id": int(task_id) if task_id.isdigit() else task_id,
        "task_family_id": task.get("task_family_id") or "task-%s" % task_id,
        "attempt_id": attempt_id,
        "toolchain_id": toolchain_id,
        "runner": "scoped-run-v1",
        "command": argv,
        "source_snapshot": source_snapshot,
        "adapter": adapter,
    }
    if mode == "red":
        _write_attempt(workspace, task_id, identity)
    rc = _run(argv, command, raw_output)
    if mode != "red":
        return rc

    try:
        output_text = raw_output.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RunnerError("cmd did not preserve full output: %s" % exc) from exc
    if adapter == "unittest":
        tests_run, executed, failures, errors = _parse_unittest(output_text)
        payload = {
            "version": 1,
            **identity,
            "tests_run": tests_run,
            "executed_tests": executed,
            "failures": failures,
            "errors": errors,
            "tests": ([{"id": name, "outcome": "failure" if name in failures else
                        "error" if name in errors else "passed"} for name in executed]),
            "exit_code": rc,
            "raw_output_path": str(raw_output),
        }
    else:
        parser_input = output_text
        report_path = evidence_path.with_suffix(".report.json")
        if adapter == "pytest_json_report" and report_path.is_file():
            parser_input = report_path.read_text(encoding="utf-8", errors="replace")
        valid_red, executed, failing = classify_raw(adapter, parser_input)
        failures = failing if valid_red else []
        errors: list[str] = []
        payload = {
            "version": 1,
            **identity,
            "tests_run": len(executed),
            "executed_tests": executed,
            "failures": failures,
            "errors": errors,
            "raw_output": parser_input,
            "raw_output_path": str(raw_output),
            "exit_code": rc,
        }
    _atomic_json(evidence_path, payload)
    return rc


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: scoped-run WORKSPACE TASK red|test|analyze|format [TEST_PATH...]", file=sys.stderr)
        return 2
    try:
        return run_scoped(argv[0], argv[1], argv[2], argv[3:])
    except RunnerError as exc:
        print("SCOPED-RUN: preflight failed: %s" % exc, file=sys.stderr)
        return INFRASTRUCTURE_EXIT
    except OSError as exc:
        print("SCOPED-RUN: infrastructure failure: %s" % exc, file=sys.stderr)
        return INFRASTRUCTURE_EXIT


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
