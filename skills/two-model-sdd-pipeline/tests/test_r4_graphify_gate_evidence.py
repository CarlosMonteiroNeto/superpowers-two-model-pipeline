import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills/two-model-sdd-pipeline/scripts"
MODULE = SCRIPTS / "gate_evidence.py"
sys.path.insert(0, str(SCRIPTS))
import test_dependency_graph


def subject():
    spec = importlib.util.spec_from_file_location("gate_evidence_graph_tests", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def complete_graph():
    return {"complete": True, "forward_edges": {"tests/test_app.py": ["src/app.py"]},
            "reverse_edges": {"src/app.py": ["tests/test_app.py"]},
            "graphify_version": "0.9.50", "graph_digest": "a" * 64,
            "source_inventory_hash": "b" * 64, "diagnostics": []}


class GraphifyGateEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self._git("init", "-q")
        self._git("config", "user.email", "test@example.invalid")
        self._git("config", "user.name", "Test")
        self._write(".gitignore", ".superpowers/\ngraphify-out/\n")
        self._write("src/app.py", "def run(): return 1\n")
        self._write("tests/test_app.py", "from src import app\ndef test_run(): app.run()\n")
        self._write("test_impact.rules", "policy")
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
            "summary": "configured", "toolchain_id": "python", "toolchain_descriptor": descriptor}) + "\n", encoding="utf-8")
        self.identity = {"available": True, "path": "graphify", "binary_sha256": "1" * 64,
                         "version": "0.9.50", "expected_version": "0.9.50", "schema_version": 1,
                         "flags": ["extract", "--code-only", "--no-cluster"], "diagnostic": ""}

    def tearDown(self):
        self.temporary.cleanup()

    def _git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True).stdout.decode("utf-8", "replace").strip()

    def _write(self, name, contents):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")

    def _graph_patches(self, build):
        return (mock.patch.object(test_dependency_graph, "extractor_identity",
                                  return_value=self.identity, create=True),
                mock.patch.object(test_dependency_graph, "build", side_effect=build))

    def test_configuration_full_suite_skips_graph_reads_and_snapshot_materialization(self):
        self._write("pyproject.toml", "[tool.pytest.ini_options]\n")
        self._git("add", "pyproject.toml")
        gate = subject()
        with mock.patch.object(gate, "_graph_evidence",
                               side_effect=AssertionError("configuration fallback must precede graph access")):
            manifest = gate.create_workspace_manifest(str(self.workspace), ["1"], "tasks")
        self.assertEqual(manifest["mode"], "full_suite")
        self.assertIn("changed dependency, build, or test configuration requires complete suite",
                      manifest["reasons"])
        self.assertIn("graph acquisition skipped during preflight",
                      manifest["evidence"]["graph_provenance"]["diagnostics"])

    def test_workspace_input_capture_does_not_read_graph_or_write_manifest(self):
        gate = subject()
        with mock.patch.object(gate, "_graph_evidence",
                               side_effect=AssertionError("input capture must not read graph evidence")):
            inputs = gate.capture_workspace_inputs(str(self.workspace), ["1"], "tasks")
        self.assertEqual(inputs["descriptors"][0]["id"], "python")
        self.assertEqual(inputs["phase"], "task")
        self.assertFalse((self.workspace / "impact-manifest.json").exists())

    def test_incomplete_graph_falls_back_without_partial_edges(self):
        self._write("src/app.py", "def run(): return 3\n")
        incomplete = {"complete": False, "reverse_edges": {"src/app.py": ["tests/test_app.py"]},
                      "graphify_version": "0.9.50", "graph_digest": "c" * 64,
                      "source_inventory_hash": "d" * 64, "diagnostics": ["failed source"]}
        identity_patch, build_patch = self._graph_patches(mock.Mock(side_effect=[complete_graph(), incomplete]))
        with identity_patch, build_patch:
            manifest = subject().create_workspace_manifest(str(self.workspace), ["1"], "tasks")
        self.assertEqual(manifest["mode"], "full_suite")
        self.assertEqual(manifest["commands"][0]["argv"], ["pytest", "{test_paths}"])

    def test_post_execution_verification_reuses_sealed_evidence_without_graph_or_selection(self):
        self._write("src/app.py", "def run(): return 2\n")
        identity_patch, build_patch = self._graph_patches(mock.Mock(return_value=complete_graph()))
        gate = subject()
        with identity_patch, build_patch:
            manifest = gate.create_workspace_manifest(str(self.workspace), ["1"], "tasks")
        self.assertEqual(manifest["mode"], "affected")
        identity_patch, build_patch = self._graph_patches(mock.Mock(side_effect=AssertionError("verification must not extract")))
        with identity_patch, build_patch, mock.patch.object(sys.modules["test_impact"], "select",
                side_effect=AssertionError("verification must not reselect")):
            gate.verify_workspace_manifest(str(self.workspace), ["1"], "tasks", manifest)

    def test_post_execution_verification_rejects_candidate_drift(self):
        self._write("src/app.py", "def run(): return 2\n")
        identity_patch, build_patch = self._graph_patches(mock.Mock(return_value=complete_graph()))
        gate = subject()
        with identity_patch, build_patch:
            manifest = gate.create_workspace_manifest(str(self.workspace), ["1"], "tasks")
        self._write("src/app.py", "def run(): return 3\n")
        identity_patch, _ = self._graph_patches(None)
        with identity_patch, self.assertRaisesRegex(ValueError, "inputs changed"):
            gate.verify_workspace_manifest(str(self.workspace), ["1"], "tasks", manifest)


if __name__ == "__main__":
    unittest.main()
