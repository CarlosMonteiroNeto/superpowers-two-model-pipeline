"""Execute only task-declared toolchain commands through the shared cmd gate."""

from __future__ import annotations

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


def _run(argv: list[str], command: dict[str, Any], full_output: Path) -> int:
    bash = os.environ.get("BASH_BIN") or shutil.which("bash")
    if not bash:
        raise RunnerError("Bash is required to invoke the shared cmd output runner")
    env = dict(os.environ)
    env.update(command.get("env", command.get("environment", {})))
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    cmd_script = SCRIPT_DIR / "cmd"
    process = subprocess.run(
        [bash, str(cmd_script), "--full-file", str(full_output), "--", *argv],
        cwd=command["cwd"], env=env,
    )
    return process.returncode


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
    paths = _validated_test_paths(raw_paths, root)
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
