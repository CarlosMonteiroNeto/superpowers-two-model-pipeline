"""Controller-owned R3.1 shared-write and mixed-toolchain tests."""
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"


def load(test, name, function):
    path = SCRIPTS / name
    test.assertTrue(path.is_file(), "R3.1 requires scripts/" + name)
    spec = importlib.util.spec_from_file_location("r31_" + name.replace(".", "_"), path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    test.assertTrue(callable(getattr(value, function, None)))
    return value


class MultitoolchainIntegrationTests(unittest.TestCase):
    def test_scheduler_includes_new_test_paths_and_shared_resources(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = pathlib.Path(temp)
            (workspace / "plan.json").write_text(json.dumps({"tasks": [
                {"id": 1, "touches": ["src/a.py"], "verification": {"new_test_files": ["tests/shared.py"]}},
                {"id": 2, "touches": ["src/b.py"], "verification": {"new_test_files": ["tests/shared.py"]}},
            ]}), encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPTS / "touches-overlap"),
                str(workspace), "1", "2"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("tests/shared.py", result.stderr)

    def test_scope_grant_allows_related_new_file_but_not_unapproved_existing_file(self):
        grants = load(self, "scope_grants.py", "reserve")
        ownership = {"run_id": "r", "family_id": 1, "allowed_roots": ["src", "tests"],
                     "declared_touches": ["src/app.py"], "protected_paths": ["plan.json"]}
        approved = grants.reserve({"path": "src/new_helper.py", "kind": "new_file"}, ownership)
        self.assertEqual(approved["decision"], "grant")
        denied = grants.reserve({"path": "src/app.py", "kind": "existing_file"}, ownership)
        self.assertEqual(denied["decision"], "block")

    def test_scope_grant_resolves_symlink_before_protected_path_checks(self):
        grants = load(self, "scope_grants.py", "reserve")
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / "src").mkdir()
            (root / "plan.json").write_text("{}", encoding="utf-8")
            alias = root / "src" / "plan-alias.json"
            try:
                alias.symlink_to(root / "plan.json")
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation is unavailable")
            ownership = {"run_id": "r", "family_id": 1, "repo_root": str(root),
                "allowed_roots": ["src"], "declared_touches": [],
                "protected_paths": ["plan.json"],
                "director_approved_existing": ["src/plan-alias.json"]}
            decision = grants.reserve({"path": "src/plan-alias.json", "kind": "existing_file"}, ownership)
            self.assertEqual(decision["decision"], "block")
            self.assertEqual(decision["reason"], "protected path")
