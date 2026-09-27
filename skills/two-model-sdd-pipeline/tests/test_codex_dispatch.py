"""Controller-owned R2.5 acceptance tests for native Codex dispatch."""
import importlib.util
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


class CodexDispatchTests(unittest.TestCase):
    def test_dispatch_module_exposes_public_entrypoint(self):
        load(self, "codex_dispatch.py", "run_dispatch")

    def test_process_module_exposes_owned_capture_and_cancellation(self):
        process = load(self, "codex_process.py", "run_owned")
        self.assertTrue(callable(getattr(process, "stop_owned_processes", None)))

    def test_backend_registry_requires_explicit_known_backend(self):
        registry = load(self, "backend_registry.py", "resolve")
        for backend in ("codex", "opencode"):
            self.assertIsNotNone(registry.resolve(backend))
        with self.assertRaises((ValueError, KeyError)):
            registry.resolve("typo")

    def test_codex_adapter_injects_runtime_without_polluting_strict_request(self):
        registry = load(self, "backend_registry.py", "resolve")
        request = {"backend": "codex", "version": 1}
        runtime = {"manifest": {"backend": "codex"}}
        with mock.patch.dict("sys.modules") as modules:
            fake = mock.Mock()
            modules["codex_dispatch"] = fake
            adapter = registry.resolve("codex", runtime=runtime)
            adapter.invoke(request)
            fake.run_dispatch.assert_called_once_with(request, runtime)

    def test_opencode_cancel_does_not_route_to_codex_process_killer(self):
        registry = load(self, "backend_registry.py", "resolve")
        adapter = registry.resolve("opencode")
        with mock.patch.dict("sys.modules") as modules:
            modules["codex_process"] = mock.Mock()
            adapter.cancel({"processes": []})
            modules["codex_process"].stop_owned_processes.assert_not_called()

    def test_dispatch_entrypoint_and_codex_adapter_exist(self):
        self.assertTrue((SCRIPTS / "dispatch-codex").is_file())
        self.assertTrue((SCRIPTS / "dispatch-opencode").is_file())
