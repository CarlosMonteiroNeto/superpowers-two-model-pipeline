"""Behavior tests for candidate-bound baseline waivers and the CLI."""

import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills/two-model-sdd-pipeline/scripts"
SCHEMA = ROOT / "skills/two-model-sdd-pipeline/schemas/baseline-waiver.schema.json"


def subject():
    spec = importlib.util.spec_from_file_location("baseline_failures", SCRIPTS / "baseline_failures.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def failure():
    return {"suite": "unit", "test": "package.Case.test_one", "signature": "AssertionError: 1 != 2",
            "raw": "FAIL: package.Case.test_one\nAssertionError: 1 != 2"}


def candidate():
    return {"candidate_commit": "a" * 40, "source_hash": "b" * 64,
            "environment_hash": "c" * 64, "command_hash": "d" * 64,
            "baseline_source_hash": "e" * 64, "failures": [failure()],
            "comparison_status": "baseline_only"}


def waiver():
    return {"approved_by": "user", "approval_record": "user-approval-123",
            "candidate_commit": "a" * 40, "source_hash": "b" * 64,
            "environment_hash": "c" * 64, "command_hash": "d" * 64,
            "baseline_source_hash": "e" * 64,
            "failures": [{k: failure()[k] for k in ("suite", "test", "signature")} ]}


class BaselineWaiverTests(unittest.TestCase):
    def test_exact_user_waiver_marks_completion_waived_and_keeps_raw_failure(self):
        result = subject().validate_waiver(waiver(), candidate())
        self.assertEqual(result["status"], "completed_with_waived_baseline")
        self.assertEqual(result["failures"], [failure()])

    def test_candidate_environment_command_and_baseline_binding_expire_waiver(self):
        for field in ("candidate_commit", "source_hash", "environment_hash",
                      "command_hash", "baseline_source_hash"):
            changed = candidate()
            changed[field] = "f" * len(changed[field])
            with self.subTest(field=field), self.assertRaises(ValueError):
                subject().validate_waiver(waiver(), changed)

    def test_broadened_stale_or_partial_failure_list_is_rejected(self):
        cases = []
        changed = candidate(); changed["failures"][0]["test"] = "package.Case.test_renamed"; cases.append(changed)
        changed = candidate(); changed["failures"][0]["signature"] = "new error"; cases.append(changed)
        changed = candidate(); changed["failures"].append({**failure(), "test": "package.Case.test_two"}); cases.append(changed)
        for changed in cases:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                subject().validate_waiver(waiver(), changed)

    def test_worker_approval_and_wildcard_are_rejected(self):
        for changed in ({**waiver(), "approved_by": "operator"},
                        {**waiver(), "failures": [{"suite": "unit", "test": "*", "signature": "*"}]}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                subject().validate_waiver(changed, candidate())

    def test_new_or_ambiguous_failures_cannot_be_waived(self):
        for status in ("blocked", "unknown"):
            changed = candidate(); changed["comparison_status"] = status
            with self.subTest(status=status), self.assertRaises(ValueError):
                subject().validate_waiver(waiver(), changed)

    def test_schema_declares_exact_waiver_shape(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["approved_by"]["const"], "user")
        self.assertFalse(schema["properties"]["failures"]["items"]["additionalProperties"])

    def test_cli_compare_emits_json_and_nonzero_for_regression(self):
        base = {"source_hash": "a" * 64, "environment_hash": "b" * 64,
                "command_hash": "c" * 64, "suites": [{"id": "unit", "failures": [], "raw_result": {"exit_code": 0}}]}
        current = json.loads(json.dumps(base))
        current["source_hash"] = "d" * 64
        current["suites"][0]["failures"] = [{k: failure()[k] for k in ("test", "signature", "raw")}]
        current["suites"][0]["raw_result"] = {"exit_code": 1}
        with tempfile.TemporaryDirectory() as temp:
            p = pathlib.Path(temp)
            (p / "base.json").write_text(json.dumps(base), encoding="utf-8")
            (p / "current.json").write_text(json.dumps(current), encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPTS / "baseline-check"), "compare",
                                     str(p / "base.json"), str(p / "current.json")],
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "blocked")

    def test_cli_capture_preserves_raw_result_and_refuses_overwrite(self):
        baseline = {"source_hash": "a" * 64, "environment_hash": "b" * 64,
                    "command_hash": "c" * 64,
                    "suites": [{"id": "unit", "failures": [{k: failure()[k] for k in ("test", "signature", "raw")}],
                                "raw_result": {"exit_code": 1, "stderr": "raw runner output"}}]}
        with tempfile.TemporaryDirectory() as temp:
            p = pathlib.Path(temp)
            source = p / "results.json"; source.write_text(json.dumps(baseline), encoding="utf-8")
            output = p / "recorded.json"
            args = [sys.executable, str(SCRIPTS / "baseline-check"), "capture", str(source), str(output)]
            first = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            recorded = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(recorded["suites"], baseline["suites"])
            self.assertIn("captured_at_utc", recorded)
            second = subprocess.run(args, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), recorded)


if __name__ == "__main__":
    unittest.main()
