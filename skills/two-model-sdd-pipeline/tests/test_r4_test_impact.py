"""Behavioral contracts for evidence-bound affected-test selection."""
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"
RULES = ROOT / "skills" / "two-model-sdd-pipeline" / "toolchains" / "test-impact-rules.json"


def load_selector(test):
    path = SCRIPTS / "test_impact.py"
    test.assertTrue(path.is_file(), "R4.2 requires scripts/test_impact.py")
    spec = importlib.util.spec_from_file_location("r42_test_impact", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    test.assertTrue(callable(getattr(module, "select", None)))
    return module


BASE = "a" * 40
HEAD = "b" * 40
BASE_TREE = "c" * 64
HEAD_TREE = "d" * 64
CONFIG = "e" * 64
ENVIRONMENT = "f" * 64


def request_fixture():
    diff = {
        "base_commit": BASE,
        "head_commit": HEAD,
        "base_tree_hash": BASE_TREE,
        "tree_hash": HEAD_TREE,
        "config_hash": CONFIG,
        "environment_hash": ENVIRONMENT,
        "task_scope": ["src/calculator.py"],
        "test_paths": [
            "tests/test_api.py",
            "tests/test_calculator.py",
            "integration/test_contract.py",
        ],
        "files": [{"status": "modified", "path": "src/calculator.py"}],
    }
    graph = {
        "version": 1,
        "base_commit": BASE,
        "base_tree_hash": BASE_TREE,
        "reverse_edges": {
            "src/calculator.py": ["src/api.py", "tests/test_calculator.py"],
            "src/api.py": ["contracts/calculator.schema.json", "tests/test_api.py"],
            "contracts/calculator.schema.json": ["integration/test_contract.py"],
        },
    }
    toolchains = [{
        "id": "python-pytest",
        "language": "python",
        "red_adapter": "pytest_json_report",
        "commands": {"test": {"argv": ["python", "-m", "pytest", "-q"], "cwd": ".", "env": {}}},
    }]
    return diff, graph, toolchains


def policy_fixture():
    return json.loads(RULES.read_text(encoding="utf-8"))


class TestImpactSelectionTests(unittest.TestCase):
    def test_transitive_consumers_contracts_and_integration_tests_are_selected(self):
        selector = load_selector(self)
        diff, graph, toolchains = request_fixture()

        result = selector.select(diff, graph, toolchains, policy_fixture())

        self.assertEqual(result["mode"], "affected")
        self.assertEqual(result["tests"], [
            "integration/test_contract.py", "tests/test_api.py", "tests/test_calculator.py",
        ])
        self.assertEqual(result["commands"][0]["argv"], [
            "python", "-m", "pytest", "-q", "integration/test_contract.py",
            "tests/test_api.py", "tests/test_calculator.py",
        ])
        self.assertEqual(result["gaps"], [])
        self.assertTrue(any("src/api.py" in reason for reason in result["reasons"]))
        self.assertEqual(result["identity"], {
            "base_commit": BASE,
            "head_commit": HEAD,
            "base_tree_hash": BASE_TREE,
            "tree_hash": HEAD_TREE,
            "config_hash": CONFIG,
            "environment_hash": ENVIRONMENT,
            "policy_version": policy_fixture()["version"],
        })

    def test_renamed_source_keeps_impact_from_old_and_new_graph_nodes(self):
        selector = load_selector(self)
        diff, graph, toolchains = request_fixture()
        diff["files"] = [{"status": "renamed", "old_path": "src/old.py", "new_path": "src/calculator.py"}]
        diff["task_scope"] = ["src/old.py", "src/calculator.py"]
        graph["reverse_edges"]["src/old.py"] = ["tests/test_api.py"]

        result = selector.select(diff, graph, toolchains, policy_fixture())

        self.assertEqual(result["mode"], "affected")
        self.assertEqual(result["tests"], [
            "integration/test_contract.py", "tests/test_api.py", "tests/test_calculator.py",
        ])
        self.assertTrue(any("src/old.py" in reason for reason in result["reasons"]))

    def test_python_unittest_and_flutter_use_their_explicit_test_adapters(self):
        selector = load_selector(self)
        diff, graph, _ = request_fixture()
        diff["files"] = [
            {"status": "modified", "path": "lib/cart.dart"},
            {"status": "modified", "path": "src/calculator.py"},
        ]
        diff["task_scope"] = ["lib/cart.dart", "src/calculator.py"]
        diff["test_paths"] = ["test/cart_test.dart", "tests/test_calculator.py"]
        graph["reverse_edges"].update({
            "lib/cart.dart": ["test/cart_test.dart"],
            "src/calculator.py": ["tests/test_calculator.py"],
        })
        toolchains = [
            {
                "id": "python-unittest", "language": "python", "red_adapter": "unittest",
                "commands": {"test": {"argv": ["python", "-m", "unittest", "discover"], "cwd": ".", "env": {}}},
            },
            {
                "id": "flutter-default", "language": "flutter", "red_adapter": "flutter_machine",
                "commands": {"test": {"argv": ["flutter", "test"], "cwd": ".", "env": {}}},
            },
        ]

        result = selector.select(diff, graph, toolchains, policy_fixture())

        by_id = {item["toolchain_id"]: item for item in result["commands"]}
        self.assertEqual(by_id["python-unittest"]["argv"], [
            "python", "-m", "unittest", "tests.test_calculator",
        ])
        self.assertEqual(by_id["flutter-default"]["argv"], [
            "flutter", "test", "test/cart_test.dart",
        ])
        self.assertEqual(result["tests"], ["test/cart_test.dart", "tests/test_calculator.py"])

    def test_cli_writes_the_same_stable_selection_from_a_json_request(self):
        diff, graph, toolchains = request_fixture()
        request = {"diff": diff, "graph": graph, "toolchains": toolchains}
        with tempfile.TemporaryDirectory() as temp:
            request_path = pathlib.Path(temp) / "request.json"
            output_path = pathlib.Path(temp) / "impact.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")

            completed = subprocess.run(
                [sys.executable, str(SCRIPTS / "select-tests"), "--request", str(request_path), "--output", str(output_path)],
                cwd=ROOT, capture_output=True, text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            result = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result["mode"], "affected")
            self.assertEqual(result["tests"], [
                "integration/test_contract.py", "tests/test_api.py", "tests/test_calculator.py",
            ])
            self.assertEqual(pathlib.Path(completed.stdout.strip()).resolve(), output_path.resolve())

    def test_manifest_binds_the_dependency_graph_even_when_selected_tests_do_not_change(self):
        selector = load_selector(self)
        diff, graph, toolchains = request_fixture()
        first = selector.select(diff, graph, toolchains, policy_fixture())
        changed_graph = json.loads(json.dumps(graph))
        changed_graph["reverse_edges"]["src/unrelated.py"] = ["src/unused_consumer.py"]

        second = selector.select(diff, changed_graph, toolchains, policy_fixture())

        self.assertEqual(first["tests"], second["tests"])
        self.assertIn("evidence", first)
        self.assertNotEqual(first["evidence"]["graph_hash"], second["evidence"]["graph_hash"])
        self.assertNotEqual(first["selection_hash"], second["selection_hash"])

    def test_accepts_the_r3_source_snapshot_tree_identity_format(self):
        selector = load_selector(self)
        diff, graph, toolchains = request_fixture()
        diff["base_tree_hash"] = "commit:" + BASE + "+sha256:" + BASE_TREE
        diff["tree_hash"] = "commit:" + HEAD + "+sha256:" + HEAD_TREE
        graph["base_tree_hash"] = diff["base_tree_hash"]

        try:
            result = selector.select(diff, graph, toolchains, policy_fixture())
        except ValueError as exc:
            self.fail("R3 source-snapshot identities must be accepted: %s" % exc)

        self.assertEqual(result["mode"], "affected")
        self.assertEqual(result["identity"]["base_tree_hash"], diff["base_tree_hash"])
        self.assertEqual(result["identity"]["tree_hash"], diff["tree_hash"])


if __name__ == "__main__":
    unittest.main()
