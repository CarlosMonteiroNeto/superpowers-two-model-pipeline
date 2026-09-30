"""Build validated supervisor-owned raw suite evidence from gate outputs."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys

from baseline_failures import validate_evidence
import red_evidence


def _hash(value) -> str:
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _failure_details(adapter: str, raw_log: str, machine: str, failed: list[str]) -> dict[str, str]:
    details = {}
    if adapter == "unittest":
        import re
        for test in failed:
            match = re.search(r"(?:FAIL|ERROR):\s*" + re.escape(test) + r"\s*\n", raw_log)
            if match:
                end = re.search(r"\n(?:={3,}|Ran\s+\d+\s+tests?)", raw_log[match.end():])
                details[test] = raw_log[match.start():match.end() + end.start() if end else len(raw_log)].strip()
    elif adapter == "pytest_json_report":
        report = json.loads(machine)
        for row in report.get("tests", []):
            name = str(row.get("nodeid", row.get("id", "")))
            if name in failed:
                call = row.get("call", {})
                details[name] = str(call.get("longrepr") or call.get("crash", {}).get("message") or "")
    elif adapter in ("flutter_machine", "go_test_json"):
        for line in machine.splitlines():
            try: event = json.loads(line)
            except ValueError: continue
            if adapter == "flutter_machine":
                test = event.get("test", {})
                name = str(event.get("testID") or (test.get("id") if isinstance(test, dict) else ""))
                if name in failed and event.get("type") == "testDone":
                    details[name] = str(event.get("error") or event.get("result") or "")
            else:
                name = str(event.get("Test") or "")
                if name in failed and event.get("Action") == "output":
                    details[name] = details.get(name, "") + str(event.get("Output") or "")
    missing = [name for name in failed if not details.get(name, "").strip()]
    if missing:
        raise ValueError("adapter cannot normalize failure details for: " + ", ".join(missing))
    return details


def capture(workspace: str, toolchain_ids: list[str], root: str, output: str,
            candidate: dict | None = None) -> dict:
    from toolchain_gate import GateContractError, gate_for_toolchain, _descriptor
    from scoped_runner import _parse_unittest
    ws, repo = pathlib.Path(workspace), pathlib.Path(root)
    rows = [json.loads(line) for line in (ws / "ledger.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    gates = {str(row.get("toolchain_id")): row for row in rows if row.get("type") == "gate"}
    multiple = len(toolchain_ids) > 1
    suites = []
    for tc in toolchain_ids:
        try:
            entry = gate_for_toolchain(workspace, tc)
        except GateContractError:
            legacy = [row for row in rows if row.get("type") == "gate"
                      and not row.get("toolchain_id") and "toolchain_descriptor" not in row
                      and str(row.get("lang") or "legacy") == tc]
            if len(legacy) != 1:
                raise
            entry = legacy[0]
        descriptor = _descriptor(entry)
        adapter = descriptor.get("red_adapter")
        suffix = "-" + "".join(c if c.isalnum() or c in "-_." else "_" for c in tc) if multiple else ""
        log = ws / ("run-gates-test%s.txt" % suffix)
        raw = log.read_text(encoding="utf-8", errors="replace")
        machine = raw
        try:
            exit_code = int(pathlib.Path(str(log) + ".exit-code").read_text(encoding="ascii").strip())
        except (OSError, ValueError) as exc:
            raise ValueError("toolchain gate omitted raw process exit status") from exc
        if adapter == "unittest":
            count, executed, failed, errors = _parse_unittest(raw)
            if count <= 0 or not executed:
                raise ValueError("unittest adapter did not produce a complete test inventory")
            failures = failed + errors
        else:
            machine = raw
            report = pathlib.Path(str(log) + ".report.json")
            if adapter == "pytest_json_report":
                if not report.is_file():
                    raise ValueError("pytest adapter did not produce its JSON report")
                machine = report.read_text(encoding="utf-8", errors="replace")
            valid, executed, failures = red_evidence.classify_raw(str(adapter), machine)
            if not executed:
                raise ValueError("%s adapter did not produce a complete test inventory" % adapter)
        details = _failure_details(str(adapter), raw, machine, failures)
        failure_rows = [{"test": name, "signature": _hash(details[name]), "raw": details[name][:20000]} for name in failures]
        suites.append({"id": tc, "tests": executed, "failures": failure_rows,
                       "raw_result": {"status": "completed" if exit_code in (0, 1) else "interrupted",
                                      "exit_code": exit_code}})
    commands = {tc: _descriptor(gates[tc]) for tc in toolchain_ids}
    commit_tree = subprocess_check(repo, "rev-parse", "HEAD^{tree}")
    evidence = {"source_hash": _hash(commit_tree),
                "environment_hash": _hash({"python": sys.version, "platform": sys.platform, "path": os.environ.get("PATH", "")}),
                "command_hash": _hash(commands), "suites": suites}
    if candidate is not None:
        evidence.update({key: candidate[key] for key in
                         ("head_commit", "tree_hash", "config_hash", "environment_hash", "policy_version")})
        evidence["source_hash"] = _hash(candidate["tree_hash"])
    validate_evidence(evidence)
    destination = pathlib.Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.name == "baseline-evidence.json" and destination.exists():
        raise ValueError("baseline evidence is immutable and already exists")
    temp = destination.with_suffix(destination.suffix + ".tmp")
    temp.write_text(json.dumps(evidence, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, destination)
    return evidence


def subprocess_check(root: pathlib.Path, *args: str) -> str:
    import subprocess
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if result.returncode:
        raise ValueError("cannot identify source tree")
    return result.stdout.strip()


if __name__ == "__main__":
    if len(sys.argv) < 5:
        raise SystemExit("usage: suite_evidence.py WORKSPACE ROOT OUTPUT TOOLCHAIN...")
    try:
        capture(sys.argv[1], sys.argv[4:], sys.argv[2], sys.argv[3])
    except (OSError, ValueError, KeyError) as exc:
        print("SUITE-EVIDENCE: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
