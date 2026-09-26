"""Black-box tests for shared invocation and semantic result schemas (Round 1 Task 3).

Contracts under test:
  skills/two-model-sdd-pipeline/scripts/dispatch_contract.py
    dispatch_contract.validate_request(value: dict) -> dict
    dispatch_contract.validate_result(value: dict, request: dict) -> dict
  skills/two-model-sdd-pipeline/schemas/worker-request.schema.json
  skills/two-model-sdd-pipeline/schemas/worker-result.schema.json
  skills/two-model-sdd-pipeline/schemas/operator-result.schema.json
  skills/two-model-sdd-pipeline/schemas/reviewer-result.schema.json
  skills/two-model-sdd-pipeline/schemas/director-result.schema.json

Acceptance encoded here (plan task 3):
  normalized invocation identity, backend, role, task/family/episode,
  worktree, candidate/base, plan revision, config/prompt hashes, requested
  settings, evidence paths, provider session and process status. Transport
  completion stays separate from semantic outcome; malformed, truncated,
  stale or mismatched output is rejected and APPROVED is never recovered
  from regex fragments. Operator DONE/DONE_WITH_CONCERNS/BLOCKED/
  NEEDS_CONTEXT/TEST_DEFECT, reviewer APPROVED/SEND_BACK/ESCALATE and
  director correction/arbitration/closing structures per the runtime spec.
  Correction routing fields (in_scope/structural/uncertain, affected paths
  and contracts) are validated without changing router behavior. Required
  types/enums, discriminated role payloads and identity consistency hold;
  both backend fixtures normalize to the same schema without treating
  backend session IDs as interchangeable. No worker process is launched and
  no existing runtime consumer switches to the unfinished contracts.

Expectations are hand-derived literals. The module runs in a fresh
interpreter per case (real behavior, no in-process imports), so a missing
module fails as an assertion on the subprocess outcome, not as a
collection error.
"""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SKILL = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
SCHEMAS = SKILL / "schemas"

REQUEST_SCHEMA = SCHEMAS / "worker-request.schema.json"
RESULT_SCHEMA = SCHEMAS / "worker-result.schema.json"
OPERATOR_SCHEMA = SCHEMAS / "operator-result.schema.json"
REVIEWER_SCHEMA = SCHEMAS / "reviewer-result.schema.json"
DIRECTOR_SCHEMA = SCHEMAS / "director-result.schema.json"
MODULE_PATH = SCRIPTS / "dispatch_contract.py"

REQUEST_SNIPPET = (
    "import sys, json; "
    "sys.path.insert(0, %r); " % str(SCRIPTS) +
    "import dispatch_contract; "
    "value = json.load(open(sys.argv[1], encoding='utf-8')); "
    "out = dispatch_contract.validate_request(value); "
    "print(json.dumps(out, sort_keys=True))"
)

RESULT_SNIPPET = (
    "import sys, json; "
    "sys.path.insert(0, %r); " % str(SCRIPTS) +
    "import dispatch_contract; "
    "value = json.load(open(sys.argv[1], encoding='utf-8')); "
    "request = json.load(open(sys.argv[2], encoding='utf-8')); "
    "out = dispatch_contract.validate_result(value, request); "
    "print(json.dumps(out, sort_keys=True))"
)


def canonical(value):
    """Independent canonical JSON (hashlib only, never the code under test)."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def output_hash_of(payload):
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def valid_request(backend="codex", role="operator"):
    if backend == "codex":
        model = "test-codex-operator-model"
        effort = "high"
    else:
        model = "test-opencode-operator-model"
        effort = "test-variant"
    if role == "reviewer":
        model = model.replace("operator", "reviewer")
    if role == "director":
        model = model.replace("operator", "director")
    return {
        "version": 1,
        "backend": backend,
        "run_id": "run-001",
        "dispatch_id": "d-001",
        "task_id": 3,
        "task_family": 3,
        "episode_id": "ep-001",
        "role": role,
        "repository_id": "repo-demo",
        "worktree": "/tmp/worktrees/task-3",
        "plan_revision": "plan-rev-001",
        "base_commit": "0123456789abcdef0123456789abcdef01234567",
        "config_hash": "a" * 64,
        "prompt_hash": "b" * 64,
        "requested_model": model,
        "requested_effort": effort,
        "evidence_paths": {
            "request_path": "attempts/3/operator/d-001/request.json",
            "prompt_path": "attempts/3/operator/d-001/prompt.md",
            "events_path": "attempts/3/operator/d-001/events.jsonl",
            "stderr_path": "attempts/3/operator/d-001/stderr.log",
            "final_path": "attempts/3/operator/d-001/final.json",
            "result_path": "attempts/3/operator/d-001/result.json",
        },
    }


def operator_payload(status="DONE"):
    concerns = []
    if status == "DONE_WITH_CONCERNS":
        concerns = ["minor drift noted"]
    return {
        "status": status,
        "summary": "implemented contracts without dispatch",
        "changed_files": [
            "skills/two-model-sdd-pipeline/scripts/dispatch_contract.py"
        ],
        "red_evidence": {
            "path": "task-3-red.txt",
            "runner": "python3 -m unittest",
            "exit_code": 1,
        },
        "concerns": concerns,
    }


def finding(severity="Minor", scope="in_scope"):
    return {
        "severity": severity,
        "file": "skills/two-model-sdd-pipeline/scripts/dispatch_contract.py",
        "line": 10,
        "issue": "missing null check",
        "fix": "add explicit null guard",
        "correction_scope": scope,
        "affected_paths": [
            "skills/two-model-sdd-pipeline/scripts/dispatch_contract.py"
        ],
        "affected_contracts": ["worker-result.schema.json"],
    }


def reviewer_payload(verdict="APPROVED"):
    if verdict == "APPROVED":
        return {
            "verdict": "APPROVED",
            "findings": [],
            "minors": [],
            "summary": "contracts match the runtime spec",
        }
    return {
        "verdict": verdict,
        "findings": [finding(severity="Important", scope="in_scope")],
        "minors": [],
        "summary": "needs correction before approval",
    }


def correction_payload():
    return {
        "mode": "correction",
        "decision": "propose",
        "reason": "follow-up task needed for router wiring",
        "source_plan_hash": "c" * 64,
        "target_task": 3,
        "proposal": {
            "title": "Wire correction routing",
            "summary": "route in-scope findings directly",
            "acceptance": ["in-scope findings skip the director"],
            "touches": ["skills/two-model-sdd-pipeline/scripts/route-next"],
        },
    }


def arbitration_payload():
    return {
        "mode": "arbitration",
        "decision": "amend",
        "reason": "scope needs a director ruling",
        "source_plan_hash": "c" * 64,
        "target_task": 3,
        "proposal": {
            "field_changes": {
                "touches": [
                    "skills/two-model-sdd-pipeline/scripts/dispatch_contract.py"
                ]
            }
        },
    }


def closing_payload(verdict="APPROVED"):
    if verdict == "APPROVED":
        return {
            "verdict": "APPROVED",
            "summary": "closing approved for candidate",
            "findings": [],
            "parked_minors": [],
            "proposed_tasks": [],
        }
    return {
        "verdict": "REOPEN",
        "summary": "reopen with one corrective task",
        "findings": [finding(severity="Important", scope="structural")],
        "parked_minors": [],
        "proposed_tasks": [
            {
                "title": "Fix stalled wave",
                "summary": "reconcile the interrupted attempt",
                "acceptance": ["attempt reconciled without replay"],
            }
        ],
    }


def valid_result(request, payload, terminal="completed", exit_code=0):
    role = request["role"]
    if role == "operator":
        schema = "operator-result-v1"
    elif role == "reviewer":
        schema = "reviewer-result-v1"
    elif request.get("_closing"):
        schema = "closing-result-v1"
    else:
        schema = "director-result-v1"
    if payload.get("verdict") in ("APPROVED", "REOPEN", "BLOCKED") and role == "director":
        schema = "closing-result-v1"
    return {
        "version": 1,
        "backend": request["backend"],
        "run_id": request["run_id"],
        "dispatch_id": request["dispatch_id"],
        "task_id": request["task_id"],
        "task_family": request["task_family"],
        "role": request["role"],
        "episode_id": request["episode_id"],
        "repository_id": request["repository_id"],
        "worktree": request["worktree"],
        "plan_revision": request["plan_revision"],
        "base_commit": request["base_commit"],
        "candidate_commit": "fedcba9876543210fedcba9876543210fedcba98",
        "requested_model": request["requested_model"],
        "requested_effort": request["requested_effort"],
        "runtime_version": "r1-test",
        "config_hash": request["config_hash"],
        "session_id": "sess-001",
        "resumed_from": None,
        "process_exit": exit_code,
        "terminal_status": terminal,
        "output_schema": schema,
        "output_hash": output_hash_of(payload),
        "final_output": payload,
        "usage": {
            "input_tokens": 10,
            "cached_tokens": 0,
            "output_tokens": 5,
        },
        "error": None,
    }


class ContractBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="foundation-contracts-")
        self.tmp = pathlib.Path(self._tmp)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def write_json(self, value, name):
        path = self.tmp / name
        path.write_text(json.dumps(value, indent=2), encoding="utf-8")
        return str(path)

    def run_request(self, value):
        path = self.write_json(value, "request.json")
        return subprocess.run(
            [sys.executable, "-c", REQUEST_SNIPPET, path],
            capture_output=True, text=True, env=dict(os.environ),
        )

    def run_result(self, value, request):
        value_path = self.write_json(value, "result.json")
        request_path = self.write_json(request, "base-request.json")
        return subprocess.run(
            [sys.executable, "-c", RESULT_SNIPPET, value_path, request_path],
            capture_output=True, text=True, env=dict(os.environ),
        )

    def request_ok(self, value):
        result = self.run_request(value)
        self.assertEqual(
            result.returncode, 0,
            "validate_request must accept the fixture: "
            + result.stdout + result.stderr,
        )
        return json.loads(result.stdout)

    def request_rejected(self, value, hint):
        result = self.run_request(value)
        self.assertNotEqual(
            result.returncode, 0,
            "validate_request must reject %s but accepted it: %s"
            % (hint, result.stdout),
        )
        return result

    def result_ok(self, value, request):
        result = self.run_result(value, request)
        self.assertEqual(
            result.returncode, 0,
            "validate_result must accept the fixture: "
            + result.stdout + result.stderr,
        )
        return json.loads(result.stdout)

    def result_rejected(self, value, request, hint):
        result = self.run_result(value, request)
        self.assertNotEqual(
            result.returncode, 0,
            "validate_result must reject %s but accepted it: %s"
            % (hint, result.stdout),
        )
        return result


class TestSchemaDocuments(ContractBase):
    def test_module_file_exists(self):
        self.assertTrue(
            MODULE_PATH.is_file(),
            "scripts/dispatch_contract.py must exist",
        )

    def test_all_five_schema_files_exist(self):
        for path in (REQUEST_SCHEMA, RESULT_SCHEMA, OPERATOR_SCHEMA,
                     REVIEWER_SCHEMA, DIRECTOR_SCHEMA):
            self.assertTrue(
                path.is_file(), "%s must exist" % path.name)

    def test_request_schema_names_identity_fields(self):
        self.assertTrue(REQUEST_SCHEMA.is_file(),
                        "worker-request.schema.json must exist")
        schema = json.loads(REQUEST_SCHEMA.read_text(encoding="utf-8"))
        required = schema.get("required", [])
        for field in ("version", "backend", "run_id", "dispatch_id",
                      "task_id", "task_family", "episode_id", "role",
                      "repository_id", "worktree", "plan_revision",
                      "base_commit", "config_hash", "prompt_hash",
                      "requested_model", "requested_effort",
                      "evidence_paths"):
            self.assertIn(field, required,
                          "request schema must require %s" % field)
        self.assertEqual(schema["properties"]["version"]["const"], 1)
        self.assertEqual(set(schema["properties"]["backend"]["enum"]),
                         {"codex", "opencode"})
        self.assertEqual(set(schema["properties"]["role"]["enum"]),
                         {"operator", "reviewer", "director"})
        self.assertFalse(schema.get("additionalProperties", True),
                         "request schema must forbid extra fields")

    def test_result_schema_names_transport_fields(self):
        self.assertTrue(RESULT_SCHEMA.is_file(),
                        "worker-result.schema.json must exist")
        schema = json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))
        required = schema.get("required", [])
        for field in ("version", "backend", "run_id", "dispatch_id",
                      "task_id", "task_family", "role", "episode_id",
                      "repository_id", "worktree", "plan_revision",
                      "base_commit", "candidate_commit", "requested_model",
                      "requested_effort", "runtime_version", "config_hash",
                      "session_id", "resumed_from", "process_exit",
                      "terminal_status", "output_schema", "output_hash",
                      "final_output", "usage", "error"):
            self.assertIn(field, required,
                          "result schema must require %s" % field)
        self.assertEqual(
            set(schema["properties"]["terminal_status"]["enum"]),
            {"completed", "failed", "interrupted", "incomplete"})
        self.assertFalse(schema.get("additionalProperties", True),
                         "result schema must forbid extra fields")

    def test_operator_schema_names_status_enum(self):
        self.assertTrue(OPERATOR_SCHEMA.is_file(),
                        "operator-result.schema.json must exist")
        schema = json.loads(OPERATOR_SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(
            set(schema["properties"]["status"]["enum"]),
            {"DONE", "DONE_WITH_CONCERNS", "BLOCKED", "NEEDS_CONTEXT",
             "TEST_DEFECT"})
        for field in ("status", "summary", "changed_files", "red_evidence",
                      "concerns"):
            self.assertIn(field, schema.get("required", []),
                          "operator schema must require %s" % field)
        self.assertFalse(schema.get("additionalProperties", True),
                         "operator schema must forbid extra fields")

    def test_reviewer_schema_names_verdict_enum(self):
        self.assertTrue(REVIEWER_SCHEMA.is_file(),
                        "reviewer-result.schema.json must exist")
        schema = json.loads(REVIEWER_SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(set(schema["properties"]["verdict"]["enum"]),
                         {"APPROVED", "SEND_BACK", "ESCALATE"})
        for field in ("verdict", "findings", "minors", "summary"):
            self.assertIn(field, schema.get("required", []),
                          "reviewer schema must require %s" % field)
        self.assertFalse(schema.get("additionalProperties", True),
                         "reviewer schema must forbid extra fields")

    def test_director_schema_covers_correction_arbitration_closing(self):
        self.assertTrue(DIRECTOR_SCHEMA.is_file(),
                        "director-result.schema.json must exist")
        text = DIRECTOR_SCHEMA.read_text(encoding="utf-8")
        schema = json.loads(text)
        blob = json.dumps(schema, sort_keys=True)
        for token in ("correction", "arbitration", "closing",
                      "source_plan_hash", "target_task", "proposal",
                      "APPROVED", "REOPEN", "BLOCKED"):
            self.assertIn(token, blob,
                          "director schema must cover %s" % token)


class TestValidateRequest(ContractBase):
    def test_valid_codex_operator_request_normalizes(self):
        out = self.request_ok(valid_request("codex", "operator"))
        self.assertEqual(out["backend"], "codex")
        self.assertEqual(out["role"], "operator")
        self.assertEqual(out["task_id"], 3)

    def test_valid_opencode_reviewer_request_normalizes(self):
        req = valid_request("opencode", "reviewer")
        out = self.request_ok(req)
        self.assertEqual(out["backend"], "opencode")
        self.assertEqual(out["role"], "reviewer")

    def test_valid_director_request_normalizes(self):
        out = self.request_ok(valid_request("codex", "director"))
        self.assertEqual(out["role"], "director")

    def test_unknown_backend_rejected(self):
        req = valid_request()
        req["backend"] = "anthropic"
        self.request_rejected(req, "an unknown backend")

    def test_unknown_role_rejected(self):
        req = valid_request()
        req["role"] = "strategist"
        self.request_rejected(req, "an unknown role")

    def test_missing_identity_field_rejected(self):
        req = valid_request()
        del req["dispatch_id"]
        self.request_rejected(req, "a missing dispatch_id")

    def test_missing_evidence_paths_rejected(self):
        req = valid_request()
        del req["evidence_paths"]
        self.request_rejected(req, "missing evidence_paths")

    def test_extra_field_rejected(self):
        req = valid_request()
        req["extra_field"] = "nope"
        self.request_rejected(req, "an extra top-level field")

    def test_wrong_version_rejected(self):
        req = valid_request()
        req["version"] = 2
        self.request_rejected(req, "version != 1")

    def test_non_integer_task_id_rejected(self):
        req = valid_request()
        req["task_id"] = "3"
        self.request_rejected(req, "a string task_id")

    def test_empty_worktree_rejected(self):
        req = valid_request()
        req["worktree"] = ""
        self.request_rejected(req, "an empty worktree")

    def test_malformed_config_hash_rejected(self):
        req = valid_request()
        req["config_hash"] = "not-a-hash"
        self.request_rejected(req, "a malformed config_hash")


class TestValidateResultTransport(ContractBase):
    def test_valid_codex_operator_result_accepted(self):
        req = self.request_ok(valid_request("codex", "operator"))
        payload = operator_payload("DONE")
        self.result_ok(valid_result(req, payload), req)

    def test_valid_opencode_operator_result_accepted(self):
        req = self.request_ok(valid_request("opencode", "operator"))
        payload = operator_payload("DONE")
        self.result_ok(valid_result(req, payload), req)

    def test_truncated_result_missing_final_output_rejected(self):
        req = self.request_ok(valid_request())
        result = valid_result(req, operator_payload("DONE"))
        del result["final_output"]
        self.result_rejected(result, req, "a truncated result")

    def test_malformed_result_with_extra_field_rejected(self):
        req = self.request_ok(valid_request())
        result = valid_result(req, operator_payload("DONE"))
        result["extra_field"] = "nope"
        self.result_rejected(result, req, "an extra transport field")

    def test_stale_plan_revision_mismatch_rejected(self):
        req = self.request_ok(valid_request())
        result = valid_result(req, operator_payload("DONE"))
        result["plan_revision"] = "plan-rev-002"
        self.result_rejected(result, req, "a stale plan_revision")

    def test_mismatched_backend_rejected(self):
        req = self.request_ok(valid_request("codex", "operator"))
        other = self.request_ok(valid_request("opencode", "operator"))
        result = valid_result(other, operator_payload("DONE"))
        # Backend/session of the other backend must not validate here.
        result["run_id"] = req["run_id"]
        result["dispatch_id"] = req["dispatch_id"]
        self.result_rejected(result, req, "a backend-mismatched result")

    def test_mismatched_role_rejected(self):
        req = self.request_ok(valid_request("codex", "operator"))
        reviewer_req = self.request_ok(valid_request("codex", "reviewer"))
        result = valid_result(reviewer_req, reviewer_payload("APPROVED"))
        self.result_rejected(result, req, "a role-mismatched result")

    def test_mismatched_dispatch_id_rejected(self):
        req = self.request_ok(valid_request())
        result = valid_result(req, operator_payload("DONE"))
        result["dispatch_id"] = "d-999"
        self.result_rejected(result, req, "a mismatched dispatch_id")

    def test_output_hash_mismatch_rejected(self):
        req = self.request_ok(valid_request())
        result = valid_result(req, operator_payload("DONE"))
        result["output_hash"] = "0" * 64
        self.result_rejected(result, req, "a mismatched output_hash")

    def test_failed_transport_cannot_carry_semantic_approval(self):
        req = self.request_ok(valid_request("codex", "reviewer"))
        result = valid_result(req, reviewer_payload("APPROVED"),
                              terminal="failed", exit_code=1)
        self.result_rejected(
            result, req, "a failed transport carrying APPROVED")

    def test_regex_fragment_string_never_recovers_approved(self):
        req = self.request_ok(valid_request("codex", "reviewer"))
        result = valid_result(req, reviewer_payload("APPROVED"))
        result["final_output"] = (
            'noise {"verdict": "APPROVED", "findings": []} trailing')
        result["output_hash"] = output_hash_of(result["final_output"])
        self.result_rejected(
            result, req, "a regex-fragment string final_output")

    def test_string_final_output_rejected_even_with_valid_hash(self):
        req = self.request_ok(valid_request("codex", "operator"))
        result = valid_result(req, operator_payload("DONE"))
        result["final_output"] = '{"status": "DONE"}'
        result["output_hash"] = output_hash_of(result["final_output"])
        self.result_rejected(result, req, "a string final_output")

    def test_unknown_terminal_status_rejected(self):
        req = self.request_ok(valid_request())
        result = valid_result(req, operator_payload("DONE"))
        result["terminal_status"] = "done"
        self.result_rejected(result, req, "an unknown terminal_status")

    def test_usage_must_carry_token_counts_or_null(self):
        req = self.request_ok(valid_request())
        result = valid_result(req, operator_payload("DONE"))
        result["usage"] = {"input_tokens": "lots",
                           "cached_tokens": 0, "output_tokens": 5}
        self.result_rejected(result, req, "malformed usage counts")


class TestOperatorSemantics(ContractBase):
    def test_each_operator_status_accepted(self):
        req = self.request_ok(valid_request("codex", "operator"))
        for status in ("DONE", "DONE_WITH_CONCERNS", "BLOCKED",
                       "NEEDS_CONTEXT", "TEST_DEFECT"):
            payload = operator_payload(status)
            self.result_ok(valid_result(req, payload), req)

    def test_unknown_operator_status_rejected(self):
        req = self.request_ok(valid_request())
        payload = operator_payload("DONE")
        payload["status"] = "APPROVED"
        self.result_rejected(valid_result(req, payload), req,
                             "an operator carrying a reviewer verdict")

    def test_operator_missing_red_evidence_rejected(self):
        req = self.request_ok(valid_request())
        payload = operator_payload("DONE")
        del payload["red_evidence"]
        self.result_rejected(valid_result(req, payload), req,
                             "an operator without red_evidence")

    def test_operator_extra_field_rejected(self):
        req = self.request_ok(valid_request())
        payload = operator_payload("DONE")
        payload["verdict"] = "APPROVED"
        self.result_rejected(valid_result(req, payload), req,
                             "an operator with a reviewer field")

    def test_done_with_concerns_requires_concerns(self):
        req = self.request_ok(valid_request())
        payload = operator_payload("DONE_WITH_CONCERNS")
        payload["concerns"] = []
        self.result_rejected(valid_result(req, payload), req,
                             "DONE_WITH_CONCERNS without concerns")

    def test_done_must_not_carry_concerns(self):
        req = self.request_ok(valid_request())
        payload = operator_payload("DONE")
        payload["concerns"] = ["late concern"]
        self.result_rejected(valid_result(req, payload), req,
                             "DONE carrying concerns")


class TestReviewerSemantics(ContractBase):
    def test_approved_without_findings_accepted(self):
        req = self.request_ok(valid_request("codex", "reviewer"))
        self.result_ok(valid_result(req, reviewer_payload("APPROVED")), req)

    def test_send_back_with_actionable_finding_accepted(self):
        req = self.request_ok(valid_request("codex", "reviewer"))
        self.result_ok(valid_result(req, reviewer_payload("SEND_BACK")), req)

    def test_escalate_with_actionable_finding_accepted(self):
        req = self.request_ok(valid_request("codex", "reviewer"))
        self.result_ok(valid_result(req, reviewer_payload("ESCALATE")), req)

    def test_approved_with_critical_finding_rejected(self):
        req = self.request_ok(valid_request("codex", "reviewer"))
        payload = reviewer_payload("APPROVED")
        payload["findings"] = [finding(severity="Critical")]
        self.result_rejected(valid_result(req, payload), req,
                             "APPROVED carrying a Critical finding")

    def test_approved_with_important_finding_rejected(self):
        req = self.request_ok(valid_request("codex", "reviewer"))
        payload = reviewer_payload("APPROVED")
        payload["findings"] = [finding(severity="Important")]
        self.result_rejected(valid_result(req, payload), req,
                             "APPROVED carrying an Important finding")

    def test_send_back_without_findings_rejected(self):
        req = self.request_ok(valid_request("codex", "reviewer"))
        payload = reviewer_payload("SEND_BACK")
        payload["findings"] = []
        self.result_rejected(valid_result(req, payload), req,
                             "SEND_BACK without findings")

    def test_finding_without_correction_scope_rejected(self):
        req = self.request_ok(valid_request("codex", "reviewer"))
        payload = reviewer_payload("SEND_BACK")
        del payload["findings"][0]["correction_scope"]
        self.result_rejected(valid_result(req, payload), req,
                             "a finding without correction_scope")

    def test_finding_with_unknown_scope_rejected(self):
        req = self.request_ok(valid_request("codex", "reviewer"))
        payload = reviewer_payload("SEND_BACK")
        payload["findings"][0]["correction_scope"] = "later"
        self.result_rejected(valid_result(req, payload), req,
                             "a finding with unknown scope")

    def test_each_correction_scope_validated(self):
        req = self.request_ok(valid_request("codex", "reviewer"))
        for scope in ("in_scope", "structural", "uncertain"):
            payload = reviewer_payload("SEND_BACK")
            payload["findings"] = [finding(severity="Important", scope=scope)]
            self.result_ok(valid_result(req, payload), req)

    def test_finding_without_affected_paths_rejected(self):
        req = self.request_ok(valid_request("codex", "reviewer"))
        payload = reviewer_payload("SEND_BACK")
        del payload["findings"][0]["affected_paths"]
        self.result_rejected(valid_result(req, payload), req,
                             "a finding without affected_paths")

    def test_finding_without_affected_contracts_rejected(self):
        req = self.request_ok(valid_request("codex", "reviewer"))
        payload = reviewer_payload("SEND_BACK")
        del payload["findings"][0]["affected_contracts"]
        self.result_rejected(valid_result(req, payload), req,
                             "a finding without affected_contracts")

    def test_minor_with_non_minor_severity_rejected(self):
        req = self.request_ok(valid_request("codex", "reviewer"))
        payload = reviewer_payload("APPROVED")
        payload["minors"] = [finding(severity="Important")]
        self.result_rejected(valid_result(req, payload), req,
                             "a parked minor that is not Minor")

    def test_reviewer_extra_field_rejected(self):
        req = self.request_ok(valid_request("codex", "reviewer"))
        payload = reviewer_payload("APPROVED")
        payload["status"] = "DONE"
        self.result_rejected(valid_result(req, payload), req,
                             "a reviewer with an operator field")

    def test_reviewer_status_payload_rejected_as_wrong_role(self):
        req = self.request_ok(valid_request("codex", "reviewer"))
        result = valid_result(req, operator_payload("DONE"))
        self.result_rejected(result, req,
                             "an operator payload under reviewer role")


class TestDirectorSemantics(ContractBase):
    def test_correction_proposal_accepted(self):
        req = self.request_ok(valid_request("codex", "director"))
        self.result_ok(valid_result(req, correction_payload()), req)

    def test_arbitration_proposal_accepted(self):
        req = self.request_ok(valid_request("codex", "director"))
        self.result_ok(valid_result(req, arbitration_payload()), req)

    def test_closing_approved_accepted(self):
        req = self.request_ok(valid_request("codex", "director"))
        self.result_ok(valid_result(req, closing_payload("APPROVED")), req)

    def test_closing_reopen_with_task_accepted(self):
        req = self.request_ok(valid_request("codex", "director"))
        self.result_ok(valid_result(req, closing_payload("REOPEN")), req)

    def test_correction_proposal_must_not_allocate_id(self):
        req = self.request_ok(valid_request("codex", "director"))
        payload = correction_payload()
        payload["proposal"]["id"] = 99
        self.result_rejected(valid_result(req, payload), req,
                             "a correction allocating its own id")

    def test_correction_without_acceptance_rejected(self):
        req = self.request_ok(valid_request("codex", "director"))
        payload = correction_payload()
        del payload["proposal"]["acceptance"]
        self.result_rejected(valid_result(req, payload), req,
                             "a correction without acceptance")

    def test_unknown_director_mode_rejected(self):
        req = self.request_ok(valid_request("codex", "director"))
        payload = correction_payload()
        payload["mode"] = "closing"
        self.result_rejected(valid_result(req, payload), req,
                             "an unknown director mode")

    def test_closing_approved_with_proposed_tasks_rejected(self):
        req = self.request_ok(valid_request("codex", "director"))
        payload = closing_payload("APPROVED")
        payload["proposed_tasks"] = [closing_payload("REOPEN")["proposed_tasks"][0]]
        self.result_rejected(valid_result(req, payload), req,
                             "APPROVED closing with proposed tasks")

    def test_closing_approved_with_blocking_finding_rejected(self):
        req = self.request_ok(valid_request("codex", "director"))
        payload = closing_payload("APPROVED")
        payload["findings"] = [finding(severity="Critical",
                                       scope="structural")]
        self.result_rejected(valid_result(req, payload), req,
                             "APPROVED closing with a blocking finding")

    def test_director_missing_source_hash_rejected(self):
        req = self.request_ok(valid_request("codex", "director"))
        payload = correction_payload()
        del payload["source_plan_hash"]
        self.result_rejected(valid_result(req, payload), req,
                             "a director proposal without source hash")


class TestIdentityAndSeparation(ContractBase):
    def test_both_backends_normalize_to_same_schema(self):
        codex_req = self.request_ok(valid_request("codex", "operator"))
        opencode_req = self.request_ok(valid_request("opencode", "operator"))
        self.assertEqual(set(codex_req), set(opencode_req),
                         "both backends must normalize to the same keys")
        codex_res = self.result_ok(
            valid_result(codex_req, operator_payload("DONE")), codex_req)
        opencode_res = self.result_ok(
            valid_result(opencode_req, operator_payload("DONE")),
            opencode_req)
        self.assertEqual(set(codex_res), set(opencode_res),
                         "both backends must share the result shape")

    def test_backend_session_ids_are_not_interchangeable(self):
        codex_req = self.request_ok(valid_request("codex", "operator"))
        opencode_req = self.request_ok(valid_request("opencode", "operator"))
        codex_res = valid_result(codex_req, operator_payload("DONE"))
        codex_res["session_id"] = "shared-session-001"
        opencode_res = valid_result(opencode_req, operator_payload("DONE"))
        opencode_res["session_id"] = "shared-session-001"
        self.result_rejected(codex_res, opencode_req,
                             "a codex session used for an opencode request")
        self.result_rejected(opencode_res, codex_req,
                             "an opencode session used for a codex request")

    def test_operator_and_reviewer_sessions_never_swap_roles(self):
        op_req = self.request_ok(valid_request("codex", "operator"))
        rev_req = self.request_ok(valid_request("codex", "reviewer"))
        op_res = valid_result(op_req, operator_payload("DONE"))
        rev_res = valid_result(rev_req, reviewer_payload("APPROVED"))
        # Same provider session string, but roles still discriminate.
        op_res["session_id"] = "sess-shared-001"
        rev_res["session_id"] = "sess-shared-001"
        self.result_rejected(op_res, rev_req,
                             "an operator session used as reviewer output")
        self.result_rejected(rev_res, op_req,
                             "a reviewer session used as operator output")


class TestNoDispatchSideEffects(ContractBase):
    def test_module_launches_no_worker_process(self):
        self.assertTrue(MODULE_PATH.is_file(),
                        "scripts/dispatch_contract.py must exist")
        text = MODULE_PATH.read_text(encoding="utf-8")
        for token in ("subprocess", "Popen", "os.system", "os.exec",
                      "codex exec", "opencode run"):
            self.assertNotIn(token, text,
                             "dispatch_contract must not launch workers")

    def test_validation_creates_no_attempt_files(self):
        req = valid_request()
        before = set(path.name for path in self.tmp.iterdir())
        result = self.run_request(req)
        self.assertEqual(result.returncode, 0,
                         "fixture must validate: " + result.stderr)
        after = set(path.name for path in self.tmp.iterdir())
        # Only the harness-written request.json may appear; no attempts/ dir.
        self.assertFalse((self.tmp / "attempts").exists(),
                         "validation must not create attempt directories")
        self.assertTrue(after.issuperset(before))

    def test_existing_consumers_do_not_import_unfinished_contracts(self):
        consumers = ["dispatch", "dispatch-retry", "route-next",
                     "coder-gate", "run-gates", "review-package"]
        for name in consumers:
            path = SCRIPTS / name
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            self.assertNotIn("dispatch_contract", text,
                             "%s must not switch to unfinished contracts"
                             % name)


if __name__ == "__main__":
    unittest.main()
