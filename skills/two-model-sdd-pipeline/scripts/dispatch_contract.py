"""Shared invocation and semantic result contracts (Round 1 Task 3).

The normalized request carries invocation identity, backend, role,
task/family/episode, worktree, base commit, plan revision, config and
prompt hashes, requested settings and evidence paths. The normalized
result carries the same identity plus candidate commit, runtime version,
provider session, process status, terminal completion, output schema and
hash, semantic final output, usage and error.

Transport completion stays separate from semantic outcome: a result is
accepted only for a clean completed transport with a matching output
hash and a strictly validated role payload. Malformed, truncated, stale
or mismatched output is rejected. A string that merely contains a verdict
is never accepted as a semantic payload.

Usage: dispatch_contract.validate_request(value: dict) -> dict;
dispatch_contract.validate_result(value: dict, request: dict) -> dict.
Invalid inputs raise dispatch_contract.ContractError (a ValueError).
No worker activity happens here: validation is pure and creates nothing.
"""

import copy
import hashlib
import json

VERSION = 1
BACKENDS = ("codex", "opencode")
ROLES = ("operator", "reviewer", "director")
TERMINAL_STATUSES = ("completed", "failed", "interrupted", "incomplete")
OPERATOR_STATUSES = (
    "DONE",
    "DONE_WITH_CONCERNS",
    "BLOCKED",
    "NEEDS_CONTEXT",
    "TEST_DEFECT",
)
REVIEWER_VERDICTS = ("APPROVED", "SEND_BACK", "ESCALATE")
SEVERITIES = ("Critical", "Important", "Minor")
CORRECTION_SCOPES = ("in_scope", "structural", "uncertain")
DIRECTOR_MODES = ("correction", "arbitration")
DIRECTOR_DECISIONS = ("propose", "amend")
CLOSING_VERDICTS = ("APPROVED", "REOPEN", "BLOCKED")
OUTPUT_SCHEMAS = (
    "operator-result-v1",
    "reviewer-result-v1",
    "director-result-v1",
    "closing-result-v1",
)
EVIDENCE_KEYS = (
    "request_path",
    "prompt_path",
    "events_path",
    "stderr_path",
    "final_path",
    "result_path",
)
REQUEST_FIELDS = (
    "version",
    "backend",
    "run_id",
    "dispatch_id",
    "task_id",
    "task_family",
    "episode_id",
    "role",
    "repository_id",
    "worktree",
    "plan_revision",
    "base_commit",
    "config_hash",
    "prompt_hash",
    "requested_model",
    "requested_effort",
    "evidence_paths",
)
RESULT_FIELDS = (
    "version",
    "backend",
    "run_id",
    "dispatch_id",
    "task_id",
    "task_family",
    "role",
    "episode_id",
    "repository_id",
    "worktree",
    "plan_revision",
    "base_commit",
    "candidate_commit",
    "requested_model",
    "requested_effort",
    "runtime_version",
    "config_hash",
    "session_id",
    "resumed_from",
    "process_exit",
    "terminal_status",
    "output_schema",
    "output_hash",
    "final_output",
    "usage",
    "error",
)
IDENTITY_FIELDS = (
    "backend",
    "run_id",
    "dispatch_id",
    "task_id",
    "task_family",
    "role",
    "episode_id",
    "repository_id",
    "worktree",
    "plan_revision",
    "base_commit",
    "requested_model",
    "requested_effort",
    "config_hash",
)
USAGE_KEYS = ("input_tokens", "cached_tokens", "output_tokens")
FINDING_FIELDS = (
    "severity",
    "file",
    "line",
    "issue",
    "fix",
    "correction_scope",
    "affected_paths",
    "affected_contracts",
)
ALLOWED_ARBITRATION_FIELDS = ("touches", "acceptance", "summary", "title")


class ContractError(ValueError):
    """A request or result failed strict contract validation."""


def _fail(message):
    raise ContractError(message)


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _output_hash(payload):
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _is_hex64(value):
    if not isinstance(value, str) or len(value) != 64:
        return False
    for char in value:
        if char not in "0123456789abcdefABCDEF":
            return False
    return True


def _nonempty_string(value, label):
    if not isinstance(value, str) or not value.strip():
        _fail("%s must be a nonempty string" % label)
    return value


def _positive_int(value, label):
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("%s must be an integer" % label)
    if value < 1:
        _fail("%s must be positive" % label)
    return value


def _non_negative_int_or_null(value, label):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("%s must be an integer or null" % label)
    if value < 0:
        _fail("%s must not be negative" % label)
    return value


def _string_list(value, label):
    if not isinstance(value, list):
        _fail("%s must be an array" % label)
    for item in value:
        if not isinstance(item, str):
            _fail("%s entries must be strings" % label)
    return list(value)


def _validate_evidence_paths(value):
    if not isinstance(value, dict):
        _fail("evidence_paths must be an object")
    for key in value:
        if key not in EVIDENCE_KEYS:
            _fail("evidence_paths.%s is not a known evidence path" % key)
    for key in EVIDENCE_KEYS:
        if key not in value:
            _fail("evidence_paths.%s is required" % key)
        _nonempty_string(value[key], "evidence_paths.%s" % key)
    return {key: value[key] for key in EVIDENCE_KEYS}


def validate_request(value):
    """Strictly validate a normalized worker request. Returns a copy."""
    if not isinstance(value, dict):
        _fail("request must be an object")
    for key in value:
        if key not in REQUEST_FIELDS:
            _fail("unsupported request field: %r" % key)
    for key in REQUEST_FIELDS:
        if key not in value:
            _fail("missing required request field: %r" % key)
    if isinstance(value.get("version"), bool) or value.get("version") != VERSION:
        _fail("version must be exactly 1")
    if value.get("backend") not in BACKENDS:
        _fail("backend must be one of %s" % (list(BACKENDS),))
    if value.get("role") not in ROLES:
        _fail("role must be one of %s" % (list(ROLES),))
    _nonempty_string(value.get("run_id"), "run_id")
    _nonempty_string(value.get("dispatch_id"), "dispatch_id")
    _positive_int(value.get("task_id"), "task_id")
    _positive_int(value.get("task_family"), "task_family")
    _nonempty_string(value.get("episode_id"), "episode_id")
    _nonempty_string(value.get("repository_id"), "repository_id")
    _nonempty_string(value.get("worktree"), "worktree")
    _nonempty_string(value.get("plan_revision"), "plan_revision")
    _nonempty_string(value.get("base_commit"), "base_commit")
    if not _is_hex64(value.get("config_hash")):
        _fail("config_hash must be 64 hex characters")
    if not _is_hex64(value.get("prompt_hash")):
        _fail("prompt_hash must be 64 hex characters")
    _nonempty_string(value.get("requested_model"), "requested_model")
    _nonempty_string(value.get("requested_effort"), "requested_effort")
    evidence = _validate_evidence_paths(value.get("evidence_paths"))
    return {
        "version": VERSION,
        "backend": value["backend"],
        "run_id": value["run_id"],
        "dispatch_id": value["dispatch_id"],
        "task_id": value["task_id"],
        "task_family": value["task_family"],
        "episode_id": value["episode_id"],
        "role": value["role"],
        "repository_id": value["repository_id"],
        "worktree": value["worktree"],
        "plan_revision": value["plan_revision"],
        "base_commit": value["base_commit"],
        "config_hash": value["config_hash"],
        "prompt_hash": value["prompt_hash"],
        "requested_model": value["requested_model"],
        "requested_effort": value["requested_effort"],
        "evidence_paths": evidence,
    }


def _validate_usage(value):
    if not isinstance(value, dict):
        _fail("usage must be an object")
    for key in value:
        if key not in USAGE_KEYS:
            _fail("unsupported usage field: %r" % key)
    for key in USAGE_KEYS:
        if key not in value:
            _fail("missing required usage field: %r" % key)
        _non_negative_int_or_null(value[key], "usage.%s" % key)
    return {
        "input_tokens": value["input_tokens"],
        "cached_tokens": value["cached_tokens"],
        "output_tokens": value["output_tokens"],
    }


def _validate_finding(value, label):
    if not isinstance(value, dict):
        _fail("%s must be an object" % label)
    for key in value:
        if key not in FINDING_FIELDS:
            _fail("unsupported %s field: %r" % (label, key))
    for key in FINDING_FIELDS:
        if key not in value:
            _fail("missing required %s field: %r" % (label, key))
    if value.get("severity") not in SEVERITIES:
        _fail("%s.severity must be one of %s" % (label, list(SEVERITIES)))
    _nonempty_string(value.get("file"), "%s.file" % label)
    line = value.get("line")
    if isinstance(line, bool) or not isinstance(line, int) or line < 0:
        _fail("%s.line must be an integer >= 0" % label)
    _nonempty_string(value.get("issue"), "%s.issue" % label)
    _nonempty_string(value.get("fix"), "%s.fix" % label)
    if value.get("correction_scope") not in CORRECTION_SCOPES:
        _fail("%s.correction_scope must be one of %s"
              % (label, list(CORRECTION_SCOPES)))
    _string_list(value.get("affected_paths"), "%s.affected_paths" % label)
    _string_list(value.get("affected_contracts"),
                 "%s.affected_contracts" % label)
    return {
        "severity": value["severity"],
        "file": value["file"],
        "line": value["line"],
        "issue": value["issue"],
        "fix": value["fix"],
        "correction_scope": value["correction_scope"],
        "affected_paths": list(value["affected_paths"]),
        "affected_contracts": list(value["affected_contracts"]),
    }


def _validate_operator(payload):
    if not isinstance(payload, dict):
        _fail("operator final_output must be an object")
    expected = ("status", "summary", "changed_files", "red_evidence",
                "concerns")
    for key in payload:
        if key not in expected:
            _fail("unsupported operator field: %r" % key)
    for key in expected:
        if key not in payload:
            _fail("missing required operator field: %r" % key)
    if payload.get("status") not in OPERATOR_STATUSES:
        _fail("operator status must be one of %s"
              % (list(OPERATOR_STATUSES),))
    _nonempty_string(payload.get("summary"), "operator summary")
    changed = payload.get("changed_files")
    if not isinstance(changed, list):
        _fail("operator changed_files must be an array")
    for item in changed:
        _nonempty_string(item, "operator changed_files entry")
    evidence = payload.get("red_evidence")
    if not isinstance(evidence, dict):
        _fail("operator red_evidence must be an object")
    for key in evidence:
        if key not in ("path", "runner", "exit_code"):
            _fail("unsupported operator red_evidence field: %r" % key)
    for key in ("path", "runner", "exit_code"):
        if key not in evidence:
            _fail("missing required operator red_evidence field: %r" % key)
    _nonempty_string(evidence.get("path"), "operator red_evidence.path")
    _nonempty_string(evidence.get("runner"),
                     "operator red_evidence.runner")
    exit_code = evidence.get("exit_code")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        _fail("operator red_evidence.exit_code must be an integer")
    concerns = payload.get("concerns")
    if not isinstance(concerns, list):
        _fail("operator concerns must be an array")
    for item in concerns:
        if not isinstance(item, str):
            _fail("operator concerns entries must be strings")
    status = payload["status"]
    if status == "DONE" and concerns:
        _fail("DONE must not carry concerns")
    if status == "DONE_WITH_CONCERNS" and not concerns:
        _fail("DONE_WITH_CONCERNS requires at least one concern")
    return {
        "status": payload["status"],
        "summary": payload["summary"],
        "changed_files": list(changed),
        "red_evidence": {
            "path": evidence["path"],
            "runner": evidence["runner"],
            "exit_code": evidence["exit_code"],
        },
        "concerns": list(concerns),
    }


def _validate_reviewer(payload):
    if not isinstance(payload, dict):
        _fail("reviewer final_output must be an object")
    expected = ("verdict", "findings", "minors", "summary")
    for key in payload:
        if key not in expected:
            _fail("unsupported reviewer field: %r" % key)
    for key in expected:
        if key not in payload:
            _fail("missing required reviewer field: %r" % key)
    if payload.get("verdict") not in REVIEWER_VERDICTS:
        _fail("reviewer verdict must be one of %s"
              % (list(REVIEWER_VERDICTS),))
    _nonempty_string(payload.get("summary"), "reviewer summary")
    findings = payload.get("findings")
    minors = payload.get("minors")
    if not isinstance(findings, list):
        _fail("reviewer findings must be an array")
    if not isinstance(minors, list):
        _fail("reviewer minors must be an array")
    clean_findings = [_validate_finding(item, "finding")
                      for item in findings]
    clean_minors = [_validate_finding(item, "minor") for item in minors]
    for item in clean_minors:
        if item["severity"] != "Minor":
            _fail("parked minors must be Minor")
    verdict = payload["verdict"]
    if verdict == "APPROVED":
        for item in clean_findings:
            if item["severity"] in ("Critical", "Important"):
                _fail("APPROVED cannot carry Critical/Important findings")
    else:
        if not clean_findings:
            _fail("%s requires at least one finding" % verdict)
    return {
        "verdict": verdict,
        "findings": clean_findings,
        "minors": clean_minors,
        "summary": payload["summary"],
    }


def _validate_correction_proposal(value):
    if not isinstance(value, dict):
        _fail("correction proposal must be an object")
    expected = ("title", "summary", "acceptance", "touches")
    for key in value:
        if key not in expected:
            _fail("unsupported correction proposal field: %r" % key)
    for key in expected:
        if key not in value:
            _fail("missing required correction proposal field: %r" % key)
    _nonempty_string(value.get("title"), "proposal title")
    _nonempty_string(value.get("summary"), "proposal summary")
    acceptance = value.get("acceptance")
    if not isinstance(acceptance, list) or not acceptance:
        _fail("proposal acceptance must be a nonempty array")
    for item in acceptance:
        _nonempty_string(item, "proposal acceptance entry")
    touches = value.get("touches")
    if not isinstance(touches, list):
        _fail("proposal touches must be an array")
    for item in touches:
        _nonempty_string(item, "proposal touches entry")
    return {
        "title": value["title"],
        "summary": value["summary"],
        "acceptance": list(acceptance),
        "touches": list(touches),
    }


def _validate_arbitration_proposal(value):
    if not isinstance(value, dict):
        _fail("arbitration proposal must be an object")
    for key in value:
        if key != "field_changes":
            _fail("unsupported arbitration proposal field: %r" % key)
    if "field_changes" not in value:
        _fail("arbitration proposal requires field_changes")
    changes = value["field_changes"]
    if not isinstance(changes, dict) or not changes:
        _fail("arbitration field_changes must be a nonempty object")
    for key in changes:
        if key not in ALLOWED_ARBITRATION_FIELDS:
            _fail("arbitration field %r is not permitted" % key)
    changes = {key: copy.deepcopy(item) for key, item in changes.items() if item is not None}
    if not changes:
        _fail("arbitration field_changes must change at least one field")
    return {"field_changes": changes}


def _validate_proposed_task(value):
    if not isinstance(value, dict):
        _fail("proposed task must be an object")
    expected = ("title", "summary", "acceptance")
    for key in value:
        if key not in expected:
            _fail("unsupported proposed task field: %r" % key)
    for key in expected:
        if key not in value:
            _fail("missing required proposed task field: %r" % key)
    _nonempty_string(value.get("title"), "proposed task title")
    _nonempty_string(value.get("summary"), "proposed task summary")
    acceptance = value.get("acceptance")
    if not isinstance(acceptance, list) or not acceptance:
        _fail("proposed task acceptance must be a nonempty array")
    for item in acceptance:
        _nonempty_string(item, "proposed task acceptance entry")
    return {
        "title": value["title"],
        "summary": value["summary"],
        "acceptance": list(acceptance),
    }


def _validate_closing(payload):
    if not isinstance(payload, dict):
        _fail("closing final_output must be an object")
    expected = ("verdict", "summary", "findings", "parked_minors",
                "proposed_tasks")
    for key in payload:
        if key not in expected:
            _fail("unsupported closing field: %r" % key)
    for key in expected:
        if key not in payload:
            _fail("missing required closing field: %r" % key)
    if payload.get("verdict") not in CLOSING_VERDICTS:
        _fail("closing verdict must be one of %s"
              % (list(CLOSING_VERDICTS),))
    _nonempty_string(payload.get("summary"), "closing summary")
    findings = payload.get("findings")
    parked = payload.get("parked_minors")
    proposed = payload.get("proposed_tasks")
    if not isinstance(findings, list):
        _fail("closing findings must be an array")
    if not isinstance(parked, list):
        _fail("closing parked_minors must be an array")
    if not isinstance(proposed, list):
        _fail("closing proposed_tasks must be an array")
    clean_findings = [_validate_finding(item, "closing finding")
                      for item in findings]
    clean_parked = [_validate_finding(item, "parked minor")
                    for item in parked]
    for item in clean_parked:
        if item["severity"] != "Minor":
            _fail("parked minors must be Minor")
    clean_proposed = [_validate_proposed_task(item) for item in proposed]
    if payload["verdict"] == "APPROVED":
        for item in clean_findings:
            if item["severity"] in ("Critical", "Important"):
                _fail("APPROVED closing cannot carry blocking findings")
        if clean_proposed:
            _fail("APPROVED closing cannot carry proposed tasks")
    return {
        "verdict": payload["verdict"],
        "summary": payload["summary"],
        "findings": clean_findings,
        "parked_minors": clean_parked,
        "proposed_tasks": clean_proposed,
    }


def _validate_director_proposal(payload):
    if not isinstance(payload, dict):
        _fail("director final_output must be an object")
    if "mode" in payload:
        expected = ("mode", "decision", "reason", "source_plan_hash",
                    "target_task", "proposal")
        for key in payload:
            if key not in expected:
                _fail("unsupported director field: %r" % key)
        for key in expected:
            if key not in payload:
                _fail("missing required director field: %r" % key)
        if payload.get("mode") not in DIRECTOR_MODES:
            _fail("director mode must be one of %s"
                  % (list(DIRECTOR_MODES),))
        if payload.get("decision") not in DIRECTOR_DECISIONS:
            _fail("director decision must be one of %s"
                  % (list(DIRECTOR_DECISIONS),))
        _nonempty_string(payload.get("reason"), "director reason")
        if not _is_hex64(payload.get("source_plan_hash")):
            _fail("director source_plan_hash must be 64 hex characters")
        _positive_int(payload.get("target_task"), "target_task")
        if payload["mode"] == "correction":
            proposal = _validate_correction_proposal(payload["proposal"])
        else:
            proposal = _validate_arbitration_proposal(payload["proposal"])
        return {
            "mode": payload["mode"],
            "decision": payload["decision"],
            "reason": payload["reason"],
            "source_plan_hash": payload["source_plan_hash"],
            "target_task": payload["target_task"],
            "proposal": proposal,
        }
    return _validate_closing(payload)


def _validate_semantic(role, payload, output_schema):
    if role == "operator":
        if output_schema != "operator-result-v1":
            _fail("operator role requires operator-result-v1")
        return _validate_operator(payload)
    if role == "reviewer":
        if output_schema != "reviewer-result-v1":
            _fail("reviewer role requires reviewer-result-v1")
        return _validate_reviewer(payload)
    if role == "director":
        if output_schema == "director-result-v1":
            if not isinstance(payload, dict) or "mode" not in payload:
                _fail("director-result-v1 requires a mode proposal")
            return _validate_director_proposal(payload)
        if output_schema == "closing-result-v1":
            if not isinstance(payload, dict) or "verdict" not in payload:
                _fail("closing-result-v1 requires a closing verdict")
            return _validate_closing(payload)
        _fail("director role requires director-result-v1 or "
              "closing-result-v1")
    _fail("unknown role for semantic validation: %r" % (role,))


def validate_result(value, request):
    """Strictly validate a normalized worker result against its request."""
    if not isinstance(value, dict):
        _fail("result must be an object")
    if not isinstance(request, dict):
        _fail("request must be an object")
    clean_request = validate_request(request)
    for key in value:
        if key not in RESULT_FIELDS:
            _fail("unsupported result field: %r" % key)
    for key in RESULT_FIELDS:
        if key not in value:
            _fail("missing required result field: %r" % key)
    if isinstance(value.get("version"), bool) or value.get("version") != VERSION:
        _fail("version must be exactly 1")
    if value.get("backend") not in BACKENDS:
        _fail("backend must be one of %s" % (list(BACKENDS),))
    if value.get("role") not in ROLES:
        _fail("role must be one of %s" % (list(ROLES),))
    _positive_int(value.get("task_id"), "task_id")
    _positive_int(value.get("task_family"), "task_family")
    for key in ("run_id", "dispatch_id", "episode_id", "repository_id",
                "worktree", "plan_revision", "base_commit",
                "candidate_commit", "requested_model", "requested_effort",
                "runtime_version"):
        _nonempty_string(value.get(key), key)
    if not _is_hex64(value.get("config_hash")):
        _fail("config_hash must be 64 hex characters")
    if not _is_hex64(value.get("output_hash")):
        _fail("output_hash must be 64 hex characters")
    _nonempty_string(value.get("session_id"), "session_id")
    resumed = value.get("resumed_from")
    if resumed is not None:
        _nonempty_string(resumed, "resumed_from")
    process_exit = value.get("process_exit")
    if process_exit is not None:
        if isinstance(process_exit, bool) or not isinstance(process_exit,
                                                            int):
            _fail("process_exit must be an integer or null")
    if value.get("terminal_status") not in TERMINAL_STATUSES:
        _fail("terminal_status must be one of %s"
              % (list(TERMINAL_STATUSES),))
    if value.get("output_schema") not in OUTPUT_SCHEMAS:
        _fail("output_schema must be one of %s" % (list(OUTPUT_SCHEMAS),))
    final = value.get("final_output")
    if not isinstance(final, dict):
        _fail("final_output must be an object; fragments are rejected")
    usage = _validate_usage(value.get("usage"))
    error = value.get("error")
    if error is not None and not isinstance(error, (str, dict)):
        _fail("error must be a string, an object, or null")
    for key in IDENTITY_FIELDS:
        if value[key] != clean_request[key]:
            _fail("result %s does not match the request; "
                  "stale or mismatched output" % key)
    expected_hash = _output_hash(final)
    if value["output_hash"] != expected_hash:
        _fail("output_hash does not match final_output; "
              "truncated or mismatched output")
    if value.get("terminal_status") != "completed":
        _fail("transport did not complete; semantic outcome is not valid")
    if process_exit != 0:
        _fail("transport process did not exit cleanly; "
              "semantic outcome is not valid")
    clean_semantic = _validate_semantic(value["role"], final,
                                        value["output_schema"])
    return {
        "version": VERSION,
        "backend": value["backend"],
        "run_id": value["run_id"],
        "dispatch_id": value["dispatch_id"],
        "task_id": value["task_id"],
        "task_family": value["task_family"],
        "role": value["role"],
        "episode_id": value["episode_id"],
        "repository_id": value["repository_id"],
        "worktree": value["worktree"],
        "plan_revision": value["plan_revision"],
        "base_commit": value["base_commit"],
        "candidate_commit": value["candidate_commit"],
        "requested_model": value["requested_model"],
        "requested_effort": value["requested_effort"],
        "runtime_version": value["runtime_version"],
        "config_hash": value["config_hash"],
        "session_id": value["session_id"],
        "resumed_from": value["resumed_from"],
        "process_exit": value["process_exit"],
        "terminal_status": value["terminal_status"],
        "output_schema": value["output_schema"],
        "output_hash": value["output_hash"],
        "final_output": clean_semantic,
        "usage": usage,
        "error": error,
    }


def main(argv=None):
    import argparse
    import sys
    parser = argparse.ArgumentParser(prog="dispatch_contract")
    parser.add_argument("--request", help="request file to validate")
    parser.add_argument("--result", help="result file to validate")
    parser.add_argument("--against", help="request file for result check")
    args = parser.parse_args(argv)
    try:
        if args.request:
            with open(args.request, encoding="utf-8") as handle:
                out = validate_request(json.load(handle))
            print(json.dumps(out, indent=2, sort_keys=True))
            return 0
        if args.result and args.against:
            with open(args.result, encoding="utf-8") as handle:
                result = json.load(handle)
            with open(args.against, encoding="utf-8") as handle:
                req = json.load(handle)
            out = validate_result(result, req)
            print(json.dumps(out, indent=2, sort_keys=True))
            return 0
        parser.print_usage(sys.stderr)
        return 2
    except ContractError as exc:
        print("dispatch_contract: invalid contract: %s" % exc,
              file=sys.stderr)
        return 4
    except (OSError, ValueError) as exc:
        print("dispatch_contract: cannot read input: %s" % exc,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
