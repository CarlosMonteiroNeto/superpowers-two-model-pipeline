"""Read exact toolchain gate records and execute their argv contracts safely."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


class GateContractError(ValueError):
    pass


def _read_plan(workspace: str) -> dict[str, Any]:
    path = Path(workspace) / "plan.json"
    try:
        with path.open(encoding="utf-8") as stream:
            plan = json.load(stream)
    except (OSError, ValueError) as exc:
        raise GateContractError("cannot read plan: %s" % exc) from exc
    if not isinstance(plan, dict) or not isinstance(plan.get("tasks"), list):
        raise GateContractError("plan must contain a tasks array")
    return plan


def task_toolchain_id(workspace: str, task_id: str) -> str:
    tasks = _read_plan(workspace)["tasks"]
    matches = [task for task in tasks if isinstance(task, dict)
               and str(task.get("id")) == str(task_id)]
    if len(matches) != 1:
        raise GateContractError("task %s is missing or ambiguous in the plan" % task_id)
    toolchain_id = matches[0].get("toolchain_id")
    if not isinstance(toolchain_id, str) or not toolchain_id.strip():
        raise GateContractError("task %s has no explicit toolchain_id" % task_id)
    return toolchain_id


def load_gate_entries(workspace: str) -> list[dict[str, Any]]:
    path = Path(workspace) / "ledger.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise GateContractError("cannot read ledger: %s" % exc) from exc
    entries = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError as exc:
            raise GateContractError("invalid ledger JSON on line %d" % number) from exc
        if isinstance(entry, dict) and entry.get("type") == "gate":
            entries.append(entry)
    return entries


def gate_for_toolchain(workspace: str, toolchain_id: str) -> dict[str, Any]:
    matches = [entry for entry in load_gate_entries(workspace)
               if entry.get("toolchain_id") == toolchain_id]
    if len(matches) != 1:
        reason = "no" if not matches else "multiple"
        raise GateContractError("%s gate entries for toolchain_id %s" % (reason, toolchain_id))
    return matches[0]


def task_language(workspace: str, task_id: str) -> str:
    try:
        toolchain_id = task_toolchain_id(workspace, task_id)
    except GateContractError as exc:
        # A single unstructured gate remains supported for pre-R2 plans.
        # Structured descriptors always require the explicit task identity.
        if "no explicit toolchain_id" not in str(exc) and (Path(workspace) / "plan.json").exists():
            raise
        entries = load_gate_entries(workspace)
        if len(entries) != 1 or "toolchain_descriptor" in entries[0]:
            raise
        entry = entries[0]
        toolchain_id = str(entry.get("toolchain_id") or "legacy")
    else:
        entry = gate_for_toolchain(workspace, toolchain_id)
    language = entry.get("lang")
    if not isinstance(language, str) or not language.strip():
        descriptor = _descriptor(entry)
        language = descriptor.get("language")
    if not isinstance(language, str) or not language.strip():
        raise GateContractError("gate for %s has no language" % toolchain_id)
    return language


def legacy_gate_language(workspace: str) -> str:
    entries = load_gate_entries(workspace)
    if len(entries) != 1:
        raise GateContractError("legacy language selection requires exactly one gate entry")
    if "toolchain_descriptor" in entries[0]:
        raise GateContractError("structured gate selection requires an exact task toolchain_id")
    language = entries[0].get("lang")
    if not isinstance(language, str) or not language.strip():
        language = _descriptor(entries[0]).get("language")
    if not isinstance(language, str) or not language.strip():
        raise GateContractError("legacy gate entry has no language")
    return language


def _descriptor(entry: dict[str, Any]) -> dict[str, Any]:
    value = entry.get("toolchain_descriptor")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise GateContractError("malformed toolchain_descriptor") from exc
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise GateContractError("toolchain_descriptor must be an object")
    return value


def _argv_from_value(value: Any, label: str) -> list[str] | None:
    if value is None or value == "":
        return None
    if isinstance(value, list):
        argv = value
    elif isinstance(value, str):
        try:
            decoded = json.loads(value)
        except ValueError:
            decoded = None
        if isinstance(decoded, list):
            argv = decoded
        else:
            try:
                argv = shlex.split(value, posix=True)
            except ValueError as exc:
                raise GateContractError("malformed legacy %s command: %s" % (label, exc)) from exc
    else:
        raise GateContractError("%s command must be an argv array or string" % label)
    if not argv or not all(isinstance(part, str) and part and "\x00" not in part for part in argv):
        raise GateContractError("%s command must contain nonempty string argv" % label)
    return argv


def command_spec(entry: dict[str, Any], name: str) -> dict[str, Any] | None:
    descriptor = _descriptor(entry)
    if descriptor.get("available") is False:
        raise GateContractError(
            "toolchain %s is unavailable: %s" % (
                entry.get("toolchain_id", "unknown"),
                descriptor.get("preflight_error", "preflight failed"),
            )
        )
    commands = descriptor.get("commands")
    if isinstance(commands, dict):
        raw = commands.get(name)
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise GateContractError("commands.%s must be an object" % name)
        argv = _argv_from_value(raw.get("argv"), name)
        if argv is None:
            raise GateContractError("commands.%s.argv is missing" % name)
        cwd = raw.get("cwd")
        env = raw.get("env", raw.get("environment", {}))
        if cwd is not None and (not isinstance(cwd, str) or "\x00" in cwd):
            raise GateContractError("commands.%s.cwd must be a path" % name)
        if not isinstance(env, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            and key and "\x00" not in key and "\x00" not in value
            for key, value in env.items()
        ):
            raise GateContractError("commands.%s.env must map strings to strings" % name)
        return {"argv": argv, "cwd": cwd, "env": env}

    value = entry.get(name + "_cmd")
    if value in (None, ""):
        value = entry.get(name)
    argv = _argv_from_value(value, name)
    return None if argv is None else {"argv": argv, "cwd": None, "env": {}}


def _all_task_toolchains(workspace: str, task_ids: list[str]) -> list[str]:
    plan = _read_plan(workspace)
    requested = {str(task_id) for task_id in task_ids}
    matching: dict[str, list[dict[str, Any]]] = {task_id: [] for task_id in requested}
    for task in plan["tasks"]:
        if isinstance(task, dict) and str(task.get("id")) in matching:
            matching[str(task.get("id"))].append(task)
    missing = sorted(task_id for task_id, found in matching.items() if not found)
    if missing:
        raise GateContractError("tasks missing from plan: %s" % ", ".join(missing))
    result: list[str] = []
    for task_id in task_ids:
        found = matching[str(task_id)]
        if len(found) != 1:
            raise GateContractError("task %s is ambiguous in the plan" % task_id)
        toolchain_id = found[0].get("toolchain_id")
        if not isinstance(toolchain_id, str) or not toolchain_id.strip():
            raise GateContractError("task %s has no explicit toolchain_id" % task_id)
        if toolchain_id not in result:
            result.append(toolchain_id)
    return result


def _legacy_default_entry(workspace: str) -> dict[str, Any]:
    entries = load_gate_entries(workspace)
    if len(entries) != 1:
        raise GateContractError("legacy gate selection requires exactly one gate entry")
    if "toolchain_descriptor" in entries[0]:
        raise GateContractError("structured gate selection requires an exact task toolchain_id")
    return entries[0]


def _match_entry_for_argv(workspace: str, test_value: str, analyze_value: str) -> dict[str, Any] | None:
    test_argv = _argv_from_value(test_value, "test")
    analyze_argv = _argv_from_value(analyze_value, "analyze")
    matches = []
    for entry in load_gate_entries(workspace):
        test_spec = command_spec(entry, "test")
        analyze_spec = command_spec(entry, "analyze")
        if ((test_spec["argv"] if test_spec else None) == test_argv
                and (analyze_spec["argv"] if analyze_spec else None) == analyze_argv):
            matches.append(entry)
    if len(matches) > 1:
        ids = {entry.get("toolchain_id") for entry in matches}
        if len(ids) > 1:
            raise GateContractError("command strings match multiple toolchains; select an exact toolchain_id")
    return matches[0] if matches else None


def _try_match_entry_for_argv(workspace: str, test_value: str, analyze_value: str) -> dict[str, Any] | None:
    try:
        return _match_entry_for_argv(workspace, test_value, analyze_value)
    except GateContractError as exc:
        if "cannot read ledger" in str(exc):
            return None
        raise


def _run_one(workspace: str, entry: dict[str, Any], name: str, log_path: str) -> int | None:
    spec = command_spec(entry, name)
    if spec is None:
        if name == "analyze":
            identity = entry.get("toolchain_id", "legacy")
            print("RUN-GATES: analysis unavailable for %s (no analyzer configured)" % identity)
            return None
        raise GateContractError("gate record has no test command")
    bash = os.environ.get("BASH_BIN") or shutil.which("bash")
    if not bash:
        raise GateContractError("Bash is required to run the cmd output wrapper")
    script_dir = Path(__file__).resolve().parent
    cmd_path = script_dir / "cmd"
    cwd = spec["cwd"] or workspace
    env = dict(os.environ)
    env.update(spec["env"])
    process = subprocess.run(
        [bash, str(cmd_path), "--full-file", log_path, "--", *spec["argv"]],
        cwd=cwd, env=env,
    )
    return process.returncode


def run_gates(workspace: str, entries: list[dict[str, Any]]) -> int:
    Path(workspace).mkdir(parents=True, exist_ok=True)
    multiple = len(entries) > 1
    for entry in entries:
        identity = str(entry.get("toolchain_id") or entry.get("lang") or "legacy")
        suffix = "-" + "".join(char if char.isalnum() or char in "-_." else "_" for char in identity) if multiple else ""
        test_log = str(Path(workspace) / ("run-gates-test%s.txt" % suffix))
        analyze_log = str(Path(workspace) / ("run-gates-analyze%s.txt" % suffix))
        test_rc = _run_one(workspace, entry, "test", test_log)
        if test_rc:
            print("RUN-GATES: tests FAILED (see %s)" % test_log, file=sys.stderr)
            return 1
        analyze_rc = _run_one(workspace, entry, "analyze", analyze_log)
        if analyze_rc:
            print("RUN-GATES: analysis found issues (see %s)" % analyze_log, file=sys.stderr)
            return 2
    print("RUN-GATES: all configured gates passed")
    return 0


def run_cli(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: toolchain_gate.py run WORKSPACE (--toolchains ID...|--tasks ID...|--commands TEST ANALYZE)", file=sys.stderr)
        return 2
    mode, workspace, *args = argv
    if mode != "run":
        print("unsupported toolchain_gate.py mode: %s" % mode, file=sys.stderr)
        return 2
    try:
        if not args:
            raise GateContractError("missing gate selection")
        if args[0] == "--toolchains":
            if len(args) < 2:
                raise GateContractError("--toolchains requires at least one ID")
            entries = [gate_for_toolchain(workspace, item) for item in args[1:]]
        elif args[0] == "--tasks":
            if len(args) < 2:
                raise GateContractError("--tasks requires at least one task ID")
            try:
                ids = _all_task_toolchains(workspace, args[1:])
            except GateContractError as exc:
                # Preserve pre-R2 single-gate ledgers. Structured R2 records
                # always require the plan's explicit task toolchain identity.
                legacy_eligible = (
                    "has no explicit toolchain_id" in str(exc)
                    or ("cannot read plan:" in str(exc)
                        and not (Path(workspace) / "plan.json").exists())
                )
                if not legacy_eligible:
                    raise
                legacy = load_gate_entries(workspace)
                if len(legacy) == 1 and "toolchain_descriptor" not in legacy[0]:
                    entries = legacy
                else:
                    raise
            else:
                entries = [gate_for_toolchain(workspace, item) for item in ids]
        elif args[0] == "--commands":
            if len(args) != 3:
                raise GateContractError("--commands requires TEST_CMD and ANALYZE_CMD")
            entry = _try_match_entry_for_argv(workspace, args[1], args[2])
            if entry is None:
                raise GateContractError("commands do not match a ledgered legacy gate")
            if "toolchain_descriptor" in entry:
                raise GateContractError("structured gate selection requires an exact task toolchain_id")
            entries = [entry]
        elif args[0] == "--ledger":
            if len(args) != 1:
                raise GateContractError("--ledger takes no extra arguments")
            entries = [_legacy_default_entry(workspace)]
        elif args[0] == "--legacy":
            if len(args) != 1:
                raise GateContractError("--legacy takes no extra arguments")
            entries = [_legacy_default_entry(workspace)]
        else:
            # Preserve the historical WORKSPACE TEST_CMD ANALYZE_CMD form.
            if len(args) != 2:
                raise GateContractError("expected TEST_CMD and ANALYZE_CMD")
            entry = _try_match_entry_for_argv(workspace, args[0], args[1])
            if entry is None:
                raise GateContractError("commands do not match a ledgered legacy gate")
            if "toolchain_descriptor" in entry:
                raise GateContractError("structured gate selection requires an exact task toolchain_id")
            entries = [entry]
        return run_gates(workspace, entries)
    except GateContractError as exc:
        print("RUN-GATES: %s" % exc, file=sys.stderr)
        return 3


def main(argv: list[str]) -> int:
    if not argv:
        print("toolchain_gate.py is a library; use run-gates", file=sys.stderr)
        return 2
    if argv[0] == "task-toolchain" and len(argv) == 3:
        try:
            print(task_toolchain_id(argv[1], argv[2]))
            return 0
        except GateContractError as exc:
            print("TASK-TOOLCHAIN: %s" % exc, file=sys.stderr)
            return 1
    if argv[0] == "task-lang" and len(argv) == 3:
        try:
            print(task_language(argv[1], argv[2]))
            return 0
        except GateContractError as exc:
            print("TASK-LANG: %s" % exc, file=sys.stderr)
            return 1
    if argv[0] == "legacy-lang" and len(argv) == 2:
        try:
            print(legacy_gate_language(argv[1]))
            return 0
        except GateContractError as exc:
            print("LEGACY-LANG: %s" % exc, file=sys.stderr)
            return 1
    return run_cli(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
