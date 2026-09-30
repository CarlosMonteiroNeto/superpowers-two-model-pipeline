import importlib.util
import json
import os
import pathlib
import shutil
import sqlite3
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

    def test_gate_without_run_start_cache_falls_back_without_graphify(self):
        self._write("src/app.py", "def run(): return 2\n")
        self._write("tests/test_extra.py", "VALUE = 2\n")
        self._git("add", "src/app.py")
        gate = subject()
        import test_dependency_graph
        import test_impact
        with mock.patch.object(test_dependency_graph, "build", side_effect=AssertionError("per-gate Graphify is forbidden")) as builder, \
                mock.patch.object(test_impact, "select", wraps=test_impact.select) as selector:
            manifest = gate.create_workspace_manifest(str(self.workspace), ["1"], "tasks")
        self.assertEqual(builder.call_count, 0)
        self.assertIsNone(selector.call_args.args[1])
        self.assertEqual(manifest["mode"], "full_suite")
        self.assertFalse(manifest["evidence"]["graph_provenance"]["complete"])

    def test_task_gate_reuses_run_start_cache_without_graphify(self):
        scripts = str(SCRIPTS)
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import graph_context
        import test_dependency_graph

        source = self._git("rev-parse", "HEAD")
        extracted = {"complete": True,
                     "forward_edges": {"src/app.py": ["tests/test_app.py"]},
                     "reverse_edges": {"tests/test_app.py": ["src/app.py"]},
                     "graphify_version": "0.9.50", "graph_digest": "a" * 64,
                     "source_inventory_hash": "b" * 64, "diagnostics": []}
        with mock.patch.object(test_dependency_graph, "build", return_value=extracted) as build:
            graph_context.prepare(self.workspace, self.root,
                                  self.workspace / "plan.json", source)
        self.assertEqual(build.call_count, 1)
        (self.workspace / "base-commit.txt").write_text(source + "\n", encoding="utf-8")
        self._write("src/app.py", "def run(): return 2\n")
        self._git("add", "src/app.py")
        with mock.patch.object(test_dependency_graph, "build", side_effect=AssertionError("gate must reuse the run cache")):
            manifest = subject().create_workspace_manifest(str(self.workspace), ["1"], "tasks")
        self.assertEqual(manifest["evidence"]["graph_provenance"]["run_start_commit"], source)
        self.assertTrue(manifest["evidence"]["graph_provenance"]["complete"])

    def _prepare_identity_fixture(self):
        subject()
        import graph_context
        import test_dependency_graph

        source = self._git("rev-parse", "HEAD")
        (self.workspace / ".pipeline-identity.json").write_text(
            json.dumps({"identity": "9" * 64}), encoding="utf-8")
        (self.workspace / "base-commit.txt").write_text(source + "\n", encoding="utf-8")
        extracted = {"complete": True,
                     "forward_edges": {"tests/test_app.py": ["src/app.py"]},
                     "reverse_edges": {"src/app.py": ["tests/test_app.py"]},
                     "graphify_version": "0.9.50", "graph_digest": "a" * 64,
                     "source_inventory_hash": "b" * 64, "diagnostics": []}
        with mock.patch.object(test_dependency_graph, "build", return_value=extracted):
            graph_context.prepare(self.workspace, self.root, self.workspace / "plan.json", source)

    def test_gate_rejects_cache_from_another_run_repository_tree_or_policy(self):
        self._prepare_identity_fixture()
        self._write("src/app.py", "def run(): return 2\n")
        gate = subject()
        self.assertEqual(gate.create_workspace_manifest(str(self.workspace), ["1"], "tasks")["mode"],
                         "affected")
        for field, value in (("run_identity", "8" * 64),
                             ("repository", str(self.root / "missing-repository")),
                             ("source_tree", "0" * 40), ("policy_hash", "0" * 64)):
            with self.subTest(field=field):
                db = sqlite3.connect(self.workspace / "graph-context.sqlite3")
                try:
                    original = db.execute("SELECT value FROM metadata WHERE key=?", (field,)).fetchone()[0]
                    db.execute("UPDATE metadata SET value=? WHERE key=?", (value, field))
                    db.commit()
                    manifest = gate.create_workspace_manifest(str(self.workspace), ["1"], "tasks")
                    self.assertEqual(manifest["mode"], "full_suite")
                    self.assertFalse(manifest["evidence"]["graph_provenance"]["complete"])
                finally:
                    db.execute("UPDATE metadata SET value=? WHERE key=?", (original, field))
                    db.commit()
                    db.close()

    def test_linked_worktree_accepts_cache_from_the_same_repository_and_run(self):
        self._prepare_identity_fixture()
        linked = self.root / ".superpowers/linked"
        self._git("worktree", "add", "--detach", str(linked), "HEAD")
        workspace = linked / ".superpowers/workspace"
        shutil.copytree(self.workspace, workspace)
        (linked / "src/app.py").write_text("def run(): return 2\n", encoding="utf-8")
        manifest = subject().create_workspace_manifest(str(workspace), ["1"], "tasks")
        self.assertEqual(manifest["mode"], "affected")
        self.assertEqual(manifest["tests"], ["tests/test_app.py"])

    def test_integration_omits_green_test_only_while_its_inputs_match(self):
        scripts = str(SCRIPTS)
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import graph_context
        import test_dependency_graph

        source = self._git("rev-parse", "HEAD")
        (self.workspace / "base-commit.txt").write_text(source + "\n", encoding="utf-8")
        rows = [json.loads(line) for line in (self.workspace / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        marker = self.root / "green-test-ran.txt"
        rows[0]["toolchain_descriptor"]["commands"]["test"]["argv"] = [
            sys.executable, "-c", "from pathlib import Path; Path('green-test-ran.txt').write_text('ran')"]
        rows[0]["toolchain_descriptor"]["commands"]["analyze"]["argv"] = [sys.executable, "-c", "pass"]
        rows[0]["toolchain_descriptor"]["commands"]["format"]["argv"] = [sys.executable, "-c", "pass"]
        for name in ("test", "analyze", "format"):
            rows[0]["toolchain_descriptor"]["commands"][name]["cwd"] = str(self.root)
        (self.workspace / "ledger.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        extracted = {"complete": True,
                     "forward_edges": {"tests/test_app.py": ["src/app.py"]},
                     "reverse_edges": {"src/app.py": ["tests/test_app.py"]},
                     "graphify_version": "0.9.50", "graph_digest": "a" * 64,
                     "source_inventory_hash": "b" * 64, "diagnostics": []}
        with mock.patch.object(test_dependency_graph, "build", return_value=extracted):
            graph_context.prepare(self.workspace, self.root,
                                  self.workspace / "plan.json", source)
        self._write("src/app.py", "def run(): return 2\n")
        gate = subject()
        with mock.patch.dict("os.environ", {"PIPELINE_GATE_PHASE": "task"}):
            green = gate.create_workspace_manifest(str(self.workspace), ["1"], "tasks")
        self.assertEqual(green["tests"], ["tests/test_app.py"])
        gate.record_green_evidence(self.workspace, "1", green)

        with mock.patch.dict("os.environ", {"PIPELINE_GATE_PHASE": "integration",
                                              "PIPELINE_IMPACT_BASE_COMMIT": source}):
            integrated = gate.create_workspace_manifest(str(self.workspace), ["1"], "tasks")
        self.assertEqual(integrated["commands"][0]["tests"], [])
        self.assertTrue(integrated["commands"][0]["skip_tests"])
        self.assertEqual(integrated["evidence"]["green_subtractions"], [
            {"toolchain_id": "python", "test": "tests/test_app.py"}])
        impact_path = self.workspace / "impact-manifest.json"
        import toolchain_gate
        entry = json.loads((self.workspace / "ledger.jsonl").read_text(encoding="utf-8"))
        env_patch = {"PIPELINE_GATE_PHASE": "integration",
                     "PIPELINE_IMPACT_BASE_COMMIT": source,
                     "PIPELINE_IMPACT_MANIFEST": str(impact_path),
                     "PIPELINE_IMPACT_EXPECTED_HASH": integrated["selection_hash"]}
        with mock.patch.dict("os.environ", env_patch):
            rc = toolchain_gate._run_one(str(self.workspace), entry, "test",
                                         str(self.workspace / "green-test.log"))
        self.assertEqual(rc, 0)
        self.assertFalse(marker.exists(), "matching Green evidence must suppress only the duplicate test command")

        self._write("src/app.py", "def run(): return 3\n")
        with mock.patch.dict("os.environ", {"PIPELINE_GATE_PHASE": "integration",
                                              "PIPELINE_IMPACT_BASE_COMMIT": source}):
            changed = gate.create_workspace_manifest(str(self.workspace), ["1"], "tasks")
        self.assertEqual(changed["commands"][0]["tests"], ["tests/test_app.py"])
        self.assertNotIn("skip_tests", changed["commands"][0])
        env_patch["PIPELINE_IMPACT_EXPECTED_HASH"] = changed["selection_hash"]
        with mock.patch.dict("os.environ", env_patch):
            rc = toolchain_gate._run_one(str(self.workspace), entry, "test",
                                         str(self.workspace / "changed-test.log"))
        self.assertEqual(rc, 0)
        self.assertTrue(marker.is_file(), "changed relevant source invalidates the Green subtraction")

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

    def test_integration_manifest_binds_diff_to_run_start_graph(self):
        run_start = self._git("rev-parse", "HEAD")
        scripts = str(SCRIPTS)
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import graph_context
        import test_dependency_graph
        extracted = {"complete": True,
                     "forward_edges": {"tests/test_app.py": ["src/app.py"]},
                     "reverse_edges": {"src/app.py": ["tests/test_app.py"]},
                     "graphify_version": "0.9.50", "graph_digest": "a" * 64,
                     "source_inventory_hash": "b" * 64, "diagnostics": []}
        with mock.patch.object(test_dependency_graph, "build", return_value=extracted):
            graph_context.prepare(self.workspace, self.root,
                                  self.workspace / "plan.json", run_start)
        self._write("src/app.py", "def run(): return 4\n")
        self._git("add", "src/app.py")
        self._git("commit", "-qm", "pre-wave commit")
        base = self._git("rev-parse", "HEAD")
        self._write("src/app.py", "def run(): return 5\n")
        gate = subject()
        import test_impact
        (self.workspace / "base-commit.txt").write_text(run_start + "\n", encoding="utf-8")
        with mock.patch.dict("os.environ", {"PIPELINE_IMPACT_BASE_COMMIT": base}), \
                mock.patch.object(test_impact, "select", wraps=test_impact.select) as selector:
            manifest = gate.create_workspace_manifest(str(self.workspace), ["1"], "tasks")
        diff = selector.call_args.args[0]
        self.assertEqual(diff["base_commit"], base)
        self.assertEqual(manifest["identity"]["base_commit"], base)
        self.assertEqual(manifest["evidence"]["graph_provenance"]["run_start_commit"], run_start)

    def test_deleted_test_selects_full_suite_even_when_graphs_are_complete(self):
        source = self._git("rev-parse", "HEAD")
        scripts = str(SCRIPTS)
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import graph_context
        import test_dependency_graph
        extracted = {"complete": True, "forward_edges": {"tests/test_app.py": ["src/app.py"]},
                     "reverse_edges": {"src/app.py": ["tests/test_app.py"]},
                     "graphify_version": "0.9.50", "graph_digest": "a" * 64,
                     "source_inventory_hash": "b" * 64, "diagnostics": []}
        with mock.patch.object(test_dependency_graph, "build", return_value=extracted):
            graph_context.prepare(self.workspace, self.root,
                                  self.workspace / "plan.json", source)
        (self.workspace / "base-commit.txt").write_text(source + "\n", encoding="utf-8")
        (self.root / "tests/test_app.py").unlink()
        self._git("add", "-A")
        graph = {"complete": True, "reverse_edges": {}, "graphify_version": "0.9.50",
                 "graph_digest": "a" * 64, "source_inventory_hash": "b" * 64, "diagnostics": []}
        gate = subject()
        manifest = gate.create_workspace_manifest(str(self.workspace), ["1"], "tasks")
        self.assertEqual(manifest["mode"], "full_suite")
        self.assertTrue(any("deleted test" in reason for reason in manifest["reasons"]))


if __name__ == "__main__":
    unittest.main()




