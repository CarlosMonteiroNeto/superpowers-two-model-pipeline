"""Controller-owned R3.2 review retry and candidate binding tests."""
import importlib.util
import pathlib
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
        "attempt_base": "b" * 40, "context_hash": "d" * 64}


def runtime():
    return {"manifest": {"backend": "codex", "version": "test", "roles": {
        "reviewer": {"model": "gpt-6-luna", "settings": {"model_reasoning_effort": "medium"},
            "policy": "read-only"}}}, "capabilities": {}}


def finding():
    return {"severity": "Important", "file": "src/example.py", "line": 4,
        "issue": "missing guard", "fix": "add guard", "correction_scope": "in_scope",
        "affected_paths": ["src/example.py"], "affected_contracts": ["safe input"]}


class ReviewRecoveryTests(unittest.TestCase):
    def test_failed_review_dispatch_stays_pending_and_retry_reuses_same_candidate(self):
        module = load(self)
        req = request()
        env = runtime()
        with mock.patch.object(module.codex_dispatch, "run_dispatch", side_effect=[
                OSError("review transport unavailable"),
                {"role": "reviewer", "run_id": "run-a", "task_id": 2,
                 "task_family": 2, "base_commit": "b" * 40, "candidate_commit": "a" * 40,
                 "final_output": {"verdict": "APPROVED", "findings": [], "minors": [], "summary": "approved"}}]) as dispatch:
            pending = module.ensure_review(req, env)
            self.assertEqual(pending["status"], "review_pending")
            approved = module.ensure_review(req, env)
            self.assertEqual(approved["verdict"], "APPROVED")
            self.assertEqual(dispatch.call_count, 2)
            self.assertEqual(dispatch.call_args_list[0].args[0]["candidate_commit"], "a" * 40)
            self.assertEqual(dispatch.call_args_list[1].args[0]["candidate_commit"], "a" * 40)

    def test_completed_verdict_for_old_candidate_is_not_reused(self):
        module = load(self)
        req = request()
        old = {"role": "reviewer", "run_id": "run-a", "task_id": 2,
            "task_family": 2, "base_commit": "b" * 40, "candidate_commit": "e" * 40,
            "final_output": {"verdict": "APPROVED", "findings": [], "minors": [], "summary": "approved"}}
        with mock.patch.object(module, "load_review_result", return_value=old), \
             mock.patch.object(module.codex_dispatch, "run_dispatch", return_value={
                "role": "reviewer", "run_id": "run-a", "task_id": 2, "task_family": 2,
                "base_commit": "b" * 40, "candidate_commit": "a" * 40,
                "final_output": {"verdict": "SEND_BACK", "findings": [finding()], "minors": [], "summary": "revise"}}) as dispatch:
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
