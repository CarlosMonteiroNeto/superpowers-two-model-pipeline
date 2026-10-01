"""Task 4 RED: working-area enforcement and supported local capabilities."""

import json
import os
import pathlib
import sys
import tempfile
import unittest


SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import scope_grants


def make_tree():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="worker-caps-"))
    root = tmp / "repo"
    (root / "src" / "a").mkdir(parents=True)
    (root / "src" / "other").mkdir(parents=True)
    (root / "src" / "a" / "x.py").write_text("x = 1\n", encoding="utf-8")
    (root / "src" / "other" / "y.py").write_text("y = 2\n", encoding="utf-8")
    (root / "src" / "a" / "x_test.py").write_text(
        "import unittest\n\n\nclass T(unittest.TestCase):\n"
        "    def test_x(self):\n        self.assertTrue(True)\n",
        encoding="utf-8")
    (root / "package-lock.json").write_text("{}\n", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("", encoding="utf-8")
    return tmp, root


def ownership(root, scope_roots, **extra):
    value = {"run_id": "run-1", "family_id": 1,
             "repo_root": str(root), "allowed_roots": ["src"],
             "scope": {"mode": "areas", "roots": list(scope_roots),
                       "exact_paths": []}}
    value.update(extra)
    return value


class AreaGrantParityTests(unittest.TestCase):
    def setUp(self):
        self._tmp, self.root = make_tree()

    def test_create_unlisted_file_inside_area_is_granted(self):
        result = scope_grants.reserve(
            {"path": "src/a/fresh.py", "kind": "new_file"},
            ownership(self.root, ["src/a"]))
        self.assertEqual(result["decision"], "grant")

    def test_modify_ordinary_file_inside_area_needs_no_director_approval(self):
        result = scope_grants.reserve(
            {"path": "src/a/x.py", "kind": "existing_file"},
            ownership(self.root, ["src/a"]))
        self.assertEqual(result["decision"], "grant")

    def test_outside_area_is_blocked(self):
        result = scope_grants.reserve(
            {"path": "src/other/y.py", "kind": "existing_file"},
            ownership(self.root, ["src/a"]))
        self.assertEqual(result["decision"], "block")

    def test_protected_paths_are_blocked_inside_areas(self):
        for path in (".git/config", "package-lock.json",
                     ".superpowers/ledger.jsonl"):
            with self.subTest(path=path):
                result = scope_grants.reserve(
                    {"path": path, "kind": "existing_file"},
                    ownership(self.root, ["."]))
                self.assertEqual(result["decision"], "block")

    def test_deletion_and_rename_kinds_are_rejected(self):
        for kind in ("delete", "rename", "append"):
            with self.subTest(kind=kind):
                result = scope_grants.reserve(
                    {"path": "src/a/x.py", "kind": kind},
                    ownership(self.root, ["src/a"]))
                self.assertEqual(result["decision"], "block")

    def test_legacy_exact_path_authority_is_unchanged(self):
        legacy = {"run_id": "run-1", "family_id": 1,
                  "repo_root": str(self.root), "allowed_roots": ["src"]}
        blocked = scope_grants.reserve(
            {"path": "src/a/x.py", "kind": "existing_file"}, legacy)
        self.assertEqual(blocked["decision"], "block")
        self.assertIn("director approval", blocked["reason"])
        granted = scope_grants.reserve(
            {"path": "src/a/fresh.py", "kind": "new_file"}, legacy)
        self.assertEqual(granted["decision"], "grant")


def _load(name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "caps_" + name.replace(".", "_"), SCRIPTS / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def capability_policy(root, evdir):
    return {
        "project_root": str(root),
        "evidence_dir": str(evdir),
        "scope": {"mode": "areas", "roots": ["src/a"], "exact_paths": []},
        "protected_paths": ["plan.json"],
        "toolchains": {
            "py": {"adapter": "unittest",
                   "commands": {
                       "test": {"argv": ["python", "-m", "unittest",
                                         "discover"],
                                "cwd": "."},
                       "red": {"argv": ["python", "-m", "unittest",
                                        "discover"],
                               "cwd": "."}}}}
    }


class ResolveCapabilityTests(unittest.TestCase):
    def setUp(self):
        self._tmp, self.root = make_tree()
        self.evdir = self._tmp / "evidence"
        self.evdir.mkdir()
        scoped = _load("scoped_runner.py")
        self.resolve = scoped.resolve_capability
        self.policy = capability_policy(self.root, self.evdir)

    def test_valid_request_returns_trusted_argv_cwd_and_evidence(self):
        result = self.resolve(
            {"mode": "test", "toolchain_id": "py",
             "paths": ["src/a/x_test.py"]},
            self.policy)
        self.assertEqual(result["argv"][:3], ["python", "-m", "unittest"])
        self.assertTrue(any("x_test" in part for part in result["argv"]))
        self.assertEqual(pathlib.Path(result["cwd"]).resolve(),
                         self.root.resolve())
        self.assertTrue(str(result["evidence_path"]).startswith(
            str(self.evdir)))
        self.assertEqual(result["identity"]["toolchain_id"], "py")
        self.assertEqual(result["identity"]["mode"], "test")

    def test_supported_test_case_selector_expands_for_unittest(self):
        result = self.resolve(
            {"mode": "test", "toolchain_id": "py", "paths": [],
             "selector": {"kind": "test_case",
                          "value": "x_test.T.test_x"}},
            self.policy)
        self.assertIn("x_test.T.test_x", result["argv"])

    def test_worker_supplied_commands_flags_and_shell_are_rejected(self):
        bad_requests = [
            {"mode": "test", "toolchain_id": "py",
             "paths": ["src/a/x_test.py"], "argv": ["evil"]},
            {"mode": "test", "toolchain_id": "py",
             "paths": ["src/a/x_test.py"], "command": "evil"},
            {"mode": "test", "toolchain_id": "py",
             "paths": ["src/a/x_test.py"], "shell": True},
            {"mode": "install", "toolchain_id": "py", "paths": []},
            {"mode": "test", "toolchain_id": "py",
             "paths": ["src/a/x_test.py; rm -rf /"]},
            {"mode": "test", "toolchain_id": "py",
             "paths": ["src/a/$(x)_test.py"]},
            {"mode": "test", "toolchain_id": "py",
             "paths": ["src/a/x_test.py"],
             "selector": {"kind": "magic", "value": "x"}},
        ]
        for request in bad_requests:
            with self.subTest(request=request):
                with self.assertRaises(ValueError):
                    self.resolve(request, self.policy)

    def test_outside_scope_protected_and_unknown_toolchain_are_rejected(self):
        cases = [
            {"mode": "test", "toolchain_id": "py",
             "paths": ["src/other/y.py"]},
            {"mode": "test", "toolchain_id": "py",
             "paths": ["plan.json"]},
            {"mode": "test", "toolchain_id": "nope",
             "paths": ["src/a/x_test.py"]},
            {"mode": "test", "toolchain_id": "py",
             "paths": ["../escape_test.py"]},
        ]
        for request in cases:
            with self.subTest(request=request):
                with self.assertRaises(ValueError):
                    self.resolve(request, self.policy)

    def test_resolution_is_deterministic(self):
        request = {"mode": "test", "toolchain_id": "py",
                   "paths": ["src/a/x_test.py"]}
        first = self.resolve(request, self.policy)
        second = self.resolve(request, self.policy)
        self.assertEqual(first["argv"], second["argv"])
        self.assertEqual(first["identity"], second["identity"])


class PolicyScopeTests(unittest.TestCase):
    def test_codex_attempt_policy_embeds_task_scope(self):
        codex_policy = _load("codex_policy.py")
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="caps-policy-"))
        prompt = tmp / "prompt.md"
        prompt.write_text("prompt", encoding="utf-8")
        plan = {"tasks": [{"id": 1, "working_areas": ["src/a"],
                           "touches": [], "verification": {}}]}
        plan_path = tmp / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        import hashlib as _hashlib
        request = {"role": "operator", "task_id": 1,
                   "evidence_paths": {"prompt_path": str(prompt)},
                   "worktree": str(tmp), "dispatch_id": "d",
                   "plan_revision": _hashlib.sha256(
                       plan_path.read_bytes()).hexdigest()}
        runtime = {"capabilities": {
            "hooks_enabled": True, "hooks_trusted": True}}
        policy = codex_policy.build_attempt_policy(request, runtime)
        self.assertEqual(policy["scope"]["mode"], "areas")
        self.assertEqual(policy["scope"]["roots"], ["src/a"])

    def test_opencode_settings_record_area_scope(self):
        opencode_policy = _load("opencode_policy.py")
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="caps-opencode-"))
        request = {"workspace_root": str(tmp), "touches": ["src/a/x.py"],
                   "new_test_files": [], "protected_paths": [],
                   "runner_commands": {}, "read_only_commands": [],
                   "capabilities": {"permission_schema": "v1",
                                    "uncovered_mutating_tools": []},
                   "scope": {"mode": "areas", "roots": ["src/a"],
                             "exact_paths": []}}
        runtime = {"backend": "opencode",
                   "roles": {"operator": {
                       "model": "m",
                       "settings": {"variant": "v", "agent": "a"}}}}
        result = opencode_policy.build_settings("operator", runtime, request)
        self.assertIn("directory-scoped edits",
                      result["capabilities"]["enforced"])
        self.assertEqual(result["capabilities"]["scope"]["roots"], ["src/a"])


class DescribeCapabilitiesTests(unittest.TestCase):
    def test_description_covers_modes_selectors_scope_and_protected(self):
        scoped = _load("scoped_runner.py")
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="caps-desc-"))
        text = scoped.describe_capabilities(
            capability_policy(tmp, tmp / "ev"))
        folded = text.casefold()
        for marker in ("red", "test", "analyze", "format", "test_case",
                       "src/a", "plan.json"):
            self.assertIn(marker, folded)


if __name__ == "__main__":
    unittest.main()
