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
import importlib.util

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
    def test_director_schema_is_selected_by_episode_mode(self):
        module = load(self, "codex_dispatch.py", "_structured_schema_path")
        correction = module._structured_schema_path({"role":"director","episode_id":"run-family-2-correction"}, {})
        arbitration = module._structured_schema_path({"role":"director","episode_id":"run-family-2-arbitration"}, {})
        closing = module._structured_schema_path({"role":"director","episode_id":"run-closing-1"}, {})
        self.assertEqual(pathlib.Path(correction).name, "director-result.schema.json")
        self.assertEqual(pathlib.Path(arbitration).name, "director-arbitration.schema.json")
        self.assertEqual(pathlib.Path(closing).name, "closing-result.schema.json")

    def test_request_dispatch_publishes_normalized_result_to_caller_path(self):
        module = load(self, "codex_dispatch.py", "publish_requested_result")
        with tempfile.TemporaryDirectory() as temp:
            target = pathlib.Path(temp) / "attempt" / "result.json"
            request = {"evidence_paths":{"result_path":str(target)}}
            result = {"role":"director", "terminal_status":"completed"}
            module.publish_requested_result(request, result)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), result)

    def test_normalized_director_output_hash_excludes_null_schema_slots(self):
        module = load(self, "codex_dispatch.py", "normalized_output_and_hash")
        raw={"mode":"arbitration","decision":"amend","reason":"narrow scope",
            "source_plan_hash":"a"*64,"target_task":2,
            "proposal":{"field_changes":{"touches":["src/beta.py"],"acceptance":None,
                "summary":None,"title":None}}}
        normalized,digest=module.normalized_output_and_hash("director",raw,"director-result-v1")
        self.assertEqual(normalized["proposal"]["field_changes"],{"touches":["src/beta.py"]})
        self.assertEqual(digest,hashlib.sha256(json.dumps(normalized,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")).hexdigest())

    def test_start_identity_timeout_terminates_the_spawned_child_tree(self):
        module = load(self, "codex_process.py", "run_owned")
        spec = importlib.util.spec_from_file_location(
            "codex_process_launch_failure", SCRIPTS / "codex_process.py")
        process_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(process_module)
        child = mock.Mock(pid=321)
        with mock.patch.object(process_module.subprocess, "Popen", return_value=child), \
             mock.patch.object(process_module, "_start_identity",
                               side_effect=subprocess.TimeoutExpired("powershell", 5)), \
             mock.patch.object(process_module, "_kill_unverified_child") as stop:
            with self.assertRaisesRegex(RuntimeError, "could not verify process start identity"):
                process_module.run_owned(["fake-codex"], ".")
        stop.assert_called_once_with(child)

    def test_stop_owned_windows_process_uses_verified_pid(self):
        spec = importlib.util.spec_from_file_location(
            "codex_process_stop_windows", SCRIPTS / "codex_process.py")
        process_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(process_module)
        record = {"pid": 321, "start_identity": "verified-start"}
        with mock.patch.object(process_module.os, "name", "nt"), \
             mock.patch.object(process_module, "_start_identity",
                               side_effect=["verified-start", None, None]), \
             mock.patch.object(process_module.subprocess, "run",
                               return_value=subprocess.CompletedProcess([], 0)) as run:
            process_module.stop_owned_processes([record], 0)
        run.assert_called_once_with(
            ["taskkill", "/PID", "321", "/T", "/F"],
            capture_output=True, timeout=1)

    def test_dispatch_module_exposes_public_entrypoint(self):
        module = load(self, "codex_dispatch.py", "run_dispatch")
        self.assertEqual(
            module.ledger_append_script(str(SCRIPTS)),
            str(SCRIPTS / "ledger-append"),
        )
        command = module.ledger_append_argv("ledger-append", ["ledger.jsonl", "task_complete"] , platform="nt")
        self.assertEqual(command, ["bash", "ledger-append", "ledger.jsonl", "task_complete"])

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
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Acceptance"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "acceptance@example.invalid"], check=True)
            prompt = root / "prompt.md"
            prompt.write_text("prompt", encoding="utf-8")
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps({"tasks":[{"id":1,"touches":[],"verification":{}}]}), encoding="utf-8")
            evidence = root / ".superpowers" / "dispatch" / "family" / "operator" / "dispatch"
            paths = {key: str(evidence / value) for key, value in (
                ("request_path", "request.json"), ("events_path", "events.jsonl"),
                ("stderr_path", "stderr.log"), ("final_path", "final.json"),
                ("result_path", "result.json"))}
            paths["prompt_path"] = str(root / "prompt.md")
            request = {"version":1,"backend":"codex","run_id":"r","dispatch_id":"d",
                "task_id":1,"task_family":1,"episode_id":"e","role":"operator",
                "repository_id":"repo","worktree":directory,"plan_revision":hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                "base_commit":"a"*40,"config_hash":"b"*64,
                "prompt_hash":hashlib.sha256(b"prompt").hexdigest(),
                "requested_model":"m","requested_effort":"medium","evidence_paths":paths}
            capabilities = {k:True for k in ("hooks_enabled","hooks_trusted","sandbox_enforced","bash_hook_covered","apply_patch_hook_covered")}
            capabilities.update({k:[] for k in ("unhooked_mutating_tools","managed_policy_conflicts","inherited_instruction_conflicts")})
            runtime = {"manifest":{"backend":"codex","version":"test","roles":{"operator":{
                "model":"m","settings":{"model_reasoning_effort":"medium"},"policy":"workspace-write","instruction":"operator"}}},
                "capabilities":capabilities,"developer_instructions":"instructions",
                "executable":["definitely-missing-codex-executable-r25"]}
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
            request_path, runtime_path = root / "request.json", root / "runtime.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            runtime_path.write_text(json.dumps(runtime), encoding="utf-8")
            env = dict(os.environ, CODEX_RUNTIME_JSON=str(runtime_path))
            result = subprocess.run([bash, str(SCRIPTS / "dispatch-codex"), "--request", str(request_path)],
                                    cwd=str(root), env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)

    def test_legacy_operator_request_hash_matches_crlf_prompt_text(self):
        bash = shutil.which("bash")
        if os.name == "nt":
            git_bash = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
            bash = str(git_bash) if git_bash.exists() else bash
        if not bash:
            self.skipTest("Bash is required for dispatch wrapper contract")
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Acceptance"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "acceptance@example.invalid"], check=True)
            workspace = root / ".superpowers" / "two-model" / "run"
            workspace.mkdir(parents=True)
            plan_path = workspace / "plan.json"
            plan_path.write_text(json.dumps({"tasks": [{"id": 1, "touches": ["src/a.py"],
                                                         "verification": {}}]}), encoding="utf-8")
            identity = {"run_id": "run", "repository_id": "repo"}
            (workspace / ".pipeline-identity.json").write_text(json.dumps(identity), encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "a.py").write_text("", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
            prompt = workspace / "task-1-brief.md"
            prompt.write_bytes(b"# CRLF brief\r\n")
            missing = "definitely-missing-codex-executable-r3"
            runtime = {
                "manifest": {"backend": "codex", "config_hash": "c" * 64,
                    "roles": {"operator": {"model": "m",
                        "settings": {"model_reasoning_effort": "medium"},
                        "policy": "workspace-write"}}},
                "capabilities": {key: True for key in (
                    "hooks_enabled", "hooks_trusted", "sandbox_enforced",
                    "bash_hook_covered", "apply_patch_hook_covered")},
                "developer_instructions": "instructions",
                "executable": [missing],
            }
            for key in ("unhooked_mutating_tools", "managed_policy_conflicts",
                        "inherited_instruction_conflicts"):
                runtime["capabilities"][key] = []
            runtime_path = root / "runtime.json"
            runtime_path.write_text(json.dumps(runtime), encoding="utf-8")
            env = dict(os.environ, CODEX_RUNTIME_JSON=str(runtime_path))
            result = subprocess.run([
                bash, str(SCRIPTS / "dispatch-codex"), "--agent", "two-model-coder",
                "--task", "1", "--prompt-file", str(prompt), "--log",
                str(workspace / "task-1-coder.log"),
            ], cwd=str(root), env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            self.assertNotIn("prompt hash mismatch", result.stderr)
