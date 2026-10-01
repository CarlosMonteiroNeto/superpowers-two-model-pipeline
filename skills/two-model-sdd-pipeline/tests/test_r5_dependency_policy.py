"""Dependency approval and manifest write coordination."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts" / "dependency_policy.py"


def load_module():
    spec = importlib.util.spec_from_file_location("r5_dependency_policy", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DependencyPolicyTests(unittest.TestCase):
    def setUp(self): self.policy = load_module()

    def test_compatible_known_license_allows_without_flutter_scoring(self):
        result = self.policy.evaluate({"name": "store", "version": "2.1.0"}, {"compatible": True, "license": {"status": "known", "value": "mit"}})
        self.assertEqual("allow", result["status"])

    def test_unknown_and_conflicting_dependency_question_but_incompatible_blocks(self):
        self.assertEqual("question", self.policy.evaluate({"name": "x", "version": "1.0"}, {"compatible": None, "license": {"status": "known", "value": "mit"}})["status"])
        self.assertEqual("question", self.policy.evaluate({"name": "x", "version": "1.0"}, {"compatible": True, "license": {"status": "unknown"}, "conflict": "constraint"})["status"])
        self.assertEqual("block", self.policy.evaluate({"name": "x", "version": "1.0"}, {"compatible": False, "license": {"status": "known", "value": "mit"}})["status"])
        self.assertEqual("block", self.policy.evaluate({"name": "x", "version": "latest"}, {"compatible": True, "license": {"status": "known", "value": "mit"}})["status"])

    def test_manifest_write_requires_scope_grant_and_shared_exclusive_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            request = {"name": "store", "version": "2.1", "write_paths": ["pubspec.yaml"], "granted_paths": ["pubspec.yaml"], "lock_path": str(Path(temp) / "manifest.lock"), "owner": {"repository_id": "repo", "branch": "main", "run_id": "run-a"}}
            calls = []
            evidence = {"compatible": True, "license": {"status": "known", "value": "mit"}}
            self.assertEqual("written", self.policy.prepare(request, evidence, lambda: calls.append("write"))["status"])
            self.assertEqual(["write"], calls)
            request["granted_paths"] = []
            self.assertEqual("blocked", self.policy.prepare(request, evidence, lambda: calls.append("bad"))["status"])
            self.assertEqual(["write"], calls)

    def test_concurrent_manifest_claim_cannot_enter_writer(self):
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / "manifest.lock"
            owner = {"repository_id": "repo", "branch": "main", "run_id": "run-a"}
            with self.policy._resource_lock(str(lock), owner):
                request = {"name": "store", "version": "2.1", "write_paths": ["pubspec.yaml"], "granted_paths": ["pubspec.yaml"], "lock_path": str(lock), "owner": {**owner, "run_id": "run-b"}}
                calls = []
                result = self.policy.prepare(request, {"compatible": True, "license": {"status": "known", "value": "mit"}}, lambda: calls.append("write"))
                self.assertEqual("question", result["status"])
                self.assertFalse(calls)
