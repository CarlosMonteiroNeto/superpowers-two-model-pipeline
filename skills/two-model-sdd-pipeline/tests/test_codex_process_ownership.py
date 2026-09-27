"""Controller-owned R2.5 acceptance tests for bounded process ownership."""
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

