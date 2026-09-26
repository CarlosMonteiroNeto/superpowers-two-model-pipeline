"""Validate attempt-bound RED evidence and classify tested adapter formats."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


IDENTITY_FIELDS = (
    "task_id", "attempt_id", "toolchain_id", "runner", "command", "source_snapshot", "adapter"
)


def _jsonl(text: str):
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            yield value


def _classify_unittest(value: dict[str, Any]) -> tuple[bool, str]:
    executed = value.get("executed_tests")
    if executed is None:
        executed = [test.get("id") for test in value.get("tests", [])
                    if isinstance(test, dict) and test.get("id")]
    failures = value.get("failures") or []
    errors = value.get("errors") or []
    tests_run = value.get("tests_run")
    if tests_run is not None and (not isinstance(tests_run, int) or tests_run < 1):
        return False, "unittest reported no executed tests"
    if not isinstance(executed, list) or not executed:
        return False, "no unittest test actually executed"
    if any("_FailedTest" in str(test) for test in executed):
        return False, "unittest loader failures are not executed tests"
    if not isinstance(failures, list) or not isinstance(errors, list):
        return False, "unittest failures/errors must be lists"
    executed_set = {str(test) for test in executed}
    failing = {str(test) for test in failures + errors}
    if not failing.intersection(executed_set):
        return False, "no executed unittest assertion or runtime error failed"
    if value.get("exit_code", 1) == 0:
        return False, "unittest command exited successfully"
    return True, "executed unittest test failed"


def _classify_flutter(text: str) -> tuple[bool, list[str], list[str]]:
    started: set[str] = set()
    failed: set[str] = set()
    for event in _jsonl(text):
        kind = event.get("type")
        test = event.get("test")
        test_id = str(event.get("testID") or (test.get("id") if isinstance(test, dict) else ""))
        if kind == "testStart":
            started.add(test_id or str(len(started) + 1))
        elif kind == "testDone" and event.get("result") in ("failure", "error"):
            failed.add(test_id or (next(iter(started)) if started else ""))
    failed.discard("")
    return bool(started and failed), sorted(started), sorted(failed)


def _classify_pytest(text: str) -> tuple[bool, list[str], list[str]]:
    try:
        report = json.loads(text)
    except ValueError:
        return False, [], []
    if not isinstance(report, dict) or not isinstance(report.get("tests"), list):
        return False, [], []
    tests = report["tests"]
    executed = [str(test.get("nodeid", test.get("id", ""))) for test in tests
                if isinstance(test, dict) and test.get("outcome") in ("passed", "failed", "error")]
    failures = [str(test.get("nodeid", test.get("id", ""))) for test in tests
                if isinstance(test, dict) and test.get("outcome") == "failed"]
    errors = [str(test.get("nodeid", test.get("id", ""))) for test in tests
              if isinstance(test, dict) and test.get("outcome") == "error"]
    return bool(executed and (failures or errors)), executed, failures + errors


def _classify_go(text: str) -> tuple[bool, list[str], list[str]]:
    started: set[str] = set()
    failed: set[str] = set()
    for event in _jsonl(text):
        test = event.get("Test")
        if not test:
            continue
        name = str(test)
        if event.get("Action") == "run":
            started.add(name)
        elif event.get("Action") == "fail":
            failed.add(name)
    return bool(started and failed), sorted(started), sorted(failed)


def classify_raw(adapter: str, text: str) -> tuple[bool, list[str], list[str]]:
    """Classify raw output for one of the tested RED adapters."""
    if adapter in ("flutter_machine", "flutter"):
        return _classify_flutter(text)
    if adapter in ("pytest_json_report", "pytest", "python"):
        return _classify_pytest(text)
    if adapter in ("go_test_json", "go"):
        return _classify_go(text)
    return False, [], []


def validate_evidence(path: str, expected: dict) -> dict[str, Any]:
    """Validate identity and RED shape for an evidence file.

    ``expected`` must bind the task, attempt, selected toolchain, runner,
    command, and source snapshot. Previous-attempt evidence is rejected even
    when its test outcome was once a valid failure.
    """
    try:
        with open(path, encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, ValueError) as exc:
        return {"valid_red": False, "error": "cannot read JSON evidence: %s" % exc}
    if not isinstance(value, dict) or not isinstance(expected, dict):
        return {"valid_red": False, "error": "evidence and expected identity must be objects"}
    missing_expected = [field for field in IDENTITY_FIELDS if field not in expected]
    if missing_expected:
        return {"valid_red": False, "error": "expected identity is missing: %s" % ", ".join(missing_expected)}
    mismatched = [field for field in IDENTITY_FIELDS
                  if field not in value or value[field] != expected[field]]
    if mismatched:
        return {"valid_red": False, "error": "evidence identity mismatch: %s" % ", ".join(mismatched)}

    adapter = value.get("adapter")
    if adapter == "unittest":
        valid, reason = _classify_unittest(value)
    else:
        raw = value.get("raw_output")
        if not isinstance(raw, str):
            return {"valid_red": False, "error": "machine-readable raw_output is missing"}
        valid, _, _ = classify_raw(str(adapter), raw)
        reason = "executed test failed" if valid else "suite has no executed failing test"
    return {"valid_red": bool(valid), "error": "" if valid else reason,
            "identity": {field: value[field] for field in IDENTITY_FIELDS},
            "adapter": adapter}
