import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import template_triage


def evidence(**overrides):
    value = {
        "owner_repo": "acme/catalog",
        "evidence_hash": "e1",
        "readme_text": "A complete README",
        "pubspec_text": "environment: {sdk: '>=3.0.0'}",
        "tree_text": "lib/main.dart",
        "constraints": {"sdk": "pass", "license": "pass"},
    }
    value.update(overrides)
    return value


def context(**overrides):
    value = {
        "score_report": {"verdict": "DEVELOPER_DECISION", "score": 60},
        "generic_category": "productivity",
        "specific_category": "inventory",
        "original_implementations": "lib/catalog.dart",
        "intended_use": "catalog app",
        "observed_decision": "developer_review",
    }
    value.update(overrides)
    return value


class CatalogTriageTests(unittest.TestCase):
    def test_protected_scoring_verdicts_do_not_call_jev(self):
        for verdict in ("AUTO_APPROVE", "AUTO_REJECT"):
            with patch.object(template_triage.jev_classify, "classify") as classify:
                result = template_triage.triage(evidence(), context(score_report={"verdict": verdict}), workspace=tempfile.mkdtemp())
            classify.assert_not_called()
            self.assertEqual(result["decision"], "existing_path")
            self.assertEqual(result["actor"], "baseline")

    def test_off_and_shadow_preserve_existing_path_and_keep_evidence(self):
        with tempfile.TemporaryDirectory() as workspace, tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as policy:
            json.dump({"site": "site1", "mode": "off"}, policy)
            policy.flush()
            with patch.object(template_triage.jev_classify, "classify") as classify:
                result = template_triage.triage(evidence(), context(), workspace=workspace, policy_path=policy.name)
            classify.assert_not_called()
            self.assertEqual(result["decision"], "existing_path")
            self.assertEqual(result["fallback_reason"], "policy_off")
            self.assertEqual(result["evidence_hash"], "e1")

    def test_active_high_confidence_adopt_is_shortlist_only(self):
        with tempfile.TemporaryDirectory() as workspace, tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as policy:
            json.dump({
                "site": "site1", "mode": "active", "threshold": 0.9,
                "model": "jev", "schema_hash": "schema", "evaluator": "eval", "calibration_report": {
                    "site": "site1", "model": "jev", "schema_hash": "schema", "threshold": 0.9, "evaluator": "eval"
                }
            }, policy)
            policy.flush()
            envelope = {"model": "jev", "schema_hash": "schema", "answers": {
                "triage": {"choice": "adopt", "confidence": 0.95}
            }}
            with patch.object(template_triage.jev_classify, "classify", return_value=(0, envelope)):
                result = template_triage.triage(evidence(), context(), workspace=workspace, policy_path=policy.name)
            self.assertEqual(result["decision"], "adopt")
            self.assertEqual(result["actor"], "jev")
            self.assertFalse(result["project_selected"])

    def test_active_decision_persists_triage_metadata_without_changing_score(self):
        with tempfile.TemporaryDirectory() as workspace:
            database = str(Path(workspace) / "catalog.sqlite3")
            conn = sqlite3.connect(database)
            with conn:
                conn.execute("CREATE TABLE templates (owner_repo TEXT PRIMARY KEY, score_verdict TEXT, triage_decision TEXT, triage_confidence REAL, triage_policy_version TEXT, triage_actor TEXT)")
                conn.execute("INSERT INTO templates(owner_repo, score_verdict) VALUES ('acme/catalog', 'DEVELOPER_DECISION')")
            conn.close()
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as policy:
                json.dump({"site": "site1", "mode": "active", "threshold": 0.9, "model": "jev", "schema_hash": "schema", "evaluator": "eval", "version": "p1", "calibration_report": {"site": "site1", "model": "jev", "schema_hash": "schema", "threshold": 0.9, "evaluator": "eval"}}, policy); policy.flush()
                envelope = {"model": "jev", "schema_hash": "schema", "answers": {"triage": {"choice": "reject", "confidence": .95}}}
                with patch.object(template_triage.jev_classify, "classify", return_value=(0, envelope)):
                    template_triage.triage(evidence(), context(catalog_path=database), workspace=workspace, policy_path=policy.name)
            conn = sqlite3.connect(database)
            with conn:
                row = conn.execute("SELECT score_verdict, triage_decision, triage_confidence, triage_policy_version, triage_actor FROM templates").fetchone()
            conn.close()
            self.assertEqual(row, ("DEVELOPER_DECISION", "reject", .95, "p1", "jev"))

    def test_missing_evidence_blocks_positive_triage(self):
        with patch.object(template_triage.jev_classify, "classify") as classify:
            result = template_triage.triage(evidence(readme_text=None), context(), workspace=tempfile.mkdtemp())
        classify.assert_not_called()
        self.assertEqual(result["decision"], "existing_path")
        self.assertEqual(result["fallback_reason"], "missing_required_evidence")

    def test_changed_evidence_invalidates_previous_triage(self):
        with tempfile.TemporaryDirectory() as workspace:
            first = template_triage.triage(evidence(), context(), workspace=workspace)
            second = template_triage.triage(evidence(evidence_hash="e2"), context(), workspace=workspace)
        self.assertEqual(first["evidence_hash"], "e1")
        self.assertEqual(second["fallback_reason"], "evidence_changed")
        self.assertNotEqual(first.get("triage_identity"), second.get("triage_identity"))

    def test_nested_failed_constraint_blocks_positive_triage(self):
        with patch.object(template_triage.jev_classify, "classify") as classify:
            result = template_triage.triage(evidence(constraints={"sdk": {"status": "failed"}}), context(), workspace=tempfile.mkdtemp())
        classify.assert_not_called()
        self.assertEqual(result["fallback_reason"], "failed_explicit_constraint")

    def test_shadow_keeps_proposal_and_observed_decision_separate(self):
        with tempfile.TemporaryDirectory() as workspace, patch.object(template_triage.jev_classify, "classify", return_value=(0, {
            "model": "jev", "schema_hash": "x", "answers": {"triage": {"choice": "reject", "confidence": .95}}
        })):
            result = template_triage.triage(evidence(), context(observed_decision="developer_review"), workspace=workspace)
        self.assertEqual(result["hypothetical_decision"], "reject")
        self.assertEqual(result["jev_proposed_decision"], "reject")
        self.assertEqual(result["observed_decision"], "developer_review")

    def test_provider_failure_is_unavailable_with_provenance(self):
        with tempfile.TemporaryDirectory() as workspace, patch.object(template_triage.jev_classify, "classify", return_value=(3, {
            "status": "unavailable", "error": "timeout", "usage": None, "model": None
        })):
            result = template_triage.triage(evidence(), context(), workspace=workspace)
        self.assertEqual(result["fallback_reason"], "provider_unavailable")
        self.assertEqual(result["inference_status"], "unavailable")
        self.assertEqual(result["provider_error"], "timeout")

    def test_provider_failure_audit_preserves_provenance_and_existing_triage(self):
        with tempfile.TemporaryDirectory() as workspace:
            template_triage.triage(evidence(), context(), workspace=workspace)
            with patch.object(template_triage.jev_classify, "classify", return_value=(3, {
                "status": "unavailable", "error": "timeout", "usage": {"input": 4}, "duration_ms": 123,
                "model": "jev"
            })):
                result = template_triage.triage(evidence(), context(), workspace=workspace)
            audit = json.loads((Path(workspace) / ".jev" / "site1-triage.json").read_text(encoding="utf-8"))["acme/catalog"]
        self.assertEqual(result["fallback_reason"], "provider_unavailable")
        self.assertEqual(audit["inference_status"], "unavailable")
        self.assertEqual(audit["provider_error"], "timeout")
        self.assertEqual(audit["usage"], {"input": 4})
        self.assertEqual(audit["duration_ms"], 123)

    def test_cli_invalid_json_returns_two(self):
        with tempfile.TemporaryDirectory() as workspace:
            bad = Path(workspace) / "bad.json"
            good = Path(workspace) / "good.json"
            bad.write_text("{", encoding="utf-8")
            good.write_text("{}", encoding="utf-8")
            self.assertEqual(template_triage.main([str(bad), str(good), "--workspace", workspace, "--output", str(Path(workspace) / "out.json")]), 2)

    def test_cli_valid_json_wrong_shape_returns_two(self):
        with tempfile.TemporaryDirectory() as workspace:
            evidence_file = Path(workspace) / "evidence.json"
            context_file = Path(workspace) / "context.json"
            evidence_file.write_text("[]", encoding="utf-8")
            context_file.write_text("[]", encoding="utf-8")
            self.assertEqual(template_triage.main([str(evidence_file), str(context_file), "--workspace", workspace, "--output", str(Path(workspace) / "out.json")]), 2)

    def test_workspace_catalog_is_updated_and_rejected_rows_are_not_default_shortlist(self):
        with tempfile.TemporaryDirectory() as workspace:
            database = Path(workspace) / "template-catalog.sqlite3"
            conn = sqlite3.connect(database)
            with conn:
                conn.execute("CREATE TABLE templates (owner_repo TEXT PRIMARY KEY, category TEXT, project TEXT, score_report TEXT, score_verdict TEXT, triage_decision TEXT, triage_confidence REAL, triage_policy_version TEXT, triage_actor TEXT, evidence_hash TEXT)")
                conn.execute("INSERT INTO templates(owner_repo, category, project, score_report, score_verdict) VALUES ('acme/catalog','inventory','p','{}','DEVELOPER_DECISION')")
            conn.close()
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as policy:
                json.dump({"site": "site1", "mode": "active", "threshold": .9, "model": "jev", "schema_hash": "schema", "evaluator": "eval", "version": "p1", "calibration_report": {"site": "site1", "model": "jev", "schema_hash": "schema", "threshold": .9, "evaluator": "eval"}}, policy); policy.flush()
                with patch.object(template_triage.jev_classify, "classify", return_value=(0, {"model": "jev", "schema_hash": "schema", "answers": {"triage": {"choice": "reject", "confidence": .95}}})):
                    template_triage.triage(evidence(), context(), workspace=workspace, policy_path=policy.name)
            conn = sqlite3.connect(database)
            row = conn.execute("SELECT triage_decision, triage_actor FROM templates").fetchone(); conn.close()
            self.assertEqual(row, ("reject", "jev"))

    def test_evidence_change_clears_catalog_triage_metadata(self):
        with tempfile.TemporaryDirectory() as workspace:
            database = Path(workspace) / "template-catalog.sqlite3"
            conn = sqlite3.connect(database)
            with conn:
                conn.execute("CREATE TABLE templates (owner_repo TEXT PRIMARY KEY, triage_decision TEXT, triage_confidence REAL, triage_policy_version TEXT, triage_actor TEXT, evidence_hash TEXT)")
                conn.execute("INSERT INTO templates VALUES ('acme/catalog','adopt',.95,'p1','jev','e1')")
            conn.close()
            template_triage.triage(evidence(evidence_hash="e2"), context(), workspace=workspace)
            conn = sqlite3.connect(database); row = conn.execute("SELECT triage_decision, triage_confidence, triage_policy_version, triage_actor FROM templates").fetchone(); conn.close()
            self.assertEqual(row, (None, None, None, None))


if __name__ == "__main__":
    unittest.main()
