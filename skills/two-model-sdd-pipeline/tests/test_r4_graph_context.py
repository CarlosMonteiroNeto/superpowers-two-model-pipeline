import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"


def load_graph_context(test):
    sys.path.insert(0, str(SCRIPTS))
    path = SCRIPTS / "graph_context.py"
    test.assertTrue(path.is_file(), "R4 requires the script-owned graph context cache")
    spec = importlib.util.spec_from_file_location("r4_graph_context", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def complete_graph(version="0.9.50"):
    return {
        "complete": True,
        "forward_edges": {
            "src/api.py": ["src/core.py"],
            "tests/test_api.py": ["src/api.py"],
        },
        "reverse_edges": {
            "src/api.py": ["tests/test_api.py"],
            "src/core.py": ["src/api.py"],
        },
        "graphify_version": version,
        "graph_digest": "a" * 64,
        "source_inventory_hash": "b" * 64,
        "diagnostics": [],
    }


class GraphContextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="r4-graph-context-")
        self.root = pathlib.Path(self.temporary.name) / "repo"
        self.root.mkdir()
        self._git("init", "-q")
        self._git("config", "user.email", "test@example.invalid")
        self._git("config", "user.name", "Graph Context Test")
        self._write("src/api.py", "from src.core import calculate\n")
        self._write("src/core.py", "def calculate(): return 1\n")
        self._write("tests/test_api.py", "from src.api import calculate\n")
        self._write("pyproject.toml", '[project]\nname = "graph-context-test"\n')
        self._git("add", "-A")
        self._git("commit", "-qm", "run start")
        self.source_commit = self._git("rev-parse", "HEAD")
        self.workspace = self.root / ".superpowers" / "workspace"
        self.workspace.mkdir(parents=True)
        self.plan_path = self.workspace / "plan.json"
        self.plan_path.write_text(json.dumps({
            "version": 1,
            "tasks": [
                {"id": 1, "touches": ["src/api.py"]},
                {"id": 2, "touches": ["src/core.py"]},
            ],
        }), encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def _git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def _write(self, relative, contents):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def test_prepares_one_graph_and_persists_task_scoped_dependency_context(self):
        module = load_graph_context(self)
        import test_dependency_graph

        with mock.patch.object(test_dependency_graph, "build", return_value=complete_graph()) as build:
            result = module.prepare(self.workspace, self.root, self.plan_path, self.source_commit)

        self.assertEqual(build.call_count, 1)
        self.assertTrue(result["complete"])
        self.assertEqual(result["source_commit"], self.source_commit)
        self.assertRegex(result["graph_digest"], r"^[0-9a-f]{64}$")
        self.assertTrue((self.workspace / "graph-context.sqlite3").is_file())
        self.assertTrue((self.workspace / "graph-task-context" / "1.json").is_file())

        api = module.load_task_context(self.workspace, {"id": 1, "touches": ["src/api.py"]})
        self.assertEqual(api["dependencies"], ["src/core.py"])
        self.assertEqual(api["consumers"], ["tests/test_api.py"])
        self.assertEqual(api["tests"], ["tests/test_api.py"])

        core = module.load_task_context(self.workspace, {"id": 2, "touches": ["src/core.py"]})
        self.assertEqual(core["consumers"], ["src/api.py", "tests/test_api.py"])

    def test_plan_correction_reuses_graph_cache_and_derives_its_own_context(self):
        module = load_graph_context(self)
        import test_dependency_graph

        with mock.patch.object(test_dependency_graph, "build", return_value=complete_graph()) as build:
            module.prepare(self.workspace, self.root, self.plan_path, self.source_commit)
            plan = json.loads(self.plan_path.read_text(encoding="utf-8"))
            plan["tasks"].append({"id": 3, "touches": ["src/core.py"]})
            self.plan_path.write_text(json.dumps(plan), encoding="utf-8")
            result = module.prepare(self.workspace, self.root, self.plan_path, self.source_commit)

        self.assertEqual(build.call_count, 1)
        self.assertTrue(result["complete"])
        task_context = module.load_task_context(
            self.workspace, {"id": 3, "touches": ["src/core.py"]})
        self.assertEqual(task_context["consumers"], ["src/api.py", "tests/test_api.py"])

    def test_stale_source_tree_or_run_identity_rebuilds_cache(self):
        module = load_graph_context(self)
        import test_dependency_graph

        with mock.patch.object(test_dependency_graph, "build", return_value=complete_graph()) as build:
            module.prepare(self.workspace, self.root, self.plan_path, self.source_commit)
            self._write("src/new.py", "VALUE = 2\n")
            self._git("add", "src/new.py")
            self._git("commit", "-qm", "advance run-start tree")
            next_commit = self._git("rev-parse", "HEAD")
            result = module.prepare(self.workspace, self.root, self.plan_path, next_commit)
            self.assertEqual(build.call_count, 2)
            self.assertEqual(result["source_commit"], next_commit)

            identity = {"identity": "d" * 64}
            (self.workspace / ".pipeline-identity.json").write_text(json.dumps(identity), encoding="utf-8")
            module.prepare(self.workspace, self.root, self.plan_path, next_commit)
            self.assertEqual(build.call_count, 3)

    def test_failed_refresh_marker_prevents_reuse_of_old_cache(self):
        module = load_graph_context(self)
        import test_dependency_graph

        with mock.patch.object(test_dependency_graph, "build", return_value=complete_graph()):
            module.prepare(self.workspace, self.root, self.plan_path, self.source_commit)
        with self.assertRaises(OSError):
            module.prepare(self.workspace, self.root, self.workspace / "missing-plan.json",
                           self.source_commit)
        context = module.load_task_context(
            self.workspace, {"id": 1, "touches": ["src/api.py"]})
        self.assertFalse(context["complete"])
        self.assertTrue(context["requires_full_suite"])
        self.assertEqual(context["dependencies"], [])

    def test_incomplete_graph_never_exposes_partial_task_edges(self):
        module = load_graph_context(self)
        import test_dependency_graph

        incomplete = complete_graph()
        incomplete.update(complete=False, diagnostics=["unresolved local import"])
        with mock.patch.object(test_dependency_graph, "build", return_value=incomplete):
            result = module.prepare(self.workspace, self.root, self.plan_path, self.source_commit)

        self.assertFalse(result["complete"])
        task_context = module.load_task_context(
            self.workspace, {"id": 1, "touches": ["src/api.py"]})
        self.assertFalse(task_context["complete"])
        self.assertEqual(task_context["dependencies"], [])
        self.assertEqual(task_context["consumers"], [])
        self.assertTrue(task_context["requires_full_suite"])


if __name__ == "__main__":
    unittest.main()
