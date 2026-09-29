"""Conservative fallback and input-safety contracts for R4 impact selection."""
import importlib.util
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"
RULES = ROOT / "skills" / "two-model-sdd-pipeline" / "toolchains" / "test-impact-rules.json"


def load_selector(test):
    path = SCRIPTS / "test_impact.py"
    test.assertTrue(path.is_file(), "R4.2 requires scripts/test_impact.py")
    spec = importlib.util.spec_from_file_location("r42_test_impact_fallbacks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    test.assertTrue(callable(getattr(module, "select", None)))
    return module


def fixture():
    base, head, base_tree = "a" * 40, "b" * 40, "c" * 64
    diff = {
        "base_commit": base, "head_commit": head, "base_tree_hash": base_tree,
        "tree_hash": "d" * 64, "config_hash": "e" * 64, "environment_hash": "f" * 64,
        "task_scope": ["src/service.py"], "test_paths": ["tests/test_service.py"],
        "files": [{"status": "modified", "path": "src/service.py"}],
    }
    graph = {"version": 1, "base_commit": base, "base_tree_hash": base_tree,
             "reverse_edges": {"src/service.py": ["tests/test_service.py"]}}
    toolchains = [{"id": "python-pytest", "language": "python", "red_adapter": "pytest_json_report",
                   "commands": {"test": {"argv": ["pytest", "-q"], "cwd": ".", "env": {}}}}]
    policy = json.loads(RULES.read_text(encoding="utf-8"))
    return diff, graph, toolchains, policy


class TestImpactFallbackTests(unittest.TestCase):
    def test_stale_graph_expands_to_full_suite_with_reason(self):
        selector = load_selector(self)
        diff, graph, toolchains, policy = fixture()
        graph["base_commit"] = "9" * 40

        result = selector.select(diff, graph, toolchains, policy)

        self.assertEqual(result["mode"], "full_suite")
        self.assertEqual(result["commands"][0]["argv"], ["pytest", "-q"])
        self.assertTrue(any("stale" in item["reason"].lower() for item in result["reasons_detail"]))

    def test_unknown_language_retains_full_suite_descriptor(self):
        selector = load_selector(self)
        diff, graph, toolchains, policy = fixture()
        toolchains = [{"id": "node-default", "language": "node", "commands": {
            "test": {"argv": ["npm", "test"], "cwd": ".", "env": {}}
        }}]

        result = selector.select(diff, graph, toolchains, policy)

        self.assertEqual(result["mode"], "full_suite")
        self.assertEqual(result["commands"][0]["argv"], ["npm", "test"])
        self.assertTrue(any("unsupported" in item["reason"].lower() for item in result["reasons_detail"]))

    def test_python_dependency_configuration_change_expands_to_full_suite(self):
        selector = load_selector(self)
        diff, graph, toolchains, policy = fixture()
        diff["files"] = [{"status": "modified", "path": "pyproject.toml"}]
        diff["task_scope"] = ["pyproject.toml"]

        result = selector.select(diff, graph, toolchains, policy)

        self.assertEqual(result["mode"], "full_suite")
        self.assertTrue(any("configuration" in item["reason"].lower() for item in result["reasons_detail"]))

    def test_setup_py_build_configuration_change_expands_even_with_a_test_mapping(self):
        selector = load_selector(self)
        diff, graph, toolchains, policy = fixture()
        diff["files"] = [{"status": "modified", "path": "setup.py"}]
        diff["task_scope"] = ["setup.py"]
        graph["reverse_edges"]["setup.py"] = ["tests/test_service.py"]

        result = selector.select(diff, graph, toolchains, policy)

        self.assertEqual(result["mode"], "full_suite")
        self.assertEqual(result["commands"][0]["argv"], ["pytest", "-q"])
        self.assertTrue(any("configuration" in item["reason"].lower() for item in result["reasons_detail"]))

    def test_shared_infrastructure_and_generated_contract_changes_expand_to_full_suite(self):
        selector = load_selector(self)
        for path in ("skills/two-model-sdd-pipeline/scripts/cmd", "schemas/api.schema.json"):
            with self.subTest(path=path):
                diff, graph, toolchains, policy = fixture()
                diff["files"] = [{"status": "modified", "path": path}]
                diff["task_scope"] = [path]

                result = selector.select(diff, graph, toolchains, policy)

                self.assertEqual(result["mode"], "full_suite")
                self.assertTrue(result["reasons_detail"])

    def test_production_change_without_a_test_mapping_is_an_explicit_gap(self):
        selector = load_selector(self)
        diff, graph, toolchains, policy = fixture()
        graph["reverse_edges"] = {}

        result = selector.select(diff, graph, toolchains, policy)

        self.assertEqual(result["mode"], "full_suite")
        self.assertEqual(result["gaps"], ["src/service.py"])
        self.assertTrue(any("no test" in item["reason"].lower() for item in result["reasons_detail"]))

    def test_source_unclassified_by_every_toolchain_is_a_gap_and_falls_back(self):
        selector = load_selector(self)
        diff, graph, toolchains, policy = fixture()
        diff["files"] = [{"status": "modified", "path": "frontend/runtime.js"}]
        diff["task_scope"] = ["frontend/runtime.js"]

        result = selector.select(diff, graph, toolchains, policy)

        self.assertEqual(result["mode"], "full_suite")
        self.assertEqual(result["gaps"], ["frontend/runtime.js"])
        self.assertEqual(result["commands"][0]["argv"], ["pytest", "-q"])

    def test_deleted_test_and_deleted_test_target_broaden_verification(self):
        selector = load_selector(self)
        diff, graph, toolchains, policy = fixture()
        diff["files"] = [{"status": "deleted", "path": "tests/test_service.py"}]
        diff["task_scope"] = ["tests/test_service.py"]
        diff["test_paths"] = []
        graph["reverse_edges"] = {}

        result = selector.select(diff, graph, toolchains, policy)

        self.assertEqual(result["mode"], "full_suite")
        self.assertTrue(any("deleted test" in item["reason"].lower() for item in result["reasons_detail"]))

    def test_cycles_terminate_and_output_order_is_deterministic(self):
        selector = load_selector(self)
        diff, graph, toolchains, policy = fixture()
        graph["reverse_edges"] = {
            "src/service.py": ["src/shared.py"],
            "src/shared.py": ["src/service.py", "tests/test_service.py"],
        }

        first = selector.select(diff, graph, toolchains, policy)
        second = selector.select(diff, graph, toolchains, policy)

        self.assertEqual(first, second)
        self.assertEqual(first["tests"], ["tests/test_service.py"])
        self.assertEqual(first["mode"], "affected")

    def test_malformed_graph_and_unsafe_paths_are_rejected(self):
        selector = load_selector(self)
        diff, graph, toolchains, policy = fixture()
        graph["reverse_edges"] = {"src/service.py": "tests/test_service.py"}
        with self.assertRaisesRegex(ValueError, "reverse_edges"):
            selector.select(diff, graph, toolchains, policy)

        diff, graph, toolchains, policy = fixture()
        diff["files"] = [{"status": "modified", "path": "../outside.py"}]
        with self.assertRaisesRegex(ValueError, "path"):
            selector.select(diff, graph, toolchains, policy)

    def test_unittest_rejects_non_module_test_paths_by_falling_back_to_full_suite(self):
        selector = load_selector(self)
        diff, graph, toolchains, policy = fixture()
        diff["test_paths"] = ["tests/test-service.py"]
        graph["reverse_edges"]["src/service.py"] = ["tests/test-service.py"]
        toolchains[0] = {
            "id": "python-unittest", "language": "python", "red_adapter": "unittest",
            "commands": {"test": {"argv": ["python", "-m", "unittest", "discover"], "cwd": ".", "env": {}}},
        }

        result = selector.select(diff, graph, toolchains, policy)

        self.assertEqual(result["mode"], "full_suite")
        self.assertEqual(result["commands"][0]["argv"], ["python", "-m", "unittest", "discover"])
        self.assertTrue(any("invalid unittest module" in item["reason"].lower() for item in result["reasons_detail"]))


if __name__ == "__main__":
    unittest.main()
