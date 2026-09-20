import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
SCHEMAS = pathlib.Path(__file__).resolve().parent.parent / "schemas"
sys.path.insert(0, str(SCRIPTS))

import director_prompt


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def active_policy():
    schema = json.loads((SCHEMAS / "jev-site-3.json").read_text(encoding="utf-8"))
    schema_hash = hashlib.sha256(canonical(schema).encode("utf-8")).hexdigest()
    return {
        "site": "site3",
        "mode": "active",
        "model": schema["model"],
        "schema_hash": schema_hash,
        "threshold": 0.9,
        "evaluator": "test-evaluator",
        "calibration_report": {
            "site": "site3",
            "model": schema["model"],
            "schema_hash": schema_hash,
            "threshold": 0.9,
            "evaluator": "test-evaluator",
        },
    }


def answer(choice, confidence=0.95):
    choices = {
        "local_mechanical_correction": 0.95,
        "architectural_disagreement": 0.03,
        "test_noise_or_unclear": 0.02,
    }
    choices[choice] = 0.95
    remaining = [name for name in choices if name != choice]
    choices[remaining[0]] = 0.03
    choices[remaining[1]] = 0.02
    return {
        "status": "answered",
        "model": "jev",
        "schema_hash": active_policy()["schema_hash"],
        "usage": {"input_tokens": 12, "output_tokens": 4},
        "cache_hit": False,
        "answers": {
            "director_classification": {
                "type": "choice",
                "choice": choice,
                "probabilities": choices,
                "confidence": confidence,
            }
        },
    }


class DirectorSelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jev director ")
        self.workspace = pathlib.Path(self.tmp.name)
        self.plan = self.workspace / "plan.json"
        self.baseline = self.workspace / "baseline.md"
        self.output = self.workspace / "selected.md"
        self.plan.write_text(json.dumps({
            "feature": "director selection",
            "tasks": [{
                "id": 7,
                "title": "Keep director dispatch",
                "summary": "Preserve the complete correction context.",
                "spec_refs": ["docs/spec.md#site-3"],
                "touches": ["scripts/task-run"],
                "acceptance": ["the director remains authoritative"],
            }],
        }), encoding="utf-8")
        self.baseline.write_text(
            "Mode: CORRECTIVE. Target task: 7\n"
            "Plan: plan.json\n"
            "Findings: task-7-review.json\n"
            "Target task: {structured task}\n"
            "Append ONE corrective task and reply with its id.\n",
            encoding="utf-8",
        )
        (self.workspace / "task-7-review.json").write_text(json.dumps({
            "verdict": "SEND_BACK",
            "findings": [{
                "severity": "Important",
                "file": "scripts/task-run",
                "line": 42,
                "issue": "tighten the boundary",
                "fix": "keep the director dispatch authoritative",
            }],
            "minors": [],
            "summary": "The correction remains within the task scope.",
        }), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_prepare(self, mode, policy):
        policy_path = self.workspace / "policy.json"
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        return director_prompt.prepare(
            mode=mode,
            workspace=str(self.workspace),
            task_id=7,
            plan_path=str(self.plan),
            baseline_path=str(self.baseline),
            output_path=str(self.output),
            policy_path=str(policy_path),
        )

    def test_active_confident_local_correction_adds_only_focused_hint(self):
        seen = {}

        def classify(schema, state, **kwargs):
            seen["schema"] = schema
            seen["state"] = state
            seen["kwargs"] = kwargs
            return 0, answer("local_mechanical_correction")

        with mock.patch.object(director_prompt.jev_classify, "classify", side_effect=classify):
            result = self.run_prepare("CORRECTIVE", active_policy())

        self.assertEqual(result["choice"], "local_mechanical_correction")
        self.assertEqual(result["actual_action"], "focused")
        prompt = self.output.read_text(encoding="utf-8")
        self.assertIn("Append ONE corrective task", prompt)
        self.assertIn("local mechanical correction", prompt)
        self.assertEqual(seen["state"]["target_task"]["id"], 7)
        self.assertEqual(seen["state"]["findings"]["verdict"], "SEND_BACK")
        self.assertEqual(seen["state"]["cited_constraints"]["spec_refs"], ["docs/spec.md#site-3"])
        self.assertEqual(seen["state"]["episode"]["mode"], "CORRECTIVE")

    def test_active_uncertain_or_nonlocal_corrective_keeps_exact_baseline(self):
        for choice, confidence in (
            ("architectural_disagreement", 0.95),
            ("local_mechanical_correction", 0.89),
        ):
            with self.subTest(choice=choice, confidence=confidence):
                self.output.unlink(missing_ok=True)
                with mock.patch.object(
                    director_prompt.jev_classify,
                    "classify",
                    return_value=(0, answer(choice, confidence)),
                ):
                    result = self.run_prepare("CORRECTIVE", active_policy())
                self.assertEqual(result["actual_action"], "baseline")
                self.assertEqual(self.output.read_text(encoding="utf-8"), self.baseline.read_text(encoding="utf-8"))

    def test_arbitrate_retains_baseline_context_and_may_add_hint(self):
        with mock.patch.object(
            director_prompt.jev_classify,
            "classify",
            return_value=(0, answer("architectural_disagreement")),
        ):
            result = self.run_prepare("ARBITRATE", active_policy())
        prompt = self.output.read_text(encoding="utf-8")
        self.assertEqual(result["actual_action"], "focused_hint")
        for required in ("Mode: CORRECTIVE", "Plan:", "Findings:", "Target task:", "Append ONE corrective task"):
            self.assertIn(required, prompt)
        self.assertIn("architectural disagreement", prompt.replace("_", " "))
        self.assertIn("full viability context", prompt)

    def test_off_and_shadow_always_dispatch_exact_baseline_and_record_hypothesis(self):
        for mode in ("off", "shadow"):
            with self.subTest(mode=mode):
                self.output.unlink(missing_ok=True)
                policy = {"site": "site3", "mode": mode, "threshold": 0.9}
                with mock.patch.object(
                    director_prompt.jev_classify,
                    "classify",
                    return_value=(0, answer("local_mechanical_correction")),
                ) as classify:
                    result = self.run_prepare("CORRECTIVE", policy)
                self.assertEqual(self.output.read_text(encoding="utf-8"), self.baseline.read_text(encoding="utf-8"))
                self.assertEqual(result["actual_action"], "baseline")
                if mode == "off":
                    classify.assert_not_called()
                records = [
                    json.loads(path.read_text(encoding="utf-8"))
                    for path in (self.workspace / ".jev" / "site3" / "advisory").glob("*.json")
                ]
                self.assertTrue(records)
                matching_records = [
                    record
                    for record in records
                    if (
                        record.get("policy_identity") == result["policy_identity"]
                        and record.get("episode", {}).get("mode") == result["episode"]["mode"]
                    )
                ]
                self.assertEqual(len(matching_records), 1)
                record = matching_records[0]
                self.assertEqual(record["actual_action"], "baseline")
                if mode == "off":
                    self.assertIsNone(record["decision"])
                    self.assertEqual(record["fallback"], "policy_off")
                else:
                    self.assertEqual(record["decision"], "local_mechanical_correction")

    def test_provider_failure_falls_back_without_ledger_write(self):
        with mock.patch.object(
            director_prompt.jev_classify,
            "classify",
            return_value=(3, {"status": "unavailable", "error": "offline", "answers": {}}),
        ):
            result = self.run_prepare("ARBITRATE", active_policy())
        self.assertEqual(result["actual_action"], "baseline")
        self.assertEqual(self.output.read_text(encoding="utf-8"), self.baseline.read_text(encoding="utf-8"))
        self.assertFalse((self.workspace / "ledger.jsonl").exists())

    def test_classifier_statuses_have_distinct_fallback_telemetry(self):
        cases = (
            (1, {"status": "circuit_open", "error": "open", "answers": {}}, "circuit_open", "circuit_open"),
            (3, {"status": "unavailable", "error": "offline", "answers": {}}, "provider_unavailable", "unavailable"),
            (2, {"status": "unavailable", "error": "bad schema", "answers": {}}, "classifier_setup_error", "setup_error"),
            (3, {"status": "cache_unavailable", "error": "cache unreadable", "answers": {}}, "cache_unavailable", "cache_unavailable"),
        )
        for code, envelope, fallback, inference_status in cases:
            with self.subTest(code=code, status=envelope["status"]):
                self.output.unlink(missing_ok=True)
                with mock.patch.object(
                    director_prompt.jev_classify,
                    "classify",
                    return_value=(code, envelope),
                ):
                    result = self.run_prepare("CORRECTIVE", active_policy())
                self.assertEqual(result["actual_action"], "baseline")
                self.assertEqual(result["fallback_reason"], fallback)
                self.assertEqual(result["inference_status"], inference_status)
                self.assertEqual(self.output.read_text(encoding="utf-8"), self.baseline.read_text(encoding="utf-8"))

    def test_all_choices_and_threshold_edge_only_local_corrective_focuses(self):
        for choice in director_prompt.CHOICES:
            with self.subTest(choice=choice):
                self.output.unlink(missing_ok=True)
                with mock.patch.object(
                    director_prompt.jev_classify,
                    "classify",
                    return_value=(0, answer(choice, 0.9)),
                ):
                    result = self.run_prepare("CORRECTIVE", active_policy())
                expected = "focused" if choice == "local_mechanical_correction" else "baseline"
                self.assertEqual(result["actual_action"], expected)
                if expected == "baseline":
                    self.assertEqual(self.output.read_text(encoding="utf-8"), self.baseline.read_text(encoding="utf-8"))

    def test_malformed_review_findings_cannot_enable_focused_corrective(self):
        self.output.unlink(missing_ok=True)
        (self.workspace / "task-7-review.json").write_text(json.dumps({
            "verdict": "SEND_BACK",
            "findings": [{"severity": "Important", "issue": "missing required evidence"}],
        }), encoding="utf-8")
        with mock.patch.object(
            director_prompt.jev_classify,
            "classify",
            return_value=(0, answer("local_mechanical_correction")),
        ) as classify:
            result = self.run_prepare("CORRECTIVE", active_policy())
        self.assertEqual(result["actual_action"], "baseline")
        self.assertEqual(result["fallback_reason"], "invalid_findings")
        classify.assert_not_called()
        self.assertEqual(self.output.read_text(encoding="utf-8"), self.baseline.read_text(encoding="utf-8"))

    def test_advisory_identity_binds_schema_policy_and_episode(self):
        with mock.patch.object(
            director_prompt.jev_classify,
            "classify",
            return_value=(0, answer("local_mechanical_correction")),
        ):
            first = self.run_prepare("CORRECTIVE", active_policy())
        policy = active_policy()
        policy["evaluator"] = "different-evaluator"
        policy["calibration_report"]["evaluator"] = "different-evaluator"
        with mock.patch.object(
            director_prompt.jev_classify,
            "classify",
            return_value=(0, answer("local_mechanical_correction")),
        ):
            second = self.run_prepare("ARBITRATE", policy)
        self.assertEqual(first["schema_identity"], second["schema_identity"])
        self.assertNotEqual(first["policy_identity"], second["policy_identity"])
        self.assertNotEqual(first["state_identity"], second["state_identity"])
        self.assertNotEqual(first["episode"]["mode"], second["episode"]["mode"])

    def test_arbitrate_classifier_receives_complete_structured_context(self):
        seen = {}

        def classify(schema, state, **kwargs):
            seen["schema"] = schema
            seen["state"] = state
            return 0, answer("test_noise_or_unclear")

        with mock.patch.object(director_prompt.jev_classify, "classify", side_effect=classify):
            result = self.run_prepare("ARBITRATE", active_policy())
        self.assertEqual(result["actual_action"], "focused_hint")
        state = seen["state"]
        self.assertEqual(state["target_task"]["id"], 7)
        self.assertEqual(state["plan"]["tasks"][0]["id"], 7)
        self.assertEqual(state["findings"]["verdict"], "SEND_BACK")
        self.assertEqual(state["actual_findings_or_escalation"]["review"]["verdict"], "SEND_BACK")
        self.assertEqual(state["cited_constraints"]["spec_refs"], ["docs/spec.md#site-3"])
        self.assertEqual(state["episode"]["mode"], "ARBITRATE")

    def test_cli_rejects_invalid_mode_and_missing_baseline(self):
        invalid = director_prompt.main([
            "--mode", "REVIEW", "--workspace", str(self.workspace), "--task", "7",
            "--plan", str(self.plan), "--baseline", str(self.baseline), "--output", str(self.output),
        ])
        self.assertEqual(invalid, 2)
        missing = director_prompt.main([
            "--mode", "CORRECTIVE", "--workspace", str(self.workspace), "--task", "7",
            "--plan", str(self.plan), "--baseline", str(self.workspace / "missing.md"),
            "--output", str(self.output),
        ])
        self.assertEqual(missing, 1)


if __name__ == "__main__":
    unittest.main()
