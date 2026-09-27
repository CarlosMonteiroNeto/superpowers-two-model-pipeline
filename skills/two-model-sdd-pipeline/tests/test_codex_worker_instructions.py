"""R2.4 acceptance tests for role instruction delivery and protected baselines."""

import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"


def load_module(testcase, filename, name, function):
    path = SCRIPTS / filename
    testcase.assertTrue(
        path.is_file(),
        "R2.4 requires scripts/" + filename + " with " + function,
    )
    spec = importlib.util.spec_from_file_location(name, path)
    testcase.assertIsNotNone(spec)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    testcase.assertTrue(callable(getattr(module, function, None)))
    return module


def runtime():
    return {
        "backend": "codex",
        "roles": {
            role: {
                "model": "gpt-6-luna",
                "settings": {"model_reasoning_effort": "max"},
                "policy": "workspace-write" if role == "operator" else "read-only",
                "instruction": "codex-" + role + "-v1",
            }
            for role in ("operator", "reviewer", "director")
        },
    }


class CodexWorkerInstructionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="role-instructions-")
        self.root = pathlib.Path(self.temp.name) / "workspace"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(self.root), check=True, timeout=10)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(self.root), check=True, timeout=10)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=str(self.root), check=True, timeout=10)
        for name, content in (("plan.json", '{"tasks": []}\n'),
                              ("ledger.jsonl", '{"event":"start"}\n'),
                              ("runtime.json", '{"version": 1}\n')):
            (self.root / name).write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", "plan.json", "ledger.jsonl", "runtime.json"], cwd=str(self.root), check=True, timeout=10)
        subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=str(self.root), check=True, timeout=10)

    def tearDown(self):
        self.temp.cleanup()

    def build_request(self, developer_instructions):
        return {
            "developer_instructions": developer_instructions,
            "capabilities": {
                "hooks_enabled": True,
                "hooks_trusted": True,
                "sandbox_enforced": True,
                "bash_hook_covered": True,
                "apply_patch_hook_covered": True,
                "unhooked_mutating_tools": [],
                "managed_policy_conflicts": [],
                "inherited_instruction_conflicts": [],
            },
        }

    def config_value(self, argv, key):
        values = [argv[index + 1] for index, value in enumerate(argv[:-1])
                  if value in ("--config", "-c")]
        prefix = key + "="
        encoded = next(value[len(prefix):] for value in values if value.startswith(prefix))
        return json.loads(encoded)

    def test_each_codex_role_instruction_is_delivered_as_developer_context(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "build_overrides")
        instructions = {
            "operator": "RED before implementation; run scoped runners only.",
            "reviewer": "Read all evidence; return an independent structured verdict.",
            "director": "Return bounded proposals; never write authoritative state.",
        }
        for role, text in instructions.items():
            with self.subTest(role=role):
                argv = module.build_overrides(role, runtime(), self.build_request(text))
                self.assertEqual(self.config_value(argv, "developer_instructions"), text)

    def test_codex_role_instruction_transport_preserves_quotes_unicode_and_newlines(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "build_overrides")
        text = 'Run RED/GREEN for "ação".\nPath: C:\\work tree\\tests.'
        argv = module.build_overrides("operator", runtime(), self.build_request(text))
        self.assertEqual(self.config_value(argv, "developer_instructions"), text)

    def test_codex_builder_rejects_unknown_role_missing_model_or_effort(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "build_overrides")
        request = self.build_request("Role instructions")
        with self.assertRaises(module.PolicyUnavailable):
            module.build_overrides("planner", runtime(), request)
        for key in ("model", "settings"):
            broken = runtime()
            if key == "model":
                broken["roles"]["operator"].pop("model")
            else:
                broken["roles"]["operator"]["settings"].pop("model_reasoning_effort")
            with self.subTest(key=key), self.assertRaises(module.PolicyUnavailable):
                module.build_overrides("operator", broken, request)

    def test_codex_builder_refuses_a_different_backend_without_fallback(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "build_overrides")
        opencode = runtime()
        opencode["backend"] = "opencode"
        with self.assertRaises(module.PolicyUnavailable):
            module.build_overrides("operator", opencode, self.build_request("Role instructions"))

    def test_protected_state_hashes_files_without_returning_their_contents(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "capture_protected_state")
        request = {
            "workspace_root": str(self.root),
            "task_id": 7,
            "attempt_id": "attempt-2",
            "protected_paths": ["plan.json", "ledger.jsonl", "runtime.json", "not-created.json"],
        }
        baseline = module.capture_protected_state(request)
        plan_hash = "sha256:" + hashlib.sha256((self.root / "plan.json").read_bytes()).hexdigest()
        self.assertEqual(baseline["protected_files"]["plan.json"], {"exists": True, "sha256": plan_hash})
        self.assertEqual(baseline["protected_files"]["not-created.json"], {"exists": False, "sha256": None})
        self.assertNotIn("tasks", json.dumps(baseline))
        self.assertEqual(baseline["task_id"], 7)
        self.assertEqual(baseline["attempt_id"], "attempt-2")
        self.assertTrue(baseline["git_head"])
        self.assertTrue(baseline["git_status_sha256"].startswith("sha256:"))
        self.assertTrue(baseline["fingerprint"].startswith("sha256:"))

    def test_protected_state_fingerprint_changes_when_a_guarded_file_changes(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "capture_protected_state")
        request = {
            "workspace_root": str(self.root), "task_id": 7, "attempt_id": "attempt-2",
            "protected_paths": ["plan.json"],
        }
        before = module.capture_protected_state(request)
        (self.root / "plan.json").write_text('{"tasks": [1]}\n', encoding="utf-8")
        after = module.capture_protected_state(request)
        self.assertNotEqual(before["protected_files"]["plan.json"]["sha256"],
                            after["protected_files"]["plan.json"]["sha256"])
        self.assertNotEqual(before["fingerprint"], after["fingerprint"])

    def test_protected_state_fingerprint_binds_workspace_task_and_attempt(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "capture_protected_state")
        base = {
            "workspace_root": str(self.root), "task_id": 7, "attempt_id": "attempt-2",
            "protected_paths": ["plan.json"],
        }
        original = module.capture_protected_state(base)
        changed = dict(base, attempt_id="attempt-3")
        self.assertNotEqual(original["fingerprint"], module.capture_protected_state(changed)["fingerprint"])


if __name__ == "__main__":
    unittest.main()
