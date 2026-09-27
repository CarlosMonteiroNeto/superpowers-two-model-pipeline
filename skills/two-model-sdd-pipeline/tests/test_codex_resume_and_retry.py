"""Controller-owned R2.5 acceptance tests for identity and retries."""
import importlib.util
import pathlib
import unittest

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

