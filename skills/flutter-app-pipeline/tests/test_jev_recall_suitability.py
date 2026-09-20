import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parent.parent / "two-model-sdd-pipeline" / "scripts"))

import recall_suitability
from template_recall import main as recall_main


def candidate(owner, *, package="flutter", readme="README", fetched_at="2026-09-20T12:00:00+00:00"):
    return {
        "owner_repo": owner,
        "category": "inventory",
        "project": owner.rsplit("/", 1)[-1],
        "score_verdict": "AUTO_APPROVE",
        "score_report": {"verdict": "AUTO_APPROVE", "total": 82},
        "evidence_hash": "evidence-" + owner.replace("/", "-"),
        "readme_text": readme,
        "pubspec_text": "name: sample",
        "tree_text": "lib/main.dart",
        "generic_category": "business",
        "specific_category": "inventory",
        "original_implementations": "lib/main.dart",
        "constraints": "{}",
        "package_names": json.dumps([package]),
        "fetched_at": fetched_at,
    }


def context(**overrides):
    value = {
        "category_skeleton": {
            "generic_category": "business",
            "specific_category": "inventory",
            "original_implementations": ["lib/main.dart"],
        },
        "intended_use": "an offline inventory app",
        "declared_dependencies": ["flutter", "http"],
    }
    value.update(overrides)
    return value


def envelope(choices, *, model="jev", schema_hash="schema"):
    return {
        "status": "answered",
        "model": model,
        "schema_hash": schema_hash,
        "usage": {"input_tokens": 10, "output_tokens": 10},
        "answers": {
            key: {
                "type": "choice",
                "choice": choice,
                "probabilities": {"suitable": 0.95 if choice == "suitable" else 0.02,
                                   "unsuitable": 0.95 if choice == "unsuitable" else 0.02,
                                   "needs_review": 0.95 if choice == "needs_review" else 0.02},
                "confidence": confidence,
            }
            for key, choice, confidence in choices
        },
    }


class RecallSuitabilityTests(unittest.TestCase):
    def _active_policy(self, workspace, schema_hash=None):
        policy = Path(workspace) / "site2-policy.json"
        policy.write_text(json.dumps({
            "site": "site2",
            "mode": "active",
            "model": "jev",
            "schema_hash": schema_hash or "schema",
            "threshold": 0.9,
            "evaluator": "test-evaluator",
            "calibration_report": {
                "site": "site2",
                "model": "jev",
                "schema_hash": schema_hash or "schema",
                "threshold": 0.9,
                "evaluator": "test-evaluator",
            },
        }), encoding="utf-8")
        return str(policy)

    def test_active_filters_only_confident_suitable_candidates(self):
        rows = [candidate("acme/good"), candidate("acme/bad"), candidate("acme/maybe")]
        with tempfile.TemporaryDirectory() as workspace:
            # Build the exact schema hash the policy must bind to.
            schema = recall_suitability.build_schema(rows, context(), model="jev")
            schema_hash = recall_suitability.schema_hash(schema)
            policy = self._active_policy(workspace, schema_hash)
            answers = [("candidate_0", "suitable", 0.96), ("candidate_1", "unsuitable", 0.98),
                       ("candidate_2", "needs_review", 0.91)]
            with patch.object(recall_suitability.jev_classify, "classify", return_value=(0, envelope(answers, schema_hash=schema_hash))) as classify:
                report = recall_suitability.assess(rows, context(), workspace=workspace, policy_path=policy)
            classify.assert_called_once()
        self.assertEqual(report["verdict"], "HIT")
        self.assertEqual([row["owner_repo"] for row in report["candidates"]], ["acme/good"])
        self.assertEqual(report["judgments"][1]["choice"], "unsuitable")
        self.assertFalse(report["judgments"][1]["selected"])
        self.assertEqual(report["judgments"][2]["status"], "answered")
        self.assertFalse(report["judgments"][2]["selected"])

    def test_all_unsuitable_is_miss_with_live_search_reason_and_no_deletion(self):
        rows = [candidate("acme/a"), candidate("acme/b")]
        with tempfile.TemporaryDirectory() as workspace:
            schema = recall_suitability.build_schema(rows, context(), model="jev")
            schema_hash = recall_suitability.schema_hash(schema)
            policy = self._active_policy(workspace, schema_hash)
            answers = [("candidate_0", "unsuitable", 0.99), ("candidate_1", "unsuitable", 0.98)]
            with patch.object(recall_suitability.jev_classify, "classify", return_value=(0, envelope(answers, schema_hash=schema_hash))):
                report = recall_suitability.assess(rows, context(), workspace=workspace, policy_path=policy)
        self.assertEqual(report["verdict"], "MISS")
        self.assertIn("live_search", report["fallback_reason"])
        self.assertEqual([item["owner_repo"] for item in report["deterministic_candidates"]], ["acme/a", "acme/b"])

    def test_shadow_and_off_preserve_deterministic_recall(self):
        rows = [candidate("acme/good")]
        for mode in ("shadow", "off"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as workspace:
                policy = Path(workspace) / "policy.json"
                policy.write_text(json.dumps({"site": "site2", "mode": mode}), encoding="utf-8")
                with patch.object(recall_suitability.jev_classify, "classify", return_value=(0, envelope([("candidate_0", "suitable", 0.95)]))) as classify:
                    report = recall_suitability.assess(rows, context(), workspace=workspace, policy_path=str(policy))
                if mode == "off":
                    classify.assert_not_called()
                else:
                    classify.assert_called_once()
                self.assertEqual(report["verdict"], "HIT")
                self.assertEqual(report["candidates"], rows)

    def test_provider_unavailability_preserves_rows_and_differs_from_answer_uncertainty(self):
        rows = [candidate("acme/good")]
        with tempfile.TemporaryDirectory() as workspace:
            unavailable = {"status": "unavailable", "error": "timeout", "model": None, "usage": None}
            with patch.object(recall_suitability.jev_classify, "classify", return_value=(3, unavailable)):
                report = recall_suitability.assess(rows, context(), workspace=workspace)
            self.assertEqual(report["verdict"], "HIT")
            self.assertEqual(report["fallback_reason"], "provider_unavailable")
            self.assertEqual(report["judgments"][0]["status"], "provider_unavailable")

            schema = recall_suitability.build_schema(rows, context(), model="jev")
            schema_hash = recall_suitability.schema_hash(schema)
            policy = self._active_policy(workspace, schema_hash)
            answer = envelope([("candidate_0", "suitable", 0.5)], schema_hash=schema_hash)
            with patch.object(recall_suitability.jev_classify, "classify", return_value=(1, answer)):
                uncertain = recall_suitability.assess(rows, context(), workspace=workspace, policy_path=policy)
        self.assertEqual(uncertain["judgments"][0]["status"], "uncertain")
        self.assertNotEqual(uncertain["fallback_reason"], "provider_unavailable")

    def test_active_model_mismatch_preserves_deterministic_recall_without_active_hit(self):
        rows = [candidate("acme/good")]
        with tempfile.TemporaryDirectory() as workspace:
            schema = recall_suitability.build_schema(rows, context(), model="jev")
            schema_hash = recall_suitability.schema_hash(schema)
            policy = self._active_policy(workspace, schema_hash)
            answers = [("candidate_0", "suitable", 0.99)]
            mismatched = envelope(answers, model="jev-other", schema_hash=schema_hash)
            with patch.object(recall_suitability.jev_classify, "classify", return_value=(0, mismatched)):
                report = recall_suitability.assess(rows, context(), workspace=workspace, policy_path=policy)

            advisory = list((Path(workspace) / ".jev" / "site2" / "advisory").glob("*.json"))
            self.assertEqual(len(advisory), 1)
            advisory_record = json.loads(advisory[0].read_text(encoding="utf-8"))

        self.assertEqual(report["verdict"], "HIT")
        self.assertEqual(report["candidates"], rows)
        self.assertEqual(report["actual_action"], "deterministic_recall")
        self.assertEqual(report["fallback_reason"], "provider_config_mismatch")
        self.assertEqual(report["inference_status"], "config_mismatch")
        self.assertFalse(report["judgments"][0]["selected"])
        self.assertEqual(report["judgments"][0]["status"], "provider_config_mismatch")
        self.assertEqual(advisory_record["fallback"], "provider_config_mismatch")

    def test_active_schema_mismatch_preserves_deterministic_recall_without_active_hit(self):
        rows = [candidate("acme/good")]
        with tempfile.TemporaryDirectory() as workspace:
            schema = recall_suitability.build_schema(rows, context(), model="jev")
            schema_hash = recall_suitability.schema_hash(schema)
            policy = self._active_policy(workspace, schema_hash)
            answers = [("candidate_0", "suitable", 0.99)]
            mismatched = envelope(answers, schema_hash="different-schema")
            with patch.object(recall_suitability.jev_classify, "classify", return_value=(0, mismatched)):
                report = recall_suitability.assess(rows, context(), workspace=workspace, policy_path=policy)

        self.assertEqual(report["verdict"], "HIT")
        self.assertEqual(report["candidates"], rows)
        self.assertEqual(report["actual_action"], "deterministic_recall")
        self.assertEqual(report["fallback_reason"], "provider_config_mismatch")
        self.assertEqual(report["inference_status"], "config_mismatch")
        self.assertFalse(report["judgments"][0]["selected"])
        self.assertEqual(report["judgments"][0]["status"], "provider_config_mismatch")

    def test_classifier_invalid_input_exit_two_preserves_deterministic_recall_and_finishes(self):
        rows = [candidate("acme/good")]
        with tempfile.TemporaryDirectory() as workspace:
            schema = recall_suitability.build_schema(rows, context(), model="jev")
            schema_hash = recall_suitability.schema_hash(schema)
            policy = self._active_policy(workspace, schema_hash)
            invalid = {
                "status": "unavailable",
                "answers": {},
                "model": None,
                "usage": None,
                "schema_hash": None,
                "error": "threshold must be finite in [0, 1]",
            }
            with patch.object(recall_suitability.jev_classify, "classify", return_value=(2, invalid)):
                report = recall_suitability.assess(rows, context(), workspace=workspace, policy_path=policy)

            advisory = list((Path(workspace) / ".jev" / "site2" / "advisory").glob("*.json"))

        self.assertEqual(report["verdict"], "HIT")
        self.assertEqual(report["candidates"], rows)
        self.assertEqual(report["actual_action"], "deterministic_recall")
        self.assertEqual(report["fallback_reason"], "classifier_setup_error")
        self.assertEqual(report["inference_status"], "setup_error")
        self.assertEqual(report["provider_error"], invalid["error"])
        self.assertEqual(report["judgments"][0]["status"], "classifier_setup_error")
        self.assertEqual(len(advisory), 1)

    def test_template_recall_maps_deterministic_setup_error_to_exit_one(self):
        with tempfile.TemporaryDirectory() as workspace:
            context_file = Path(workspace) / "context.json"
            context_file.write_text(json.dumps(context()), encoding="utf-8")
            database = Path(workspace) / "catalog.sqlite3"
            from template_catalog import _connect
            conn = _connect(str(database))
            conn.close()
            output_file = Path(workspace) / "suitability.json"

            code = recall_main([
                "inventory", "--database", str(database), "--workspace", workspace,
                "--suitability-context", str(context_file), "--suitability-output", str(output_file),
                "--model", "", "--query-vector", "[1.0]",
            ])
            report = json.loads(output_file.read_text(encoding="utf-8"))

        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "SETUP_ERROR")
        self.assertEqual(report["verdict"], "SETUP_ERROR")

    def test_open_provider_circuit_preserves_deterministic_recall_in_active_mode(self):
        rows = [candidate("acme/good")]
        with tempfile.TemporaryDirectory() as workspace:
            schema = recall_suitability.build_schema(rows, context(), model="jev")
            schema_hash = recall_suitability.schema_hash(schema)
            policy = self._active_policy(workspace, schema_hash)
            with patch.object(recall_suitability.jev_classify, "classify", return_value=(1, {
                "status": "circuit_open",
                "error": "circuit is open",
                "model": None,
                "schema_hash": schema_hash,
                "usage": None,
                "answers": {},
            })) as classify:
                report = recall_suitability.assess(rows, context(), workspace=workspace, policy_path=policy)
        classify.assert_called_once()
        self.assertEqual(report["verdict"], "HIT")
        self.assertEqual(report["candidates"], rows)
        self.assertEqual(report["fallback_reason"], "provider_unavailable")
        self.assertEqual(report["judgments"][0]["status"], "provider_unavailable")

    def test_oversized_state_and_question_count_are_unevaluated_without_provider_call(self):
        rows = [candidate("acme/{}".format(index), readme="x" * 4000) for index in range(33)]
        with tempfile.TemporaryDirectory() as workspace:
            with patch.object(recall_suitability.jev_classify, "classify") as classify:
                report = recall_suitability.assess(rows, context(), workspace=workspace)
            classify.assert_not_called()
        self.assertEqual(report["verdict"], "HIT")
        self.assertIn(report["fallback_reason"], {"question_budget_exceeded", "payload_budget_exceeded"})
        self.assertTrue(all(item["status"] == "unevaluated" for item in report["judgments"]))

    def test_zero_eligible_candidates_is_miss_without_provider_call(self):
        with tempfile.TemporaryDirectory() as workspace:
            with patch.object(recall_suitability.jev_classify, "classify") as classify:
                report = recall_suitability.assess([], context(), workspace=workspace)
            classify.assert_not_called()
        self.assertEqual(report["verdict"], "MISS")
        self.assertEqual(report["fallback_reason"], "zero_eligible_candidates")

    def test_cli_writes_report_and_uses_exit_contract(self):
        with tempfile.TemporaryDirectory() as workspace:
            candidates_file = Path(workspace) / "candidates.json"
            context_file = Path(workspace) / "context.json"
            output_file = Path(workspace) / "report.json"
            candidates_file.write_text(json.dumps([candidate("acme/good")]), encoding="utf-8")
            context_file.write_text(json.dumps(context()), encoding="utf-8")
            with patch.object(recall_suitability, "assess", return_value={"verdict": "MISS", "candidates": [], "judgments": []}):
                code = recall_suitability.main([str(candidates_file), str(context_file), "--workspace", workspace, "--output", str(output_file)])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output_file.read_text(encoding="utf-8"))["verdict"], "MISS")

    def test_template_recall_can_run_live_search_after_suitability_miss(self):
        with tempfile.TemporaryDirectory() as workspace:
            context_file = Path(workspace) / "context.json"
            context_file.write_text(json.dumps(context(specific_query="inventory app", generic_query="business app")), encoding="utf-8")
            database = Path(workspace) / "catalog.sqlite3"
            # A real empty catalog exercises deterministic MISS and the wiring.
            from template_catalog import _connect
            conn = _connect(str(database))
            conn.close()
            report_file = Path(workspace) / "suitability.json"
            with patch("template_recall._run_live_search", return_value={"exit_code": 1, "stdout": "", "stderr": ""}) as live:
                code = recall_main(["inventory", "--database", str(database), "--workspace", workspace,
                                    "--suitability-context", str(context_file), "--suitability-output", str(report_file)])
            live.assert_called_once_with("inventory app", "business app", workspace)
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
