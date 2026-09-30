import hashlib
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import unittest
import shutil
import subprocess
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills/two-model-sdd-pipeline/scripts"
RUN_GATES = SCRIPTS / "run-gates"


def load(name):
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seal(manifest):
    content = {key: value for key, value in manifest.items() if key != "selection_hash"}
    manifest["selection_hash"] = hashlib.sha256(json.dumps(
        content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return manifest


class GraphifyGateExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.workspace = self.root / ".superpowers/workspace"
        self.workspace.mkdir(parents=True)
        self.recorder = self.root / "record.py"
        self.recorder.write_text(
            "import json,os,sys; open(os.environ['CAPTURE'], 'w').write(json.dumps(sys.argv[1:]))\n",
            encoding="utf-8")
        self.test_capture = self.root / "test-argv.json"
        self.analyze_capture = self.root / "analyze-argv.json"
        self.entry = {"type": "gate", "toolchain_id": "python", "lang": "python",
            "toolchain_descriptor": {"language": "python", "red_adapter": None,
                "commands": {
                    "test": {"argv": [sys.executable, str(self.recorder), "FULL"],
                             "cwd": str(self.root), "env": {"CAPTURE": str(self.test_capture)}},
                    "analyze": {"argv": [sys.executable, str(self.recorder), "ANALYZE"],
                                "cwd": str(self.root), "env": {"CAPTURE": str(self.analyze_capture)}}}}}
        self.runner = load("toolchain_gate")
        self.manifest_path = self.workspace / "impact-manifest.json"

    def tearDown(self):
        self.temp.cleanup()

    def _manifest(self, *, full=False, toolchain_id="python", tests=None, graph_complete=True):
        tests = tests or ["tests/test_target.py"]
        full_argv = [sys.executable, str(self.recorder), "FULL"]
        argv = full_argv if full else full_argv + tests
        identity = {"base_commit": "a" * 40, "head_commit": "b" * 40,
                    "base_tree_hash": "c" * 64, "tree_hash": "d" * 64,
                    "config_hash": "e" * 64, "environment_hash": "f" * 64,
                    "policy_version": "r4-impact-1"}
        graph_provenance = {"complete": False, "diagnostics": ["uncertain"]}
        if graph_complete:
            graph_provenance = {"complete": True, "graphify_version": "0.9.50",
                "base_commit": identity["base_commit"], "base_tree_hash": identity["base_tree_hash"],
                "candidate_commit": identity["head_commit"], "candidate_tree_hash": identity["tree_hash"],
                "base": {"complete": True, "graph_digest": "1" * 64, "source_inventory_hash": "2" * 64},
                "candidate": {"complete": True, "graph_digest": "3" * 64, "source_inventory_hash": "4" * 64}}
        manifest = {"schema_version": 1, "mode": "full_suite" if full else "affected",
            "scope_paths": [], "tests": [] if full else tests,
            "commands": [{"toolchain_id": toolchain_id, "language": "python", "full_suite": full,
                "tests": [] if full else tests, "argv": argv, "cwd": str(self.root),
                "env": {"CAPTURE": str(self.test_capture)}}],
            "reasons": [], "reasons_detail": [], "gaps": [], "identity": identity,
            "evidence": {"diff_hash": "5" * 64, "graph_hash": "6" * 64,
                "toolchains_hash": "7" * 64, "policy_hash": "8" * 64,
                "graph_provenance": graph_provenance}}
        return seal(manifest)

    def _run(self, manifest, phase="task"):
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        env = {"PIPELINE_IMPACT_MANIFEST": str(self.manifest_path), "PIPELINE_GATE_PHASE": phase,
               "PIPELINE_IMPACT_EXPECTED_HASH": manifest.get("selection_hash", "")}
        with mock.patch.dict(os.environ, env):
            return self.runner._run_one(str(self.workspace), self.entry, "test",
                                       str(self.workspace / "gate.log"))

    def test_affected_manifest_runs_only_selected_paths_from_descriptor(self):
        manifest = self._manifest()
        self.assertEqual(self._run(manifest), 0)
        self.assertEqual(json.loads(self.test_capture.read_text(encoding="utf-8")),
                         ["FULL", "tests/test_target.py"])
        execution = json.loads((self.workspace / "run-gates-executed.json").read_text(encoding="utf-8"))
        self.assertEqual(execution[0]["argv"], [sys.executable, str(self.recorder), "FULL", "tests/test_target.py"])
        self.assertEqual(execution[0]["selection_hash"], manifest["selection_hash"])

    def test_closing_and_uncertain_manifests_run_original_full_command(self):
        selected = self._manifest()
        self.assertEqual(self._run(selected, "closing"), 0)
        self.assertEqual(json.loads(self.test_capture.read_text(encoding="utf-8")), ["FULL"])
        uncertain = self._manifest(full=True, graph_complete=False)
        self.assertEqual(self._run(uncertain), 0)
        self.assertEqual(json.loads(self.test_capture.read_text(encoding="utf-8")), ["FULL"])

    def test_analysis_command_is_unchanged_by_impact_selection(self):
        manifest = self._manifest()
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with mock.patch.dict(os.environ, {"PIPELINE_IMPACT_MANIFEST": str(self.manifest_path),
                                          "PIPELINE_GATE_PHASE": "task"}):
            self.assertEqual(self.runner._run_one(str(self.workspace), self.entry, "analyze",
                                                  str(self.workspace / "analyze.log")), 0)
        self.assertEqual(json.loads(self.analyze_capture.read_text(encoding="utf-8")), ["ANALYZE"])

    def test_tampered_manifest_wrong_toolchain_and_unsafe_paths_never_run_tests(self):
        cases = [
            self._manifest(),
            self._manifest(toolchain_id="flutter"),
            self._manifest(tests=["--danger.py"]),
        ]
        cases[0]["selection_hash"] = "0" * 64
        for manifest in cases:
            self.test_capture.unlink(missing_ok=True)
            with self.subTest(manifest=manifest.get("selection_hash")):
                with self.assertRaises(self.runner.GateContractError):
                    self._run(manifest)
                self.assertFalse(self.test_capture.exists())

    def test_run_gates_executes_the_graphify_selected_path_and_ledgers_argv_hash(self):
        graphify = shutil.which("graphify")
        if graphify is None:
            self.skipTest("Graphify is not installed in this test environment")
        version = subprocess.run([graphify, "--version"], capture_output=True, text=True)
        if version.returncode or "0.9.50" not in version.stdout:
            self.skipTest("Graphify is not the R4 allowlisted version")
        root = self.root / "repo"
        root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
        (root / ".gitignore").write_text(".superpowers/\ngraphify-out/\n", encoding="utf-8")
        (root / "src").mkdir()
        (root / "tests").mkdir()
        (root / "src/__init__.py").write_text("", encoding="utf-8")
        (root / "src/app.py").write_text("def run(): return 1\n", encoding="utf-8")
        (root / "tests/test_app.py").write_text(
            "from src.app import run\ndef test_app(): run()\n", encoding="utf-8")
        (root / "tests/test_other.py").write_text("def test_other(): pass\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
        (root / "src/app.py").write_text("def run(): return 2\n", encoding="utf-8")
        workspace = root / ".superpowers/workspace"
        workspace.mkdir(parents=True)
        capture = workspace / "selected.json"
        code = "import json,os,sys;open(os.environ['CAPTURE'],'w').write(json.dumps(sys.argv[1:]))"
        descriptor = {"language": "python", "red_adapter": "pytest_json_report", "commands": {
            "test": {"argv": [sys.executable, "-c", code, "{test_paths}"], "cwd": str(root),
                     "env": {"CAPTURE": str(capture)}},
            "analyze": {"argv": [sys.executable, "-c", "pass"], "cwd": str(root), "env": {}}}}
        (workspace / "plan.json").write_text(json.dumps({"tasks": [
            {"id": 1, "toolchain_id": "python", "touches": ["src/app.py"]}]}), encoding="utf-8")
        (workspace / "ledger.jsonl").write_text(json.dumps({"type": "gate", "task": "-",
            "summary": "configured", "toolchain_id": "python", "toolchain_descriptor": descriptor}) + "\n",
            encoding="utf-8")
        result = subprocess.run(["bash", str(RUN_GATES), str(workspace), "--tasks", "1"],
                                cwd=root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        manifest = json.loads((workspace / "impact-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["mode"], "affected",
                         json.dumps({"reasons": manifest["reasons"], "provenance": manifest["evidence"]["graph_provenance"]}, indent=2))
        self.assertEqual(manifest["tests"], ["tests/test_app.py"])
        self.assertEqual(json.loads(capture.read_text(encoding="utf-8"))[0], "tests/test_app.py")
        self.assertFalse((root / "graphify-out").exists())
        execution_path = workspace / "run-gates-executed.json"
        execution_hash = hashlib.sha256(execution_path.read_bytes()).hexdigest()
        rows = [json.loads(line) for line in (workspace / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        gate_record = next(item for item in rows if item.get("type") == "impact_gate_evidence")
        self.assertEqual(gate_record["gate_status"], "PASS")
        self.assertEqual(gate_record["executed_argv_hash"], execution_hash)


if __name__ == "__main__":
    unittest.main()
