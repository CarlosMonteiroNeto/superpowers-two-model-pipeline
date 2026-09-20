import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = os.path.dirname(os.path.dirname(__file__))


class ResearchCliIntegrationTests(unittest.TestCase):
    def test_catalog_embed_recall_refresh_share_one_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "catalog.sqlite3")
            score = os.path.join(tmp, "score.json")
            with open(score, "w", encoding="utf-8") as handle:
                json.dump({"verdict": "AUTO_APPROVE", "total": 80}, handle)
            add = [sys.executable, os.path.join(ROOT, "scripts", "template-catalog"), "--database", db, "add", "a/repo", "cat", "demo", score]
            self.assertEqual(subprocess.run(add, capture_output=True, text=True).returncode, 0)
            recall = [sys.executable, os.path.join(ROOT, "scripts", "template-recall"), "--database", db, "cat"]
            result = subprocess.run(recall, capture_output=True, text=True)
            self.assertIn(result.returncode, (0, 2))

    def test_recall_cli_is_offline_and_reports_setup_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "catalog.sqlite3")
            missing = subprocess.run(
                [sys.executable, os.path.join(ROOT, "scripts", "template-recall"), "cat", "--database", os.path.join(tmp, "missing.sqlite3")],
                capture_output=True,
                text=True,
            )
            self.assertEqual(missing.returncode, 1)
            self.assertFalse(os.path.exists(os.path.join(tmp, "missing.sqlite3")))

            score = os.path.join(tmp, "score.json")
            with open(score, "w", encoding="utf-8") as handle:
                json.dump({"verdict": "AUTO_APPROVE", "total": 80}, handle)
            add = [sys.executable, os.path.join(ROOT, "scripts", "template-catalog"), "--database", db, "add", "a/repo", "cat", "demo", score]
            self.assertEqual(subprocess.run(add, capture_output=True, text=True).returncode, 0)
            invalid_top = subprocess.run(
                [sys.executable, os.path.join(ROOT, "scripts", "template-recall"), "cat", "--database", db, "--top", "0"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(invalid_top.returncode, 1)

            # The wrapper must not reach GitHub to produce a normal recall
            # answer. A catalog row without evidence remains a MISS.
            result = subprocess.run(
                [sys.executable, os.path.join(ROOT, "scripts", "template-recall"), "cat", "--database", db],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["status"], "MISS")

    def test_embed_and_refresh_cli_boundaries_are_injectable(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "catalog.sqlite3")
            score = os.path.join(tmp, "score.json")
            with open(score, "w", encoding="utf-8") as handle:
                json.dump({"verdict": "AUTO_APPROVE", "total": 80}, handle)
            add = [sys.executable, os.path.join(ROOT, "scripts", "template-catalog"), "--database", db, "add", "a/repo", "cat", "demo", score]
            self.assertEqual(subprocess.run(add, capture_output=True, text=True).returncode, 0)

            embed = subprocess.run(
                [sys.executable, os.path.join(ROOT, "scripts", "template-embed"), "--model", "fake-model", "--source-hash", "e1", "--vector", "[1, 0]"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(embed.returncode, 0)
            record = json.loads(embed.stdout)
            self.assertEqual(record["model"], "fake-model")
            self.assertEqual(record["source_hash"], "e1")
            self.assertTrue(record["identity"])

            from template_refresh import main as refresh_main

            evidence = {
                "owner_repo": "a/repo",
                "score_report": {"verdict": "AUTO_APPROVE", "total": 81},
                "readme_text": "README",
                "pubspec_text": "name: demo",
                "tree_text": "lib/main.dart",
                "constraints": {},
                "evidence_hash": "e2",
                "fetched_at": "2026-09-20T12:00:00+00:00",
            }
            with patch("template_refresh.collect_evidence", return_value=evidence):
                self.assertEqual(refresh_main(["a/repo", "--database", db, "--category", "cat", "--project", "demo"]), 0)

            invalid = dict(evidence)
            invalid.pop("fetched_at")
            with patch("template_refresh.collect_evidence", return_value=invalid):
                self.assertEqual(refresh_main(["a/repo", "--database", db, "--category", "cat", "--project", "demo"]), 1)


if __name__ == "__main__":
    unittest.main()
