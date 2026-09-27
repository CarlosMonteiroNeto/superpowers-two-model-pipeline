"""R2.4 acceptance tests for Codex and OpenCode tool policies."""

import importlib.util
import json
import os
import pathlib
import shlex
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


def codex_runtime():
    roles = {}
    for role, policy in (("operator", "workspace-write"),
                         ("reviewer", "read-only"),
                         ("director", "read-only")):
        roles[role] = {
            "model": "gpt-6-luna",
            "settings": {"model_reasoning_effort": "max"},
            "policy": policy,
            "instruction": "codex-" + role + "-v1",
        }
    return {"backend": "codex", "roles": roles}


def opencode_runtime():
    roles = {}
    for role, mode in (("operator", "build"),
                       ("reviewer", "review"),
                       ("director", "director")):
        roles[role] = {
            "model": "openai/gpt-6-luna",
            "settings": {"variant": "max", "agent": mode},
            "policy": "workspace-write" if role == "operator" else "read-only",
            "instruction": "opencode-" + role + "-v1",
        }
    return {"backend": "opencode", "roles": roles}


def codex_request():
    return {
        "developer_instructions": "Role instructions: preserve RED, GREEN, and TEST_DEFECT.\nKeep \"quoted\" paths and C:\\workspace intact.",
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


class CodexRolePolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="r2.4-ação com espaço-")
        self.workspace = pathlib.Path(self.temp.name) / "repo with espaço"
        self.workspace.mkdir()
        (self.workspace / "src").mkdir()
        (self.workspace / "tests").mkdir()
        (self.workspace / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def policy(self, role="operator"):
        runner = [
            sys.executable,
            str(SCRIPTS / "scoped-run"),
            str(self.workspace),
            "7",
            "test",
        ]
        return {
            "role": role,
            "workspace_root": str(self.workspace),
            "task_id": 7,
            "task_family_id": "family-7",
            "attempt_id": "attempt-2",
            "touches": ["src/app.py"],
            "new_test_files": ["tests/test_app.py"],
            "protected_paths": ["plan.json", ".superpowers/ledger.jsonl", "runtime.json"],
            "runner_commands": {
                "red": {"argv": runner[:-1] + ["red"], "cwd": str(self.workspace)},
                "test": {"argv": runner, "cwd": str(self.workspace)},
                "analyze": {"argv": runner[:-1] + ["analyze"], "cwd": str(self.workspace)},
                "format": {"argv": runner[:-1] + ["format"], "cwd": str(self.workspace)},
            },
            "read_only_commands": [
                ["rg", "--files"],
                ["rg", "-n", "needle", "README.md"],
                ["pwd"],
            ],
            "supervisor_path_grants": [],
            "director_approved_existing_changes": [],
        }

    def event(self, tool, command=None):
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool}
        if command is not None:
            payload["tool_input"] = {"command": command}
        return payload

    def decision(self, result):
        return result["hookSpecificOutput"]["permissionDecision"]

    def test_codex_role_overrides_bind_explicit_model_effort_and_role_sandbox(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "build_overrides")
        expected_sandboxes = {
            "operator": "workspace-write",
            "reviewer": "read-only",
            "director": "read-only",
        }
        for role, sandbox in expected_sandboxes.items():
            with self.subTest(role=role):
                argv = module.build_overrides(role, codex_runtime(), codex_request())
                self.assertIn("--model", argv)
                self.assertEqual(argv[argv.index("--model") + 1], "gpt-6-luna")
                self.assertIn("--sandbox", argv)
                self.assertEqual(argv[argv.index("--sandbox") + 1], sandbox)
                self.assertIn("--ask-for-approval", argv)
                self.assertEqual(argv[argv.index("--ask-for-approval") + 1], "never")
                config_values = [argv[i + 1] for i, value in enumerate(argv[:-1])
                                 if value in ("--config", "-c")]
                self.assertIn('model_reasoning_effort="max"', config_values)
                self.assertIn("agents.enabled=false", config_values)
                self.assertIn("features.apps=false", config_values)
                self.assertIn('web_search="disabled"', config_values)

    def test_codex_director_disables_both_shell_paths(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "build_overrides")
        argv = module.build_overrides("director", codex_runtime(), codex_request())
        config_values = [argv[i + 1] for i, value in enumerate(argv[:-1])
                         if value in ("--config", "-c")]
        self.assertIn("features.shell_tool=false", config_values)
        self.assertIn("features.unified_exec=false", config_values)

    def test_codex_instruction_is_one_unicode_toml_value_not_shell_text(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "build_overrides")
        request = codex_request()
        instructions = request["developer_instructions"]
        argv = module.build_overrides("operator", codex_runtime(), request)
        config_values = [argv[i + 1] for i, value in enumerate(argv[:-1])
                         if value in ("--config", "-c")]
        encoded = next(value.partition("=")[2] for value in config_values
                       if value.startswith("developer_instructions="))
        self.assertEqual(json.loads(encoded), instructions)
        self.assertNotIn("--developer-instructions", argv)

    def test_codex_builder_refuses_untrusted_or_uncovered_hooks(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "build_overrides")
        for key in ("hooks_trusted", "bash_hook_covered", "apply_patch_hook_covered"):
            request = codex_request()
            request["capabilities"][key] = False
            with self.subTest(key=key), self.assertRaises(module.PolicyUnavailable):
                module.build_overrides("operator", codex_runtime(), request)

    def test_codex_builder_refuses_unhooked_mutators_and_policy_conflicts(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "build_overrides")
        for key, value in (("unhooked_mutating_tools", ["mcp__files__write"]),
                           ("managed_policy_conflicts", ["approval_policy"]),
                           ("inherited_instruction_conflicts", ["AGENTS.md"])):
            request = codex_request()
            request["capabilities"][key] = value
            with self.subTest(key=key), self.assertRaises(module.PolicyUnavailable):
                module.build_overrides("operator", codex_runtime(), request)

    def test_codex_build_overrides_does_not_write_global_config_or_add_bypass_flags(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "build_overrides")
        config_home = pathlib.Path(self.temp.name) / "codex-home"
        config_home.mkdir()
        config_file = config_home / "config.toml"
        config_file.write_text("approval_policy = 'on-request'\n", encoding="utf-8")
        before = config_file.read_bytes()
        old_home = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = str(config_home)
        try:
            argv = module.build_overrides("operator", codex_runtime(), codex_request())
        finally:
            if old_home is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = old_home
        self.assertEqual(config_file.read_bytes(), before)
        forbidden = {
            "--yolo", "--dangerously-bypass-approvals-and-sandbox",
            "--dangerously-bypass-hook-trust", "--full-auto", "--agent", "--variant",
        }
        self.assertTrue(forbidden.isdisjoint(argv))

    def test_codex_operator_allows_only_an_exact_declared_scoped_runner(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "check_tool_call")
        policy = self.policy()
        command = shlex.join(policy["runner_commands"]["test"]["argv"])
        self.assertEqual(self.decision(module.check_tool_call(self.event("Bash", command), policy)), "allow")

    def test_codex_operator_allows_declared_read_only_exploration(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "check_tool_call")
        for command in ("rg --files", 'rg -n needle README.md', "pwd"):
            with self.subTest(command=command):
                self.assertEqual(
                    self.decision(module.check_tool_call(self.event("Bash", command), self.policy())),
                    "allow",
                )

    def test_codex_operator_rejects_safe_runner_followed_by_shell_chain(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "check_tool_call")
        policy = self.policy()
        command = shlex.join(policy["runner_commands"]["test"]["argv"]) + " && git commit -am injected"
        self.assertEqual(self.decision(module.check_tool_call(self.event("Bash", command), policy)), "deny")

    def test_codex_operator_rejects_direct_git_and_publication_commands(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "check_tool_call")
        for command in ("git status", "git add src/app.py", "git commit -m x", "git push origin main"):
            with self.subTest(command=command):
                self.assertEqual(
                    self.decision(module.check_tool_call(self.event("Bash", command), self.policy())),
                    "deny",
                )

    def test_codex_operator_rejects_arbitrary_python_powershell_and_cmd_wrappers(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "check_tool_call")
        commands = (
            'python -c "print(1)"',
            'powershell -NoProfile -Command "Get-ChildItem"',
            'pwsh -Command "Remove-Item *"',
            'cmd.exe /c "git status"',
            'bash -c "touch src/app.py"',
            'sh -c "echo x"',
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(
                    self.decision(module.check_tool_call(self.event("Bash", command), self.policy())),
                    "deny",
                )

    def test_codex_operator_rejects_pipes_redirection_substitution_and_newline_chains(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "check_tool_call")
        policy = self.policy()
        runner = shlex.join(policy["runner_commands"]["test"]["argv"])
        for command in (runner + " | cat", runner + " > result.txt", runner + "; echo done",
                        runner + " || echo failed", runner + " $(touch escaped)",
                        runner + "\n git push origin main"):
            with self.subTest(command=command):
                self.assertEqual(
                    self.decision(module.check_tool_call(self.event("Bash", command), policy)),
                    "deny",
                )

    def test_codex_reviewer_can_inspect_but_cannot_edit_or_run_tests(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "check_tool_call")
        policy = self.policy("reviewer")
        self.assertEqual(self.decision(module.check_tool_call(self.event("Bash", "rg --files"), policy)), "allow")
        runner = shlex.join(policy["runner_commands"]["test"]["argv"])
        self.assertEqual(self.decision(module.check_tool_call(self.event("Bash", runner), policy)), "deny")
        patch = "*** Begin Patch\n*** Update File: src/app.py\n@@\n-value = 1\n+value = 2\n*** End Patch"
        self.assertEqual(self.decision(module.check_tool_call(self.event("apply_patch", patch), policy)), "deny")

    def test_codex_reviewer_rejects_test_analyze_and_format_entries_even_in_read_only_list(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "check_tool_call")
        policy = self.policy("reviewer")
        forbidden = (["pytest", "-q"], ["ruff", "check", "."], ["prettier", "--check", "."])
        policy["read_only_commands"].extend(forbidden)
        for argv in forbidden:
            with self.subTest(argv=argv):
                command = shlex.join(argv)
                self.assertEqual(self.decision(module.check_tool_call(self.event("Bash", command), policy)), "deny")

    def test_codex_reviewer_rejects_task_runner_relisted_as_read_only(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "check_tool_call")
        policy = self.policy("reviewer")
        runner = ["make", "test"]
        policy["runner_commands"]["test"]["argv"] = runner
        policy["read_only_commands"].append(runner)
        self.assertEqual(self.decision(module.check_tool_call(self.event("Bash", shlex.join(runner)), policy)), "deny")

    def test_codex_reviewer_rejects_test_launchers_in_read_only_list(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "check_tool_call")
        policy = self.policy("reviewer")
        launchers = (["npx", "jest"], ["node", "./node_modules/.bin/jest"])
        policy["read_only_commands"].extend(launchers)
        for argv in launchers:
            with self.subTest(argv=argv):
                self.assertEqual(self.decision(module.check_tool_call(self.event("Bash", shlex.join(argv)), policy)), "deny")

    def test_codex_director_cannot_run_shell_or_edit(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "check_tool_call")
        policy = self.policy("director")
        self.assertEqual(self.decision(module.check_tool_call(self.event("Bash", "pwd"), policy)), "deny")
        self.assertEqual(self.decision(module.check_tool_call(self.event("apply_patch", "*** Begin Patch\n"), policy)), "deny")

    def test_codex_unified_exec_uses_the_documented_bash_hook_event_shape(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "check_tool_call")
        policy = self.policy()
        command = shlex.join(policy["runner_commands"]["red"]["argv"])
        event = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}}
        self.assertEqual(self.decision(module.check_tool_call(event, policy)), "allow")

    def test_codex_unknown_tool_and_malformed_mutating_shapes_fail_closed(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "check_tool_call")
        for event in (
            {"hook_event_name": "PreToolUse", "tool_name": "unknown_mutator", "tool_input": {"path": "src/app.py"}},
            {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"cmd": "pwd"}},
            {"hook_event_name": "PreToolUse", "tool_name": "apply_patch", "tool_input": {"patch": "*** Begin Patch"}},
            {"tool_name": "Bash", "tool_input": {"command": "pwd"}},
        ):
            with self.subTest(event=event):
                self.assertEqual(self.decision(module.check_tool_call(event, self.policy())), "deny")

    def test_codex_apply_patch_allows_task_scoped_files_and_denies_protected_files(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "check_tool_call")
        patch = "*** Begin Patch\n*** Update File: src/app.py\n@@\n-value = 1\n+value = 2\n*** End Patch"
        self.assertEqual(self.decision(module.check_tool_call(self.event("apply_patch", patch), self.policy())), "allow")
        protected = "*** Begin Patch\n*** Update File: plan.json\n@@\n-old\n+new\n*** End Patch"
        self.assertEqual(self.decision(module.check_tool_call(self.event("apply_patch", protected), self.policy())), "deny")

    def test_codex_apply_patch_rejects_unauthorized_new_paths_and_traversal(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "check_tool_call")
        policy = self.policy()
        for path in ("src/unrelated.py", "../outside.py", str(self.workspace.parent / "outside.py")):
            patch = "*** Begin Patch\n*** Add File: " + path + "\n+value = 1\n*** End Patch"
            with self.subTest(path=path):
                self.assertEqual(self.decision(module.check_tool_call(self.event("apply_patch", patch), policy)), "deny")

    def test_codex_supervisor_grant_is_bound_to_path_task_and_attempt(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "check_tool_call")
        policy = self.policy()
        policy["supervisor_path_grants"] = [{
            "path": "src/related.py", "issuer": "supervisor", "task_id": 7,
            "attempt_id": "attempt-2", "grant_id": "grant-1",
        }]
        patch = "*** Begin Patch\n*** Add File: src/related.py\n+value = 1\n*** End Patch"
        self.assertEqual(self.decision(module.check_tool_call(self.event("apply_patch", patch), policy)), "allow")
        for key, value in (("task_id", 8), ("attempt_id", "other"), ("issuer", "worker")):
            invalid = self.policy()
            grant = dict(policy["supervisor_path_grants"][0])
            grant[key] = value
            invalid["supervisor_path_grants"] = [grant]
            with self.subTest(key=key):
                self.assertEqual(self.decision(module.check_tool_call(self.event("apply_patch", patch), invalid)), "deny")

    def test_codex_worker_asserted_grant_does_not_authorize_a_path(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "check_tool_call")
        event = self.event("apply_patch", "*** Begin Patch\n*** Add File: src/unrelated.py\n+value = 1\n*** End Patch")
        event["path_grant"] = {"issuer": "supervisor", "path": "src/unrelated.py"}
        self.assertEqual(self.decision(module.check_tool_call(event, self.policy())), "deny")

    def test_codex_director_approval_can_grant_one_existing_path(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "check_tool_call")
        policy = self.policy()
        policy["director_approved_existing_changes"] = [{
            "path": "src/app.py", "issuer": "director", "task_id": 7,
            "attempt_id": "attempt-2", "decision_id": "decision-1", "approved": True,
        }]
        policy["touches"] = []
        event = self.event("apply_patch", "*** Begin Patch\n*** Update File: src/app.py\n@@\n-value = 1\n+value = 2\n*** End Patch")
        self.assertEqual(self.decision(module.check_tool_call(event, policy)), "allow")

    def test_codex_protected_path_deny_overrides_a_matching_grant(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "check_tool_call")
        policy = self.policy()
        policy["supervisor_path_grants"] = [{
            "path": "plan.json", "issuer": "supervisor", "task_id": 7,
            "attempt_id": "attempt-2", "grant_id": "bad-grant",
        }]
        patch = "*** Begin Patch\n*** Update File: plan.json\n@@\n-old\n+new\n*** End Patch"
        self.assertEqual(self.decision(module.check_tool_call(self.event("apply_patch", patch), policy)), "deny")

    def test_codex_apply_patch_unknown_directive_fails_closed(self):
        module = load_module(self, "codex_policy.py", "codex_policy", "check_tool_call")
        event = self.event("apply_patch", "*** Begin Patch\n*** Unknown Operation: src/app.py\n")
        self.assertEqual(self.decision(module.check_tool_call(event, self.policy())), "deny")

    def test_codex_hook_cli_requires_attempt_policy_and_emits_documented_decision(self):
        policy_path = self.workspace / "attempt-policy.json"
        policy_path.write_text(json.dumps(self.policy()), encoding="utf-8")
        runner = shlex.join(self.policy()["runner_commands"]["test"]["argv"])
        event = json.dumps(self.event("Bash", runner))
        env = dict(os.environ)
        env["PIPELINE_ROLE_POLICY"] = str(policy_path)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "codex-policy")], input=event,
            text=True, capture_output=True, cwd=str(self.workspace), env=env, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "allow")

    def test_codex_hook_cli_denies_missing_policy_or_invalid_event(self):
        env = dict(os.environ)
        env.pop("PIPELINE_ROLE_POLICY", None)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "codex-policy")], input="{}",
            text=True, capture_output=True, cwd=str(self.workspace), env=env, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_codex_hook_config_covers_bash_and_apply_patch_and_references_packaged_wrapper(self):
        hooks_path = ROOT / "skills" / "two-model-sdd-pipeline" / "codex" / "hooks.json"
        self.assertTrue(hooks_path.is_file(), "R2.4 requires packaged codex/hooks.json")
        hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
        groups = hooks["hooks"]["PreToolUse"]
        matchers = {entry["matcher"] for entry in groups}
        self.assertIn("Bash", matchers)
        self.assertIn("apply_patch", matchers)
        commands = [handler["command"] for group in groups for handler in group["hooks"]]
        self.assertTrue(any("codex-policy" in command for command in commands))
        self.assertFalse(any("dangerously-bypass-hook-trust" in command for command in commands))


class OpenCodeRolePolicyTests(unittest.TestCase):
    def setUp(self):
        self.workspace = pathlib.Path(tempfile.mkdtemp(prefix="opencode-policy-"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.workspace, ignore_errors=True)

    def request(self):
        return {
            "workspace_root": str(self.workspace),
            "developer_instructions": "Keep the worker within the approved role.",
            "touches": ["src/app.py"],
            "new_test_files": ["tests/test_app.py"],
            "protected_paths": ["plan.json", ".superpowers/ledger.jsonl", "runtime.json"],
            "runner_commands": {
                "test": {"argv": ["python3", "skills/pipeline/scripts/scoped-run", ".", "7", "test"], "cwd": str(self.workspace)},
            },
            "read_only_commands": [["rg", "--files"], ["pwd"]],
            "capabilities": {"permission_schema": "v1", "uncovered_mutating_tools": []},
            "task_id": 7,
            "attempt_id": "attempt-2",
        }

    def test_opencode_operator_uses_native_scoped_permission_patterns(self):
        module = load_module(self, "opencode_policy.py", "opencode_policy", "build_settings")
        result = module.build_settings("operator", opencode_runtime(), self.request())
        self.assertTrue(result["capabilities"]["available"])
        agent = result["config"]["agent"]["build"]
        self.assertEqual(agent["model"], "openai/gpt-6-luna")
        self.assertEqual(agent["variant"], "max")
        permission = agent["permission"]
        self.assertEqual(permission["edit"]["*"], "deny")
        self.assertEqual(permission["bash"]["*"], "deny")
        self.assertEqual(permission["task"], "deny")
        self.assertEqual(permission["external_directory"], "deny")
        self.assertTrue(any(value == "allow" for value in permission["edit"].values()))
        self.assertTrue(any(value == "allow" for value in permission["bash"].values()))
        self.assertIn("path-scoped edits", result["capabilities"]["enforced"])
        self.assertEqual(result["capabilities"]["unsupported"], [])

    def test_opencode_reviewer_is_read_only_and_cannot_run_declared_test_runner(self):
        module = load_module(self, "opencode_policy.py", "opencode_policy", "build_settings")
        result = module.build_settings("reviewer", opencode_runtime(), self.request())
        agent = result["config"]["agent"]["review"]["permission"]
        self.assertEqual(agent["edit"], "deny")
        self.assertEqual(agent["task"], "deny")
        self.assertEqual(agent["bash"]["*"], "deny")
        self.assertIn("rg --files", agent["bash"])
        runner = " ".join(self.request()["runner_commands"]["test"]["argv"])
        self.assertNotIn(runner, agent["bash"])

    def test_opencode_reviewer_rejects_test_analyze_and_format_read_only_entries(self):
        module = load_module(self, "opencode_policy.py", "opencode_policy", "build_settings")
        request = self.request()
        forbidden = (["pytest", "-q"], ["ruff", "check", "."], ["prettier", "--check", "."])
        request["read_only_commands"].extend(forbidden)
        result = module.build_settings("reviewer", opencode_runtime(), request)
        agent = result["config"]["agent"]["review"]["permission"]
        for argv in forbidden:
            with self.subTest(argv=argv):
                self.assertNotIn(" ".join(argv), agent["bash"])
        self.assertFalse(result["capabilities"]["available"])
        self.assertTrue(result["capabilities"]["unsupported"])

    def test_opencode_reports_ambiguous_argv_permissions_unsupported(self):
        module = load_module(self, "opencode_policy.py", "opencode_policy", "build_settings")
        request = self.request()
        request["runner_commands"]["query"] = {
            "argv": ["rg", "query with spaces", "README.md"],
            "cwd": str(self.workspace),
        }
        result = module.build_settings("operator", opencode_runtime(), request)
        agent = result["config"]["agent"]["build"]["permission"]
        self.assertFalse(result["capabilities"]["available"])
        self.assertTrue(result["capabilities"]["unsupported"])
        self.assertNotIn("rg query with spaces README.md", agent["bash"])

    def test_opencode_does_not_allow_declared_task_runner_as_reviewer_read_only(self):
        module = load_module(self, "opencode_policy.py", "opencode_policy", "build_settings")
        request = self.request()
        runner = ["make", "test"]
        request["runner_commands"]["test"]["argv"] = runner
        request["read_only_commands"].append(runner)
        result = module.build_settings("reviewer", opencode_runtime(), request)
        permission = result["config"]["agent"]["review"]["permission"]
        self.assertNotIn("make test", permission["bash"])
        self.assertFalse(result["capabilities"]["available"])

    def test_opencode_reviewer_rejects_interpreters_and_test_launchers(self):
        module = load_module(self, "opencode_policy.py", "opencode_policy", "build_settings")
        request = self.request()
        launchers = (["python", "-m", "pytest"], ["python", "-m", "unittest", "discover"],
                     ["node", "./node_modules/.bin/jest"], ["npx", "jest"])
        request["read_only_commands"].extend(launchers)
        result = module.build_settings("reviewer", opencode_runtime(), request)
        permission = result["config"]["agent"]["review"]["permission"]
        for argv in launchers:
            with self.subTest(argv=argv):
                self.assertNotIn(" ".join(argv), permission["bash"])
        self.assertFalse(result["capabilities"]["available"])

    def test_opencode_rejects_shell_syntax_in_declared_command_argv(self):
        module = load_module(self, "opencode_policy.py", "opencode_policy", "build_settings")
        request = self.request()
        request["runner_commands"]["unsafe"] = {
            "argv": ["printf", "safe;touch"], "cwd": str(self.workspace),
        }
        result = module.build_settings("operator", opencode_runtime(), request)
        permission = result["config"]["agent"]["build"]["permission"]
        self.assertNotIn("printf safe;touch", permission["bash"])
        self.assertFalse(result["capabilities"]["available"])

    def test_opencode_director_has_no_shell_edit_or_delegation(self):
        module = load_module(self, "opencode_policy.py", "opencode_policy", "build_settings")
        result = module.build_settings("director", opencode_runtime(), self.request())
        agent = result["config"]["agent"]["director"]["permission"]
        self.assertEqual(agent["edit"], "deny")
        self.assertEqual(agent["bash"], "deny")
        self.assertEqual(agent["task"], "deny")

    def test_opencode_reports_unsupported_capabilities_separately_and_unavailable(self):
        module = load_module(self, "opencode_policy.py", "opencode_policy", "build_settings")
        request = self.request()
        request["capabilities"]["uncovered_mutating_tools"] = ["plugin__workspace__write"]
        result = module.build_settings("operator", opencode_runtime(), request)
        self.assertFalse(result["capabilities"]["available"])
        self.assertIn("plugin__workspace__write", result["capabilities"]["unsupported"])
        self.assertNotIn("plugin__workspace__write", result["capabilities"]["enforced"])

    def test_opencode_policy_does_not_leak_codex_cli_or_toml_settings(self):
        module = load_module(self, "opencode_policy.py", "opencode_policy", "build_settings")
        result = module.build_settings("operator", opencode_runtime(), self.request())
        encoded = json.dumps(result["config"], sort_keys=True)
        for codex_only in ("--sandbox", "--ask-for-approval", "model_reasoning_effort", "agents.enabled"):
            with self.subTest(setting=codex_only):
                self.assertNotIn(codex_only, encoded)


if __name__ == "__main__":
    unittest.main()
