"""Controller-owned R2.5 acceptance tests for bounded process ownership."""
import importlib.util
import pathlib
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


class ProcessOwnershipTests(unittest.TestCase):
    def test_run_owned_returns_process_identity_and_separate_streams(self):
        process = load(self, "codex_process.py", "run_owned")
        self.assertTrue(callable(process.run_owned))

    def test_cancel_requires_recorded_ownership_and_bounded_grace(self):
        process = load(self, "codex_process.py", "stop_owned_processes")
        with self.assertRaises((ValueError, TypeError)):
            process.stop_owned_processes([], -1)

    def test_cleanup_is_adapter_scoped(self):
        registry = load(self, "backend_registry.py", "resolve")
        self.assertIsNotNone(registry.resolve("codex"))
        self.assertIsNotNone(registry.resolve("opencode"))

    def test_timeout_cancellation_uses_verified_start_identity(self):
        process = load(self, "codex_process.py", "run_owned")
        fake = mock.Mock()
        fake.pid = 123
        fake.returncode = -9
        fake.communicate.side_effect = [__import__("subprocess").TimeoutExpired(["fake"], 0.01), (b"", b"")]
        with mock.patch.object(process.subprocess, "Popen", return_value=fake), \
             mock.patch.object(process, "_start_identity", return_value="start-123"), \
             mock.patch.object(process, "stop_owned_processes") as stop:
            process.run_owned(["fake"], ".", timeout=0.01)
        self.assertEqual(stop.call_args.args[0], [{"pid": 123, "start_identity": "start-123"}])
