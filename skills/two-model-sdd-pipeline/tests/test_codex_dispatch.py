"""Controller-owned R2.5 acceptance tests for native Codex dispatch."""
import importlib.util
import json
import pathlib
import hashlib
import os
import shutil
import subprocess
import sys
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

    def test_preexecution_launch_failure_uses_retryable_exit_five(self):
        bash = shutil.which("bash")
        if os.name == "nt":
            git_bash = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
            bash = str(git_bash) if git_bash.exists() else bash
        if not bash:
            self.skipTest("Bash is required for dispatch wrapper contract")
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            prompt = root / "prompt.md"
            prompt.write_text("prompt", encoding="utf-8")
            paths = {key: str(root / value) for key, value in (
                ("request_path", "request.json"), ("prompt_path", "prompt.md"),
                ("events_path", "events.jsonl"), ("stderr_path", "stderr.log"),
                ("final_path", "final.json"), ("result_path", "result.json"))}
            request = {"version":1,"backend":"codex","run_id":"r","dispatch_id":"d",
                "task_id":1,"task_family":1,"episode_id":"e","role":"operator",
                "repository_id":"repo","worktree":directory,"plan_revision":"p",
                "base_commit":"a"*40,"config_hash":"b"*64,
                "prompt_hash":hashlib.sha256(b"prompt").hexdigest(),
                "requested_model":"m","requested_effort":"medium","evidence_paths":paths}
            capabilities = {k:True for k in ("hooks_enabled","hooks_trusted","sandbox_enforced","bash_hook_covered","apply_patch_hook_covered")}
            capabilities.update({k:[] for k in ("unhooked_mutating_tools","managed_policy_conflicts","inherited_instruction_conflicts")})
            runtime = {"manifest":{"backend":"codex","version":"test","roles":{"operator":{
                "model":"m","settings":{"model_reasoning_effort":"medium"},"policy":"workspace-write","instruction":"operator"}}},
                "capabilities":capabilities,"developer_instructions":"instructions",
                "executable":["definitely-missing-codex-executable-r25"]}
            request_path, runtime_path = root / "request.json", root / "runtime.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            runtime_path.write_text(json.dumps(runtime), encoding="utf-8")
            env = dict(os.environ, CODEX_RUNTIME_JSON=str(runtime_path))
            result = subprocess.run([bash, str(SCRIPTS / "dispatch-codex"), "--request", str(request_path)],
                                    cwd=str(root), env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
