"""Controller-owned R3.2 review retry and candidate binding tests."""
import importlib.util
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"


def load(test):
    path = SCRIPTS / "review_dispatch.py"
    test.assertTrue(path.is_file(), "R3.2 requires scripts/review_dispatch.py")
    spec = importlib.util.spec_from_file_location("r32_review_dispatch", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    test.assertTrue(callable(getattr(module, "ensure_review", None)))
    return module


def request():
    return {"version": 1, "backend": "codex", "run_id": "run-a", "dispatch_id": "review-1",
        "task_id": 2, "task_family": 2, "role": "reviewer", "episode_id": "ep-1",
        "repository_id": "repo", "worktree": "C:/repo", "plan_revision": "plan-hash",
        "base_commit": "b" * 40, "candidate_commit": "a" * 40,
        "requested_model": "gpt-6-luna", "requested_effort": "medium", "config_hash": "c" * 64,
        "prompt_hash": "d" * 64,
        "evidence_paths": {key: "C:/repo/{}.json".format(key) for key in
            ("request_path", "prompt_path", "events_path", "stderr_path", "final_path", "result_path")},
        "attempt_base": "b" * 40, "context_hash": "e" * 64}


def runtime():
    return {"manifest": {"backend": "codex", "version": "test", "roles": {
        "reviewer": {"model": "gpt-6-luna", "settings": {"model_reasoning_effort": "medium"},
            "policy": "read-only"}}}, "capabilities": {}}


def finding():
    return {"severity": "Important", "file": "src/example.py", "line": 4,
        "issue": "missing guard", "fix": "add guard", "correction_scope": "in_scope",
        "affected_paths": ["src/example.py"], "affected_contracts": ["safe input"]}


def normalized_result(req, semantic, candidate=None):
    value = {key: req[key] for key in ("version", "backend", "run_id", "dispatch_id", "task_id",
        "task_family", "episode_id", "role", "repository_id", "worktree", "plan_revision", "base_commit",
        "requested_model", "requested_effort", "config_hash")}
    value.update(candidate_commit=candidate or req["candidate_commit"], runtime_version="test", session_id="review-session",
        resumed_from=None, process_exit=0, terminal_status="completed", output_schema="reviewer-result-v1",
        final_output=semantic, usage={"input_tokens":1,"cached_tokens":0,"output_tokens":1}, error=None)
    payload = json.dumps(semantic, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    value["output_hash"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return value


class ReviewRecoveryTests(unittest.TestCase):
    def test_codex_review_parser_cli_accepts_normalized_result_and_request(self):
        req = request()
        result = normalized_result(req, {
            "verdict": "APPROVED", "findings": [], "minors": [], "summary": "approved",
        })
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            result_path = root / "result.json"
            request_path = root / "request.json"
            output_path = root / "review.json"
            result_path.write_text(json.dumps(result), encoding="utf-8")
            request_path.write_text(json.dumps(req), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS / "parse_review.py"), "--backend", "codex",
                 str(result_path), str(request_path), str(output_path)],
                capture_output=True, text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["verdict"], "APPROVED")

    def test_reviewer_prompt_hash_matches_text_read_on_windows(self):
        module = load(self)
        prompt = pathlib.Path(__file__).with_name("review-prompt-crlf.tmp")
        try:
            prompt.write_bytes(b"line one\r\nline two\r\n")
            expected = hashlib.sha256(b"line one\nline two\n").hexdigest()
            self.assertEqual(module._prompt_sha(prompt), expected)
        finally:
            prompt.unlink(missing_ok=True)

    def test_failed_review_dispatch_stays_pending_and_retry_reuses_same_candidate(self):
        module = load(self)
        req = request()
        env = runtime()
        with mock.patch.object(module.codex_dispatch, "run_dispatch", side_effect=[
                OSError("review transport unavailable"),
                normalized_result(req, {"verdict": "APPROVED", "findings": [], "minors": [], "summary": "approved"})]) as dispatch:
            pending = module.ensure_review(req, env)
            self.assertEqual(pending["status"], "review_pending")
            approved = module.ensure_review(req, env)
            self.assertEqual(approved["verdict"], "APPROVED")
            self.assertEqual(dispatch.call_count, 2)
            self.assertEqual(dispatch.call_args_list[0].args[0]["base_commit"], "b" * 40)
            self.assertEqual(dispatch.call_args_list[1].args[0]["base_commit"], "b" * 40)
            self.assertEqual(dispatch.call_args_list[1].args[0]["dispatch_id"], req["dispatch_id"])

    def test_failed_review_preserves_candidate_identity_for_resume(self):
        module = load(self)
        req = request()
        with tempfile.TemporaryDirectory() as temp:
            state_path = pathlib.Path(temp) / "review-state.json"
            original = {"base_commit": req["base_commit"],
                        "candidate_commit": req["candidate_commit"],
                        "plan_hash": "plan", "context_hash": "context"}
            state_path.write_text(json.dumps(original), encoding="utf-8")
            req["review_state_path"] = str(state_path)
            with mock.patch.object(module.codex_dispatch, "run_dispatch",
                                   side_effect=OSError("review transport unavailable")):
                result = module.ensure_review(req, runtime())
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "review_pending")
            self.assertEqual(state["base_commit"], original["base_commit"])
            self.assertEqual(state["candidate_commit"], original["candidate_commit"])
            self.assertEqual(state["plan_hash"], "plan")
            self.assertEqual(state["context_hash"], "context")
            self.assertEqual(state["status"], "review_pending")

    def test_completed_verdict_for_old_candidate_is_not_reused(self):
        module = load(self)
        req = request()
        old = normalized_result(req, {"verdict": "APPROVED", "findings": [], "minors": [], "summary": "approved"}, candidate="e" * 40)
        with mock.patch.object(module, "load_review_result", return_value=old), \
             mock.patch.object(module.codex_dispatch, "run_dispatch", return_value=normalized_result(req,
                {"verdict": "SEND_BACK", "findings": [finding()], "minors": [], "summary": "revise"})) as dispatch:
            result = module.ensure_review(req, runtime())
        dispatch.assert_called_once()
        self.assertEqual(result["verdict"], "SEND_BACK")

    def test_matching_but_incomplete_normalized_envelope_is_rejected(self):
        module = load(self)
        req = request()
        partial = {"role": "reviewer", "run_id": "run-a", "task_id": 2,
            "task_family": 2, "base_commit": "b" * 40, "candidate_commit": "a" * 40,
            "final_output": {"verdict": "APPROVED", "findings": [], "minors": [], "summary": "approved"}}
        with mock.patch.object(module, "load_review_result", return_value=partial), \
             mock.patch.object(module.codex_dispatch, "run_dispatch", side_effect=OSError("unavailable")) as dispatch:
            result = module.ensure_review(req, runtime())
        dispatch.assert_called_once()
        self.assertEqual(result["status"], "review_pending")
