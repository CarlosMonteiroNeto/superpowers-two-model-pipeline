import os
import sqlite3
import sys
import tempfile
import unittest
import json
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from template_catalog import _connect, list_templates, upsert_template


class TestCatalogMigrationAndEvidence(unittest.TestCase):
    def test_migration_preserves_legacy_rows_and_invalidates_derived_data_only_when_evidence_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "catalog.sqlite3")
            legacy = sqlite3.connect(path)
            legacy.execute("CREATE TABLE templates (owner_repo TEXT PRIMARY KEY, category TEXT, project TEXT, score_report TEXT)")
            legacy.execute("INSERT INTO templates VALUES (?, ?, ?, ?)", ("acme/legacy", "generic", "shop", '{"verdict":"AUTO_APPROVE"}'))
            legacy.commit()
            legacy.close()

            conn = _connect(path)
            legacy_row = list_templates(conn)[0]
            self.assertEqual(legacy_row["owner_repo"], "acme/legacy")
            self.assertEqual(legacy_row["score_verdict"], "AUTO_APPROVE")
            self.assertIsNone(legacy_row["triage_decision"])

            score = {"template": "acme/modern", "verdict": "DEVELOPER_DECISION", "total": 58.0}
            evidence = {"evidence_hash": "evidence-v1", "readme_text": "Olá", "pubspec_text": None, "tree_text": "lib/main.dart", "constraints": {"license": {"status": "unknown", "value": None}}}
            upsert_template(conn, "acme/modern", "generic", "specific", score, evidence)
            conn.execute("UPDATE templates SET triage_decision='adopt', triage_confidence=0.95, vector_identity='model:evidence-v1', adoption_history='[\"developer\"]' WHERE owner_repo='acme/modern'")
            conn.commit()

            upsert_template(conn, "acme/modern", "generic", "specific", score, evidence)
            unchanged = [row for row in list_templates(conn) if row["owner_repo"] == "acme/modern"][0]
            self.assertEqual(unchanged["triage_decision"], "adopt")
            self.assertEqual(unchanged["vector_identity"], "model:evidence-v1")

            changed = dict(evidence, evidence_hash="evidence-v2", readme_text="Olá mundo")
            upsert_template(conn, "acme/modern", "generic", "specific", score, changed)
            refreshed = [row for row in list_templates(conn) if row["owner_repo"] == "acme/modern"][0]
            self.assertEqual(refreshed["score_verdict"], "DEVELOPER_DECISION")
            self.assertIsNone(refreshed["triage_decision"])
            self.assertIsNone(refreshed["vector_identity"])
            self.assertEqual(refreshed["adoption_history"], '["developer"]')
            self.assertEqual(refreshed["generic_category"], "generic")
            self.assertEqual(refreshed["specific_category"], "generic")
            self.assertEqual(refreshed["original_implementations"], "specific")
            conn.close()

    def test_upsert_rolls_back_when_a_write_fails(self):
        conn = _connect(":memory:")
        score = {"template": "acme/shop", "verdict": "AUTO_APPROVE"}
        upsert_template(conn, "acme/shop", "generic", "specific", score, {"evidence_hash": "one"})
        before = list_templates(conn)
        with self.assertRaises(ValueError):
            upsert_template(conn, "invalid", "generic", "specific", score, {"evidence_hash": "two"})
        self.assertEqual(list_templates(conn), before)

    def test_cli_exit_contract_and_unknown_outcome(self):
        root = os.path.join(os.path.dirname(__file__), "..", "scripts")
        wrapper = os.path.join(root, "template_catalog.py")
        with tempfile.TemporaryDirectory() as directory:
            db = os.path.join(directory, "catalog.sqlite3")
            score = os.path.join(directory, "score.json")
            with open(score, "w", encoding="utf-8") as handle:
                json.dump({"template": "acme/shop", "verdict": "AUTO_APPROVE"}, handle)
            def run(*args):
                return subprocess.run([sys.executable, wrapper, "--database", db, *args], capture_output=True, text=True)
            self.assertEqual(run("add", "acme/shop", "generic", "specific", score).returncode, 0)
            self.assertEqual(run("add", "acme/shop", "generic", "specific", score).returncode, 0)
            self.assertEqual(run("outcome", "missing/shop", "adopt").returncode, 1)
            self.assertEqual(run("outcome", "acme/shop", "adopt").returncode, 0)
            self.assertEqual(run("list").returncode, 0)
            self.assertEqual(run().returncode, 2)
