"""Behavior tests for candidate-bound baseline waivers and the CLI."""

import importlib.util
import hashlib
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


def candidate(testcase):
    temporary = tempfile.TemporaryDirectory()
    testcase.addCleanup(temporary.cleanup)
    root = pathlib.Path(temporary.name)
    def evidence(source):
        return {"source_hash": source, "environment_hash": "c" * 64,
                "command_hash": "d" * 64,
                "suites": [{"id": "unit", "tests": [failure()["test"]],
                            "failures": [{k: failure()[k] for k in ("test", "signature", "raw")}],
                            "raw_result": {"status": "completed", "exit_code": 1}}]}
    baseline, current = evidence("e" * 64), evidence("b" * 64)
    comparison = subject().compare(baseline, current)
    comparison_hash = hashlib.sha256(json.dumps(comparison, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    event = {"type": "baseline_waiver_approved", "actor": "user",
             "approval_record": "user-approval-123", "candidate_commit": "a" * 40,
             "comparison_hash": comparison_hash}
    ledger = root / "ledger.jsonl"
    ledger.write_text(json.dumps(event) + "\n", encoding="utf-8")
    return {"candidate_commit": "a" * 40, "baseline": baseline, "current": current,
            "recorded_comparison": comparison, "approval_ledger": str(ledger),
            "ledger_revision": hashlib.sha256(ledger.read_bytes()).hexdigest()}


def waiver():
    return {"approved_by": "user", "approval_record": "user-approval-123",
            "candidate_commit": "a" * 40, "source_hash": "b" * 64,
            "environment_hash": "c" * 64, "command_hash": "d" * 64,
            "baseline_source_hash": "e" * 64,
            "failures": [{k: failure()[k] for k in ("suite", "test", "signature")} ]}


class BaselineWaiverTests(unittest.TestCase):
    def test_exact_user_waiver_marks_completion_waived_and_keeps_raw_failure(self):
        result = subject().validate_waiver(waiver(), candidate(self))
        self.assertEqual(result["status"], "completed_with_waived_baseline")
        self.assertEqual(result["failures"], [failure()])

    def test_candidate_environment_command_and_baseline_binding_expire_waiver(self):
        for field in ("candidate_commit", "source_hash", "environment_hash",
                      "command_hash", "baseline_source_hash"):
            changed = candidate(self)
            target = (changed if field == "candidate_commit" else
                      changed["baseline"] if field == "baseline_source_hash" else changed["current"])
            key = "source_hash" if field == "baseline_source_hash" else field
            target[key] = "f" * len(target[key])
            with self.subTest(field=field), self.assertRaises(ValueError):
                subject().validate_waiver(waiver(), changed)

    def test_broadened_stale_or_partial_failure_list_is_rejected(self):
        cases = []
        changed = candidate(self); changed["current"]["suites"][0]["failures"][0]["test"] = "package.Case.test_renamed"; cases.append(changed)
        changed = candidate(self); changed["current"]["suites"][0]["failures"][0]["signature"] = "new error"; cases.append(changed)
        changed = candidate(self); changed["current"]["suites"][0]["failures"].append({k: ({**failure(), "test": "package.Case.test_two"})[k] for k in ("test", "signature", "raw")}); cases.append(changed)
        for changed in cases:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                subject().validate_waiver(waiver(), changed)

    def test_worker_approval_and_wildcard_are_rejected(self):
        for changed in ({**waiver(), "approved_by": "operator"},
                        {**waiver(), "failures": [{"suite": "unit", "test": "*", "signature": "*"}]}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                subject().validate_waiver(changed, candidate(self))

    def test_new_or_ambiguous_failures_cannot_be_waived(self):
        for status in ("blocked", "unknown"):
            changed = candidate(self)
            changed["comparison_status"] = "baseline_only"
            changed["recorded_comparison"]["status"] = status
            with self.subTest(status=status), self.assertRaises(ValueError):
                subject().validate_waiver(waiver(), changed)

    def test_forged_worker_approval_and_fabricated_comparison_do_not_authorize_waiver(self):
        changed = candidate(self)
        changed["recorded_comparison"]["inherited"] = []
        changed["comparison_status"] = "baseline_only"
        changed["failures"] = [failure()]
        with self.assertRaises(ValueError):
            subject().validate_waiver(waiver(), changed)
        changed = candidate(self)
        ledger = pathlib.Path(changed["approval_ledger"])
        event = json.loads(ledger.read_text(encoding="utf-8"))
        event["actor"] = "operator"
        ledger.write_text(json.dumps(event) + "\n", encoding="utf-8")
        changed["ledger_revision"] = hashlib.sha256(ledger.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):
            subject().validate_waiver(waiver(), changed)

    def test_schema_declares_exact_waiver_shape(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["approved_by"]["const"], "user")
        self.assertFalse(schema["properties"]["failures"]["items"]["additionalProperties"])

    def test_cli_compare_emits_json_and_nonzero_for_regression(self):
        base = {"source_hash": "a" * 64, "environment_hash": "b" * 64,
                "command_hash": "c" * 64, "suites": [{"id": "unit", "tests": [failure()["test"]],
                                                       "failures": [], "raw_result": {"status": "completed", "exit_code": 0}}]}
        current = json.loads(json.dumps(base))
        current["source_hash"] = "d" * 64
        current["suites"][0]["failures"] = [{k: failure()[k] for k in ("test", "signature", "raw")}]
        current["suites"][0]["raw_result"] = {"status": "completed", "exit_code": 1}
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
                    "suites": [{"id": "unit", "tests": [failure()["test"]],
                                "failures": [{k: failure()[k] for k in ("test", "signature", "raw")}],
                                "raw_result": {"status": "completed", "exit_code": 1, "stderr": "raw runner output"}}]}
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
