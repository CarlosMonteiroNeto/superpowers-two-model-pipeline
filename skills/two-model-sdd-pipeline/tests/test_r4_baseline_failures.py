"""Behavior tests for classifying recorded baseline failures."""

import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills/two-model-sdd-pipeline/scripts/baseline_failures.py"


def subject():
    spec = importlib.util.spec_from_file_location("baseline_failures", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evidence(failures, *, source="a" * 64, environment="b" * 64, command="c" * 64):
    return {
        "source_hash": source,
        "environment_hash": environment,
        "command_hash": command,
        "suites": [{"id": "unit", "failures": failures, "raw_result": {"exit_code": 1}}],
    }


def failure(test="package.Case.test_one", signature="AssertionError: 1 != 2"):
    return {"test": test, "signature": signature, "raw": "FAIL: " + test + "\n" + signature}


class BaselineComparisonTests(unittest.TestCase):
    def test_same_identity_and_signature_is_inherited_and_retains_raw_evidence(self):
        baseline = evidence([failure()])
        current = evidence([failure()], source="d" * 64)
        result = subject().compare(baseline, current)
        self.assertEqual(result["status"], "baseline_only")
        self.assertEqual(result["inherited"], [current["suites"][0]["failures"][0] | {"suite": "unit"}])
        self.assertEqual(result["new"], [])
        self.assertEqual(result["ambiguous"], [])

    def test_new_failure_blocks_affected_suite_but_healthy_suite_remains_unaffected(self):
        baseline = evidence([failure()])
        current = evidence([failure(), failure("package.Case.test_two", "ValueError: new")], source="d" * 64)
        current["suites"].append({"id": "integration", "failures": [], "raw_result": {"exit_code": 0}})
        result = subject().compare(baseline, current)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual([item["test"] for item in result["new"]], ["package.Case.test_two"])
        self.assertEqual(result["affected_suites"], ["unit"])
        self.assertEqual(result["unaffected_suites"], ["integration"])

    def test_changed_signature_and_renamed_test_are_ambiguous(self):
        baseline = evidence([failure()])
        for changed in (failure(signature="AssertionError: 3 != 4"),
                        failure(test="package.Case.test_renamed")):
            with self.subTest(changed=changed):
                result = subject().compare(baseline, evidence([changed], source="d" * 64))
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(len(result["ambiguous"]), 1)
                self.assertEqual(result["inherited"], [])

    def test_environment_or_command_drift_cannot_prove_inherited_failure(self):
        baseline = evidence([failure()])
        for current in (evidence([failure()], environment="d" * 64),
                        evidence([failure()], command="d" * 64)):
            with self.subTest(current=current):
                result = subject().compare(baseline, current)
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["inherited"], [])
                self.assertEqual(len(result["ambiguous"]), 1)

    def test_unexplained_failing_result_is_never_silent_baseline(self):
        current = evidence([])
        current["suites"][0]["raw_result"] = {"exit_code": 1, "stderr": "collection failed"}
        result = subject().compare(evidence([]), current)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["ambiguous"])

    def test_baseline_capture_rejects_missing_raw_failure_or_source_identity(self):
        module = subject()
        for bad in (evidence([{"test": "t", "signature": "boom"}]),
                    evidence([failure()], source="unknown")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                module.validate_evidence(bad)

    def test_literal_star_in_error_signature_is_not_a_waiver_wildcard(self):
        star = failure(signature="TypeError: unsupported operand for *")
        baseline = evidence([star])
        current = evidence([star], source="d" * 64)
        self.assertEqual(subject().compare(baseline, current)["status"], "baseline_only")


if __name__ == "__main__":
    unittest.main()
