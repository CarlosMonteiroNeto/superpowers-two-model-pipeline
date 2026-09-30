"""Read exact toolchain gate records and execute their argv contracts safely."""

from __future__ import annotations

import json
import os
import hashlib
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


def _task_selection_is_legacy(workspace: str, task_ids: list[str]) -> bool:
    """Return true only when every selected plan task is explicitly legacy."""
    plan_path = Path(workspace) / "plan.json"
    if not plan_path.exists():
        return True
    try:
        tasks = _read_plan(workspace)["tasks"]
    except GateContractError:
        return False
    for task_id in task_ids:
        matches = [task for task in tasks if isinstance(task, dict)
                   and str(task.get("id")) == str(task_id)]
        if len(matches) != 1:
            return False
        toolchain_id = matches[0].get("toolchain_id")
        if toolchain_id is not None:
            if not isinstance(toolchain_id, str) or toolchain_id.strip():
                return False
    return True


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


def _impact_test_argv(workspace: str, entry: dict[str, Any], spec: dict[str, Any]) -> tuple[list[str], str | None]:
    manifest_path = os.environ.get("PIPELINE_IMPACT_MANIFEST")
    if not manifest_path:
        return list(spec["argv"]), None
    try:
        from gate_evidence import validate_manifest
        import test_impact
        manifest = validate_manifest(json.loads(Path(manifest_path).read_text(encoding="utf-8")))
        expected_hash = os.environ.get("PIPELINE_IMPACT_EXPECTED_HASH")
        if not expected_hash or manifest["selection_hash"] != expected_hash:
            raise ValueError("persisted impact manifest changed after gate preflight")
        identity = str(entry.get("toolchain_id") or entry.get("lang") or "legacy")
        matches = [item for item in manifest["commands"] if item.get("toolchain_id") == identity]
        if len(matches) != 1:
            raise ValueError("impact manifest does not contain exactly one command for %s" % identity)
        command = matches[0]
        descriptor = _descriptor(entry)
        language = descriptor.get("language") or entry.get("lang")
        if spec.get("cwd"):
            expected_cwd = spec["cwd"]
        else:
            result = subprocess.run(["git", "-C", workspace, "rev-parse", "--show-toplevel"],
                                    capture_output=True, text=True)
            if result.returncode != 0:
                raise ValueError("cannot verify the manifest command working directory")
            expected_cwd = result.stdout.strip()
        mismatches = []
        if command.get("language") != language:
            mismatches.append("language")
        def normalized_path(value: Any) -> str | None:
            if not isinstance(value, str) or not value:
                return None
            return os.path.normcase(os.path.abspath(os.path.normpath(value)))

        if normalized_path(command.get("cwd")) != normalized_path(expected_cwd):
            mismatches.append("cwd")
        if command.get("env") != spec.get("env", {}):
            mismatches.append("env")
        if mismatches:
            raise ValueError("impact manifest toolchain contract differs from the ledger (%s)"
                             % ", ".join(mismatches))
        full_argv = list(spec["argv"])
        if command.get("full_suite") is True:
            if command.get("argv") != full_argv or command.get("tests") != []:
                raise ValueError("impact manifest full-suite argv differs from the ledger")
            return full_argv, manifest["selection_hash"]
        if command.get("full_suite") is not False or not manifest["evidence"]["graph_provenance"].get("complete"):
            raise ValueError("impact manifest cannot prove a complete affected selection")
        expected = test_impact.affected_argv(full_argv, descriptor.get("red_adapter"), command.get("tests"))
        if command.get("argv") != expected:
            raise ValueError("impact manifest selected argv is not derived from the ledger")
        phase = os.environ.get("PIPELINE_GATE_PHASE", "task")
        if phase in ("baseline", "closing"):
            return full_argv, manifest["selection_hash"]
        return expected, manifest["selection_hash"]
    except (OSError, ValueError, TypeError, KeyError, ImportError) as exc:
        raise GateContractError("invalid candidate-bound impact manifest: %s" % exc) from exc


def _record_executed_command(workspace: str, entry: dict[str, Any], name: str,
                             argv: list[str], cwd: str, selection_hash: str | None) -> None:
    path = Path(workspace) / "run-gates-executed.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        if not isinstance(rows, list):
            raise ValueError("execution evidence must be a list")
    except (OSError, ValueError) as exc:
        raise GateContractError("cannot read gate execution evidence: %s" % exc) from exc
    rows.append({"toolchain_id": str(entry.get("toolchain_id") or entry.get("lang") or "legacy"),
                 "command": name, "argv": argv, "cwd": cwd, "selection_hash": selection_hash})
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(rows, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


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
    # Toolchains are resolved before task worktrees are allocated. Rebase an
    # absolute configured cwd from that source checkout into the active Git
    # checkout so task gates run against the task branch they are approving.
    descriptor = _descriptor(entry)
    source_value = descriptor.get("project_root")
    if source_value and Path(str(source_value)).is_absolute() and Path(cwd).is_absolute():
        git_root = subprocess.run(
            ["git", "-C", workspace, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
        )
        if git_root.returncode == 0 and git_root.stdout.strip():
            source_root = Path(str(source_value)).resolve()
            checkout = Path(git_root.stdout.strip()).resolve()
            try:
                relative = Path(cwd).resolve().relative_to(source_root)
            except ValueError:
                pass
            else:
                mapped = (checkout / relative).resolve()
                if mapped.is_dir():
                    cwd = str(mapped)
    env = dict(os.environ)
    env.update(spec["env"])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    argv = list(spec["argv"])
    selection_hash = None
    if name == "test":
        argv, selection_hash = _impact_test_argv(workspace, entry, spec)
        adapter = descriptor.get("red_adapter")
        evidence_file = log_path + ".report.json"
        if adapter == "pytest_json_report":
            if "--json-report" not in argv:
                argv.append("--json-report")
            if not any(part.startswith("--json-report-file") for part in argv):
                argv.append("--json-report-file=" + evidence_file)
        elif adapter == "flutter_machine" and "--machine" not in argv:
            argv.append("--machine")
        elif adapter == "go_test_json" and "test" in argv and "-json" not in argv:
            argv.insert(argv.index("test") + 1, "-json")
        elif adapter == "unittest" and "-v" not in argv:
            argv.append("-v")
    _record_executed_command(workspace, entry, name, argv, cwd, selection_hash)
    process = subprocess.run(
        [bash, str(cmd_path), "--full-file", log_path, "--", *argv],
        cwd=cwd, env=env,
    )
    if name == "test":
        Path(log_path + ".exit-code").write_text(str(process.returncode), encoding="ascii")
    return process.returncode


def run_gates(workspace: str, entries: list[dict[str, Any]]) -> int:
    Path(workspace).mkdir(parents=True, exist_ok=True)
    multiple = len(entries) > 1
    result = 0
    for entry in entries:
        identity = str(entry.get("toolchain_id") or entry.get("lang") or "legacy")
        suffix = "-" + "".join(
            char if char.isalnum() or char in "-_." else "_" for char in identity
        ) if multiple else ""
        test_log = str(Path(workspace) / ("run-gates-test%s.txt" % suffix))
        analyze_log = str(Path(workspace) / ("run-gates-analyze%s.txt" % suffix))
        test_rc = _run_one(workspace, entry, "test", test_log)
        if test_rc:
            print("RUN-GATES: tests FAILED (see %s)" % test_log, file=sys.stderr)
            result = max(result, 1)
        analyze_rc = _run_one(workspace, entry, "analyze", analyze_log)
        if analyze_rc:
            print("RUN-GATES: analysis found issues (see %s)" % analyze_log, file=sys.stderr)
            result = max(result, 2)
    if result:
        return result
    print("RUN-GATES: all configured gates passed")
    return 0


def run_formats(workspace: str, entries: list[dict[str, Any]]) -> int:
    """Run configured formatters for exact toolchain identities only."""
    Path(workspace).mkdir(parents=True, exist_ok=True)
    multiple = len(entries) > 1
    for entry in entries:
        identity = str(entry.get("toolchain_id") or entry.get("lang") or "legacy")
        suffix = "-" + "".join(char if char.isalnum() or char in "-_." else "_" for char in identity) if multiple else ""
        log_path = str(Path(workspace) / ("run-gates-format%s.txt" % suffix))
        if command_spec(entry, "format") is None:
            print("RUN-GATES: formatting unavailable for %s (no formatter configured)" % identity)
            continue
        if _run_one(workspace, entry, "format", log_path):
            print("RUN-GATES: formatter failed (see %s)" % log_path, file=sys.stderr)
            return 1
    print("RUN-GATES: configured formatters completed")
    return 0


def run_cli(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: toolchain_gate.py run WORKSPACE (--toolchains ID...|--tasks ID...|--format ID...|--commands TEST ANALYZE)", file=sys.stderr)
        return 2
    mode, workspace, *args = argv
    if mode != "run":
        print("unsupported toolchain_gate.py mode: %s" % mode, file=sys.stderr)
        return 2
    try:
        if not args:
            raise GateContractError("missing gate selection")
        if args[0] == "--format":
            if len(args) < 2:
                raise GateContractError("--format requires at least one exact toolchain_id")
            entries = [gate_for_toolchain(workspace, item) for item in args[1:]]
            return run_formats(workspace, entries)
        elif args[0] == "--toolchains":
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
                if args[0] == "--tasks" and not _task_selection_is_legacy(workspace, args[1:]):
                    legacy_eligible = False
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
