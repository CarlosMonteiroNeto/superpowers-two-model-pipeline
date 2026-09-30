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


def subject():
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("gate_evidence_graph_tests", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GraphifyGateEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self._git("init", "-q")
        self._git("config", "user.email", "test@example.invalid")
        self._git("config", "user.name", "Test")
        (self.root / ".gitignore").write_text(".superpowers/\ngraphify-out/\n", encoding="utf-8")
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

    def tearDown(self):
        self.temporary.cleanup()

    def _git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True).stdout.decode("utf-8", "replace").strip()

    def _write(self, name, contents):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")

    def test_builds_distinct_bound_snapshots_and_passes_union_graph_to_selector(self):
        self._write("src/app.py", "def run(): return 2\n")
        self._write("tests/test_extra.py", "VALUE = 2\n")
        self._git("add", "src/app.py")
        self._write("tests/test_app.py", "from src import app\ndef test_run(): app.run()\n# candidate\n")
        calls = []

        def build(snapshot, expected_version):
            snapshot = pathlib.Path(snapshot)
            calls.append((snapshot, expected_version, sorted(
                p.relative_to(snapshot).as_posix() for p in snapshot.rglob("*") if p.is_file())))
            edge = {"src/old.py": ["tests/test_old.py"]} if len(calls) == 1 else {
                "src/app.py": ["tests/test_app.py"]}
            return {"complete": True, "reverse_edges": edge,
                    "graphify_version": expected_version,
                    "graph_digest": ("a" if len(calls) == 1 else "c") * 64,
                    "source_inventory_hash": "b" * 64, "diagnostics": []}

        gate = subject()
        import test_dependency_graph
        import test_impact
        with mock.patch.object(test_dependency_graph, "build", side_effect=build) as builder, \
                mock.patch.object(test_impact, "select", wraps=test_impact.select) as selector:
            manifest = gate.create_workspace_manifest(str(self.workspace), ["1"], "tasks")
        self.assertEqual(builder.call_count, 2)
        self.assertNotEqual(calls[0][0], calls[1][0])
        self.assertTrue(any("tests/test_extra.py" in paths for _, _, paths in calls))
        self.assertTrue(any(".git" not in paths for _, _, paths in calls))
        self.assertFalse(any("graphify-out" in "/".join(paths) for _, _, paths in calls))
        graph = selector.call_args.args[1]
        self.assertEqual(graph["reverse_edges"], {"src/app.py": ["tests/test_app.py"], "src/old.py": ["tests/test_old.py"]})
        self.assertEqual(graph["version"], 1)
        self.assertEqual(manifest["mode"], "affected")
        self.assertEqual(manifest["tests"], ["tests/test_app.py", "tests/test_extra.py"])
        self.assertIn("graph_provenance", manifest["evidence"])
        self.assertEqual(manifest["evidence"]["graph_provenance"]["graphify_version"], "0.9.50")
        self.assertEqual(manifest["evidence"]["graph_provenance"]["base"]["graph_digest"], "a" * 64)
        self.assertEqual(manifest["evidence"]["graph_provenance"]["candidate"]["graph_digest"], "c" * 64)

    def test_incomplete_graph_from_either_snapshot_falls_back_without_partial_edges(self):
        self._write("src/app.py", "def run(): return 3\n")
        results = [
            {"complete": True, "reverse_edges": {"src/app.py": ["tests/test_app.py"]},
             "graphify_version": "0.9.50", "graph_digest": "a" * 64,
             "source_inventory_hash": "b" * 64, "diagnostics": []},
            {"complete": False, "reverse_edges": {"src/app.py": ["tests/test_app.py"]},
             "graphify_version": "0.9.50", "graph_digest": "c" * 64,
             "source_inventory_hash": "d" * 64, "diagnostics": ["failed source"]},
        ]
        gate = subject()
        import test_dependency_graph
        with mock.patch.object(test_dependency_graph, "build", side_effect=results):
            manifest = gate.create_workspace_manifest(str(self.workspace), ["1"], "tasks")
        self.assertEqual(manifest["mode"], "full_suite")
        self.assertEqual(manifest["commands"][0]["argv"], ["pytest", "{test_paths}"])
        self.assertTrue(any("incomplete" in reason.lower() or "unavailable" in reason.lower()
                            or "graph" in reason.lower() for reason in manifest["reasons"]))

    def test_configuration_change_forces_full_suite_even_with_complete_graph(self):
        self._write("pubspec.yaml", "name: changed\n")
        graph = {"complete": True, "reverse_edges": {}, "graphify_version": "0.9.50",
                 "graph_digest": "a" * 64, "source_inventory_hash": "b" * 64, "diagnostics": []}
        gate = subject()
        import test_dependency_graph
        with mock.patch.object(test_dependency_graph, "build", return_value=graph):
            manifest = gate.create_workspace_manifest(str(self.workspace), ["1"], "tasks")
        self.assertEqual(manifest["mode"], "full_suite")
        self.assertIn("pubspec.yaml", manifest["gaps"] or manifest["scope_paths"] or ["pubspec.yaml"])

    def test_integration_manifest_uses_exact_pre_wave_commit_as_graph_base(self):
        base = self._git("rev-parse", "HEAD")
        self._write("src/app.py", "def run(): return 4\n")
        self._git("add", "src/app.py")
        self._git("commit", "-qm", "integrated candidate")
        head = self._git("rev-parse", "HEAD")
        calls = []

        def build(snapshot, expected_version):
            snapshot = pathlib.Path(snapshot)
            calls.append((sorted(path.relative_to(snapshot).as_posix()
                                 for path in snapshot.rglob("*") if path.is_file()),
                          (snapshot / "src/app.py").read_text(encoding="utf-8")))
            return {"complete": True, "reverse_edges": {"src/app.py": ["tests/test_app.py"]},
                    "graphify_version": expected_version, "graph_digest": "e" * 64,
                    "source_inventory_hash": "f" * 64, "diagnostics": []}

        gate = subject()
        import test_dependency_graph
        import test_impact
        with mock.patch.dict("os.environ", {"PIPELINE_IMPACT_BASE_COMMIT": base}), \
                mock.patch.object(test_dependency_graph, "build", side_effect=build), \
                mock.patch.object(test_impact, "select", wraps=test_impact.select) as selector:
            manifest = gate.create_workspace_manifest(str(self.workspace), ["1"], "tasks")
        diff = selector.call_args.args[0]
        self.assertEqual(diff["base_commit"], base)
        self.assertEqual(diff["head_commit"], head)
        self.assertEqual(manifest["identity"]["base_commit"], base)
        self.assertEqual(manifest["evidence"]["graph_provenance"]["base_commit"], base)
        self.assertIn("return 1", calls[0][1])
        self.assertIn("return 4", calls[1][1])

    def test_deleted_test_selects_full_suite_even_when_graphs_are_complete(self):
        (self.root / "tests/test_app.py").unlink()
        self._git("add", "-A")
        graph = {"complete": True, "reverse_edges": {}, "graphify_version": "0.9.50",
                 "graph_digest": "a" * 64, "source_inventory_hash": "b" * 64, "diagnostics": []}
        gate = subject()
        import test_dependency_graph
        with mock.patch.object(test_dependency_graph, "build", return_value=graph):
            manifest = gate.create_workspace_manifest(str(self.workspace), ["1"], "tasks")
        self.assertEqual(manifest["mode"], "full_suite")
        self.assertTrue(any("deleted test" in reason for reason in manifest["reasons"]))


if __name__ == "__main__":
    unittest.main()




