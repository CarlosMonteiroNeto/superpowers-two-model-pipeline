"""Graph-independent full-suite decisions for R4 impact selection."""

import importlib.util
import json
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills/two-model-sdd-pipeline/scripts"
POLICY_PATH = ROOT / "skills/two-model-sdd-pipeline/toolchains/test-impact-rules.json"


def load_selector():
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("r4_impact_preflight_subject", SCRIPTS / "test_impact.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def diff_fixture(files=None):
    return {
        "base_commit": "a" * 40,
        "head_commit": "b" * 40,
        "base_tree_hash": "c" * 64,
        "tree_hash": "d" * 64,
        "config_hash": "e" * 64,
        "environment_hash": "f" * 64,
        "task_scope": ["src/app.py"],
        "test_paths": ["tests/test_app.py", "test/widget_test.dart"],
        "files": files if files is not None else [
            {"status": "modified", "path": "src/app.py"},
        ],
    }


def toolchain(identifier="python", language="python", adapter="pytest_json_report"):
    return {
        "id": identifier,
        "language": language,
        "red_adapter": adapter,
        "commands": {"test": {"argv": ["pytest", "{test_paths}"], "cwd": ".", "env": {}}},
    }


class ImpactPreflightTests(unittest.TestCase):
    def setUp(self):
        self.selector = load_selector()
        self.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    def test_full_suite_inputs_are_classified_before_graph_acquisition(self):
        cases = [
            ("baseline", "baseline", [{"status": "modified", "path": "src/app.py"}], "baseline"),
            ("closing", "closing", [{"status": "modified", "path": "src/app.py"}], "closing"),
            ("dependency configuration", "task", [{"status": "modified", "path": "pyproject.toml"}], "configuration"),
            ("shared infrastructure", "task", [{"status": "modified", "path": "skills/two-model-sdd-pipeline/scripts/run-gates"}], "shared infrastructure"),
            ("unsupported adapter", "task", [{"status": "modified", "path": "src/app.rs"}], "unsupported"),
            ("deleted test", "task", [{"status": "deleted", "path": "tests/test_old.py"}], "deleted test"),
            ("unclassified change", "task", [{"status": "modified", "path": "docs/notes.md"}], "unclassified"),
        ]
        for label, phase, files, expected_reason in cases:
            with self.subTest(label=label):
                selected_toolchains = [toolchain()]
                if label == "unsupported adapter":
                    selected_toolchains = [toolchain("rust", "rust", "cargo")]
                result = self.selector.preflight(diff_fixture(files), selected_toolchains, self.policy, phase)
                self.assertFalse(result["requires_graph"])
                reasons = result["toolchain_reasons"]
                self.assertIn(expected_reason, reasons[selected_toolchains[0]["id"]].lower())

    def test_mixed_toolchains_keep_graph_for_supported_source_selection(self):
        selected = [toolchain(), toolchain("rust", "rust", "cargo")]

        result = self.selector.preflight(diff_fixture(), selected, self.policy, "task")

        self.assertTrue(result["requires_graph"])
        self.assertIsNone(result["toolchain_reasons"]["python"])
        self.assertIn("unsupported", result["toolchain_reasons"]["rust"].lower())

    def test_eligible_source_edit_still_requires_graph_and_agrees_with_selector(self):
        diff = diff_fixture()
        graph = {
            "version": 1,
            "base_commit": diff["base_commit"],
            "base_tree_hash": diff["base_tree_hash"],
            "reverse_edges": {},
        }

        preflight = self.selector.preflight(diff, [toolchain()], self.policy, "task")
        selected = self.selector.select(diff, graph, [toolchain()], self.policy)

        self.assertTrue(preflight["requires_graph"])
        self.assertIsNone(preflight["toolchain_reasons"]["python"])
        self.assertEqual(selected["mode"], "full_suite")
        self.assertIn("production change has no test mapping", " ".join(selected["reasons"]))

    def test_configuration_reason_matches_selector_without_graph_uncertainty(self):
        diff = diff_fixture([{"status": "modified", "path": "pyproject.toml"}])
        graph = {
            "version": 1,
            "base_commit": diff["base_commit"],
            "base_tree_hash": diff["base_tree_hash"],
            "reverse_edges": {},
        }

        preflight = self.selector.preflight(diff, [toolchain()], self.policy, "task")
        selected = self.selector.select(diff, graph, [toolchain()], self.policy)

        reason = preflight["toolchain_reasons"]["python"]
        self.assertEqual(reason, "changed dependency, build, or test configuration requires complete suite")
        self.assertIn(reason, selected["reasons"])


if __name__ == "__main__":
    unittest.main()
