"""Gate-level tests for snapshot-keyed, run-owned dependency evidence reuse."""

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills/two-model-sdd-pipeline/scripts"
sys.path.insert(0, str(SCRIPTS))
import test_dependency_cache
import test_dependency_graph


def load_gate():
    spec = importlib.util.spec_from_file_location("r4_dependency_cache_gate_subject", SCRIPTS / "gate_evidence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def complete_evidence():
    return {
        "complete": True,
        "forward_edges": {"tests/test_app.py": ["src/app.py"]},
        "reverse_edges": {"src/app.py": ["tests/test_app.py"]},
        "graphify_version": "0.9.50",
        "graph_digest": "a" * 64,
        "source_inventory_hash": "b" * 64,
        "diagnostics": [],
    }


class DependencyCacheGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name) / "repo"
        self.root.mkdir()
        self._git("init", "-q")
        self._git("config", "user.email", "test@example.invalid")
        self._git("config", "user.name", "Test")
        self._write(".gitignore", ".superpowers/\ngraphify-out/\n")
        self._write("src/app.py", "def run(): return 1\n")
        self._write("tests/test_app.py", "from src.app import run\ndef test_app(): run()\n")
        self._git("add", "-A")
        self._git("commit", "-qm", "fixture")
        self.workspace = self.root / ".superpowers/workspace"
        self.workspace.mkdir(parents=True)
        descriptor = {"language": "python", "red_adapter": "pytest_json_report", "commands": {
            "test": {"argv": ["pytest", "{test_paths}"], "cwd": ".", "env": {}},
            "analyze": {"argv": ["ruff", "check", "."], "cwd": ".", "env": {}},
            "format": {"argv": ["ruff", "format", "--check", "."], "cwd": ".", "env": {}}}}
        (self.workspace / "plan.json").write_text(json.dumps({"tasks": [
            {"id": 1, "toolchain_id": "python", "touches": ["src/app.py"]}]}), encoding="utf-8")
        (self.workspace / "ledger.jsonl").write_text(json.dumps({"type": "gate", "task": "-",
            "summary": "configured", "toolchain_id": "python", "toolchain_descriptor": descriptor}) + "\n",
            encoding="utf-8")
        self.base = self._git("rev-parse", "HEAD")
        self._write("src/app.py", "def run(): return 2\n")
        self._git("add", "src/app.py")
        self.cache_root = test_dependency_cache.create_owned_root()

    def tearDown(self):
        test_dependency_cache.cleanup_owned_root(self.cache_root)
        self.temporary.cleanup()

    def _git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True).stdout.decode("utf-8", "replace").strip()

    def _write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def _run_gate(self):
        return load_gate().create_workspace_manifest(str(self.workspace), ["1"], "tasks")

    def _graph_mocks(self, build):
        identity = {"available": True, "path": "graphify", "binary_sha256": "1" * 64,
                    "version": "0.9.50", "expected_version": "0.9.50", "schema_version": 1,
                    "flags": ["extract", "--code-only", "--no-cluster"], "diagnostic": ""}
        return (
            mock.patch.object(test_dependency_graph, "extractor_identity", return_value=identity, create=True),
            mock.patch.object(test_dependency_graph, "build", side_effect=build),
            mock.patch.dict(os.environ, {"PIPELINE_IMPACT_CACHE_ROOT": str(self.cache_root)}),
        )

    def test_cold_then_warm_gate_reuses_two_snapshots_outside_the_checkout(self):
        build = mock.Mock(return_value=complete_evidence())
        identity_patch, build_patch, env_patch = self._graph_mocks(build)
        with identity_patch, build_patch as graph_build, env_patch:
            cold = self._run_gate()
            warm = self._run_gate()

        self.assertEqual(cold["mode"], "affected")
        self.assertEqual(cold["tests"], ["tests/test_app.py"])
        self.assertEqual(graph_build.call_count, 2)
        self.assertEqual(warm["selection_hash"], cold["selection_hash"])
        diagnostics = json.loads((self.workspace / "impact-diagnostics.json").read_text(encoding="utf-8"))
        self.assertEqual(diagnostics, [
            {"snapshot": "base", "cache_hit": True, "cache_miss": False, "cache_write_failed": False},
            {"snapshot": "candidate", "cache_hit": True, "cache_miss": False, "cache_write_failed": False},
        ])
        self.assertTrue(test_dependency_cache.is_owned_root(self.cache_root))
        self.assertFalse(self.cache_root.is_relative_to(self.root))
        self.assertFalse((self.root / "graphify-out").exists())
        self.assertFalse((self.root / ".r4-graphify-output").exists())

    def test_changed_candidate_rebuilds_only_candidate_and_gate_identity_is_not_cached(self):
        build = mock.Mock(return_value=complete_evidence())
        identity_patch, build_patch, env_patch = self._graph_mocks(build)
        with identity_patch, build_patch as graph_build, env_patch:
            first = self._run_gate()
            self._git("reset", "-q", "--", "src/app.py")
            self._write("src/app.py", "def run(): return 3\n")
            changed = self._run_gate()
            self._git("commit", "--allow-empty", "-qm", "advance candidate identity")
            advanced = self._run_gate()

        self.assertEqual(graph_build.call_count, 3)
        self.assertNotEqual(first["selection_hash"], changed["selection_hash"])
        self.assertNotEqual(changed["identity"]["head_commit"], advanced["identity"]["head_commit"])
        self.assertNotEqual(changed["selection_hash"], advanced["selection_hash"])
        self.assertEqual(advanced["mode"], "affected")

    def test_incomplete_candidate_evidence_is_not_cached_or_used_for_narrowing(self):
        incomplete = {"complete": False, "forward_edges": {}, "reverse_edges": {},
                      "graphify_version": "0.9.50", "graph_digest": "", "source_inventory_hash": "",
                      "diagnostics": ["failed source"]}
        build = mock.Mock(side_effect=[complete_evidence(), incomplete, incomplete])
        identity_patch, build_patch, env_patch = self._graph_mocks(build)
        with identity_patch, build_patch as graph_build, env_patch:
            first = self._run_gate()
            second = self._run_gate()

        self.assertEqual(first["mode"], "full_suite")
        self.assertEqual(second["mode"], "full_suite")
        self.assertEqual(graph_build.call_count, 3)
        self.assertEqual(first["commands"][0]["argv"], ["pytest", "{test_paths}"])

    def test_configuration_fallback_avoids_extractor_identity_and_cache_reads(self):
        self._write("pyproject.toml", "[tool.pytest.ini_options]\n")
        self._git("add", "pyproject.toml")
        gate = load_gate()
        with mock.patch.object(test_dependency_graph, "extractor_identity",
                               side_effect=AssertionError("full-suite preflight must not inspect Graphify"), create=True):
            manifest = gate.create_workspace_manifest(str(self.workspace), ["1"], "tasks")
        self.assertEqual(manifest["mode"], "full_suite")
        self.assertIn("changed dependency, build, or test configuration requires complete suite",
                      manifest["reasons"])

    def test_deleted_tests_are_decided_without_graphify(self):
        (self.root / "tests/test_app.py").unlink()
        self._git("add", "-A")
        gate = load_gate()
        with mock.patch.object(test_dependency_graph, "extractor_identity",
                               side_effect=AssertionError("deleted-test preflight must not inspect Graphify"), create=True):
            manifest = gate.create_workspace_manifest(str(self.workspace), ["1"], "tasks")
        self.assertEqual(manifest["mode"], "full_suite")
        self.assertTrue(any("deleted test" in reason for reason in manifest["reasons"]))


if __name__ == "__main__":
    unittest.main()
