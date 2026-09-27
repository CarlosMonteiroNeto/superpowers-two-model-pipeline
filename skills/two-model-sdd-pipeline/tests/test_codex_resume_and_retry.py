"""Controller-owned R2.5 acceptance tests for identity and retries."""
import importlib.util
import hashlib
import json
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"


def load(test, filename, function):
    path = SCRIPTS / filename
    test.assertTrue(path.is_file(), "R2.5 requires scripts/" + filename)
    spec = importlib.util.spec_from_file_location("r25_" + filename.replace(".", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    test.assertTrue(callable(getattr(module, function, None)))
    return module


class ResumeRetryTests(unittest.TestCase):
    def dispatch_fixture(self, directory):
        prompt = pathlib.Path(directory) / "prompt.md"
        prompt.write_text("Role prompt", encoding="utf-8")
        paths = {key: str(pathlib.Path(directory) / name) for key, name in (
            ("request_path", "request.json"), ("prompt_path", "prompt.md"),
            ("events_path", "events.jsonl"), ("stderr_path", "stderr.log"),
            ("final_path", "final.json"), ("result_path", "result.json"))}
        request = {"version": 1, "backend": "codex", "run_id": "r", "dispatch_id": "d",
            "task_id": 1, "task_family": 1, "episode_id": "e", "role": "operator",
            "repository_id": "repo", "worktree": str(directory), "plan_revision": "p",
            "base_commit": "a" * 40, "config_hash": "b" * 64,
            "prompt_hash": hashlib.sha256(b"Role prompt").hexdigest(),
            "requested_model": "request-model", "requested_effort": "high", "evidence_paths": paths}
        capabilities = {key: True for key in ("hooks_enabled", "hooks_trusted", "sandbox_enforced", "bash_hook_covered", "apply_patch_hook_covered")}
        capabilities.update({key: [] for key in ("unhooked_mutating_tools", "managed_policy_conflicts", "inherited_instruction_conflicts")})
        runtime = {"manifest": {"backend": "codex", "version": "test", "roles": {
                "operator": {"model": "manifest-model", "settings": {"model_reasoning_effort": "medium"},
                    "policy": "workspace-write", "instruction": "operator"}}},
            "capabilities": capabilities, "developer_instructions": "instructions",
            "executable": ["fake-codex"], "attempt_root": str(pathlib.Path(directory) / "attempts")}
        return request, runtime

    def test_session_store_exposes_load_and_store(self):
        sessions = load(self, "codex_sessions.py", "load_session")
        self.assertTrue(callable(getattr(sessions, "store_session", None)))

    def test_retry_policy_is_a_separate_classified_entrypoint(self):
        retry = load(self, "dispatch_retry.py", "retry_decision")
        self.assertTrue(callable(retry.retry_decision))

    def test_dispatch_never_resumes_without_explicit_session_id(self):
        dispatch = load(self, "codex_dispatch.py", "run_dispatch")
        with self.assertRaises((ValueError, TypeError, OSError)):
            dispatch.run_dispatch({}, {"resume": True})

    def test_session_cleanup_entrypoint_exists(self):
        self.assertTrue((SCRIPTS / "session-clean").is_file())

    def test_retry_policy_retries_only_preexec_code_five_twice(self):
        retry = load(self, "dispatch_retry.py", "retry_decision")
        self.assertEqual(retry.retry_decision(5, 1, started=False),
                         {"retry": True, "delay_seconds": 1, "reason": "confirmed_pre_exec_transient"})
        self.assertEqual(retry.retry_decision(5, 2, started=False)["delay_seconds"], 3)
        self.assertFalse(retry.retry_decision(5, 3, started=False)["retry"])
        for code in (2, 3, 4, 6, 130, 124):
            self.assertFalse(retry.retry_decision(code, 1, started=False)["retry"], code)
        self.assertFalse(retry.retry_decision(5, 1, started=True)["retry"])

    def test_request_model_cannot_override_manifest_role_model_or_effort(self):
        dispatch = load(self, "codex_dispatch.py", "run_dispatch")
        with tempfile.TemporaryDirectory() as directory:
            request, runtime = self.dispatch_fixture(directory)
            with mock.patch.object(dispatch.codex_process, "run_owned") as run:
                with self.assertRaises(Exception):
                    dispatch.run_dispatch(request, runtime)
                run.assert_not_called()

    def test_resume_id_always_requires_explicit_identity_bound_resume(self):
        dispatch = load(self, "codex_dispatch.py", "run_dispatch")
        with tempfile.TemporaryDirectory() as directory:
            request, runtime = self.dispatch_fixture(directory)
            runtime["resume_session_id"] = "unrelated-session"
            with mock.patch.object(dispatch.codex_process, "run_owned") as run:
                with self.assertRaises(Exception):
                    dispatch.run_dispatch(request, runtime)
                run.assert_not_called()
