"""Classify suite failures against immutable pre-change evidence.

The caller records evidence before changed-code verification and supplies the
final candidate identity. This module never treats an unknown result as an
inherited failure or grants a waiver on behalf of a worker.
"""

from __future__ import annotations

import re
import hashlib
import json
from pathlib import Path
from typing import Any


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_IDENTITY = ("suite", "test", "signature")


def _digest(value: Any, label: str, pattern: re.Pattern[str] = _SHA256) -> None:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError("%s must be a lowercase hash" % label)


def _name(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or value.strip() == "*":
        raise ValueError("%s must be a concrete nonempty string" % label)


def _failures(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for suite in evidence["suites"]:
        suite_id = suite["id"]
        for failure in suite["failures"]:
            item = {**failure, "suite": suite_id}
            identity = (suite_id, item["test"])
            if identity in seen:
                raise ValueError("duplicate failure identity: %s/%s" % identity)
            seen.add(identity)
            result.append(item)
    return result


def _completed(suite: dict[str, Any]) -> bool:
    raw = suite["raw_result"]
    # Unknown exit codes cannot establish that all tests finished. A toolchain
    # adapter must normalize its ordinary test-failure exit to 1 first.
    return raw["status"] == "completed" and raw["exit_code"] in (0, 1)


def validate_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    """Validate raw suite evidence without normalizing away its output."""
    if not isinstance(evidence, dict):
        raise ValueError("evidence must be an object")
    for field in ("source_hash", "environment_hash", "command_hash"):
        _digest(evidence.get(field), field)
    suites = evidence.get("suites")
    if not isinstance(suites, list) or not suites:
        raise ValueError("evidence requires at least one suite")
    seen_suites = set()
    for suite in suites:
        if not isinstance(suite, dict):
            raise ValueError("suite must be an object")
        _name(suite.get("id"), "suite id")
        if suite["id"] in seen_suites:
            raise ValueError("duplicate suite id")
        seen_suites.add(suite["id"])
        raw_result = suite.get("raw_result")
        if not isinstance(raw_result, dict) or isinstance(raw_result.get("exit_code"), bool) or not isinstance(raw_result.get("exit_code"), int):
            raise ValueError("suite requires raw_result.exit_code")
        _name(raw_result.get("status"), "runner status")
        tests = suite.get("tests")
        if not isinstance(tests, list):
            raise ValueError("suite requires complete executed test inventory")
        for test in tests:
            _name(test, "executed test")
        if len(set(tests)) != len(tests):
            raise ValueError("duplicate executed test identity")
        failures = suite.get("failures")
        if not isinstance(failures, list):
            raise ValueError("suite failures must be an array")
        if failures and raw_result["exit_code"] == 0:
            raise ValueError("failing tests cannot have a green raw result")
        for failure in failures:
            if not isinstance(failure, dict):
                raise ValueError("failure must be an object")
            for field in ("test", "signature", "raw"):
                _name(failure.get(field), "failure %s" % field)
            if failure["test"] not in tests:
                raise ValueError("failure does not belong to executed test inventory")
    _failures(evidence)
    return evidence


def compare(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Return inherited, new and uncertain failures with suite impact.

    Only the exact suite/test/error signature under the same runner environment
    and command is inherited. Renames and changed signatures are uncertain.
    """
    validate_evidence(baseline)
    validate_evidence(current)
    prior = _failures(baseline)
    now = _failures(current)
    prior_by_test = {(item["suite"], item["test"]): item for item in prior}
    prior_signatures = {(item["suite"], item["signature"]) for item in prior}
    prior_suites = {suite["id"]: suite for suite in baseline["suites"]}
    current_suites = {suite["id"]: suite for suite in current["suites"]}
    comparable = (baseline["environment_hash"] == current["environment_hash"]
                  and baseline["command_hash"] == current["command_hash"])
    inherited: list[dict[str, Any]] = []
    new: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    for item in now:
        previous = prior_by_test.get((item["suite"], item["test"]))
        if not _completed(current_suites[item["suite"]]) or (item["suite"] in prior_suites and not _completed(prior_suites[item["suite"]])):
            ambiguous.append({**item, "reason": "runner_not_completed"})
        elif not comparable:
            ambiguous.append({**item, "reason": "environment_or_command_drift"})
        elif previous and previous["signature"] == item["signature"]:
            inherited.append(item)
        elif previous:
            ambiguous.append({**item, "reason": "changed_error_signature"})
        elif (item["suite"], item["signature"]) in prior_signatures:
            ambiguous.append({**item, "reason": "possible_renamed_test"})
        else:
            new.append(item)
    current_suite_ids = {suite["id"] for suite in current["suites"]}
    baseline_suite_ids = {suite["id"] for suite in baseline["suites"]}
    for suite in current["suites"]:
        if not _completed(suite) and not suite["failures"]:
            ambiguous.append({"suite": suite["id"], "reason": "runner_not_completed",
                              "raw_result": suite["raw_result"]})
        elif suite["raw_result"]["exit_code"] != 0 and not suite["failures"]:
            ambiguous.append({"suite": suite["id"], "reason": "unexplained_failing_result",
                              "raw_result": suite["raw_result"]})
    for suite in baseline["suites"]:
        current_suite = current_suites.get(suite["id"])
        if current_suite is None:
            continue
        for test in sorted(set(suite["tests"]) - set(current_suite["tests"])):
            ambiguous.append({"suite": suite["id"], "test": test, "reason": "test_not_rerun"})
        if not _completed(suite):
            ambiguous.append({"suite": suite["id"], "reason": "baseline_runner_not_completed",
                              "raw_result": suite["raw_result"]})
    for suite_id in sorted(baseline_suite_ids - current_suite_ids):
        ambiguous.append({"suite": suite_id, "reason": "suite_not_rerun"})
    affected = sorted({item["suite"] for item in new + ambiguous})
    current_failed_tests = {(x["suite"], x["test"]) for x in now}
    return {
        "status": "blocked" if new or ambiguous else ("baseline_only" if inherited else "green"),
        "baseline_source_hash": baseline["source_hash"],
        "source_hash": current["source_hash"],
        "environment_hash": current["environment_hash"],
        "command_hash": current["command_hash"],
        "inherited": inherited,
        "new": new,
        "ambiguous": ambiguous,
        "resolved": [item for item in prior if comparable and item["suite"] in current_suites
                     and _completed(prior_suites[item["suite"]]) and _completed(current_suites[item["suite"]])
                     and item["test"] in current_suites[item["suite"]]["tests"]
                     and (item["suite"], item["test"]) not in current_failed_tests],
        "affected_suites": affected,
        "unaffected_suites": sorted(current_suite_ids - set(affected)),
        "raw_suites": current["suites"],
    }


def validate_waiver(waiver: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Validate a user approval in the supervisor ledger against rerun evidence.

    Candidate paths and evidence come from the supervisor, not from the worker
    waiver payload. The comparison is recomputed before checking its recorded
    copy and the candidate-bound approval event in the ledger.
    """
    if not isinstance(waiver, dict) or not isinstance(candidate, dict):
        raise ValueError("waiver and candidate must be objects")
    if waiver.get("approved_by") != "user":
        raise ValueError("only an explicit user waiver is accepted")
    _name(waiver.get("approval_record"), "approval record")
    comparison = compare(candidate.get("baseline"), candidate.get("current"))
    if candidate.get("recorded_comparison") != comparison:
        raise ValueError("recorded comparison does not match raw suite evidence")
    if comparison["status"] != "baseline_only":
        raise ValueError("new or ambiguous failures cannot be waived")
    _digest(candidate.get("candidate_commit"), "candidate commit", _COMMIT)
    for field in ("candidate_commit", "source_hash", "environment_hash", "command_hash", "baseline_source_hash"):
        expected = candidate["candidate_commit"] if field == "candidate_commit" else comparison[field]
        if waiver.get(field) != expected:
            raise ValueError("waiver expired or mismatched: %s" % field)
    failures = comparison["inherited"]
    waived = waiver.get("failures")
    if not failures or not isinstance(waived, list) or not waived:
        raise ValueError("waiver requires exact remaining failures")
    def keys(items: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
        result = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("failure must be an object")
            for field in _IDENTITY:
                _name(item.get(field), field)
            result.append(tuple(item[field] for field in _IDENTITY))
        if len(set(result)) != len(result):
            raise ValueError("duplicate failure in waiver or candidate")
        return sorted(result)
    if keys(waived) != keys(failures):
        raise ValueError("waiver does not match exact remaining failures")
    if any(set(item) != set(_IDENTITY) for item in waived):
        raise ValueError("waiver failure must contain only identity fields")
    ledger_path = candidate.get("approval_ledger")
    if not isinstance(ledger_path, str) or not ledger_path:
        raise ValueError("supervisor approval ledger is required")
    try:
        raw_ledger = Path(ledger_path).read_bytes()
        entries = [json.loads(line) for line in raw_ledger.splitlines() if line.strip()]
    except (OSError, ValueError) as exc:
        raise ValueError("cannot read supervisor approval ledger") from exc
    ledger_revision = candidate.get("ledger_revision")
    _digest(ledger_revision, "ledger revision")
    if hashlib.sha256(raw_ledger).hexdigest() != ledger_revision:
        raise ValueError("approval ledger changed since candidate snapshot")
    comparison_hash = hashlib.sha256(json.dumps(comparison, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    matching = [entry for entry in entries if isinstance(entry, dict)
                and entry.get("type") == "baseline_waiver_approved"
                and entry.get("approval_record") == waiver["approval_record"]]
    if len(matching) != 1 or matching[0].get("actor") != "user" or matching[0].get("candidate_commit") != candidate["candidate_commit"] or matching[0].get("comparison_hash") != comparison_hash:
        raise ValueError("no exact supervisor-recorded user approval for candidate")
    return {"status": "completed_with_waived_baseline", "candidate_commit": candidate["candidate_commit"],
            "approval_record": waiver["approval_record"], "failures": failures}
