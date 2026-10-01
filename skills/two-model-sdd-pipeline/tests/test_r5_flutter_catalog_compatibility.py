"""The Flutter catalog stays compatible while writing generic asset records."""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from contextlib import closing


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
FLUTTER_SCRIPTS = os.path.join(ROOT, "skills", "flutter-app-pipeline", "scripts")
sys.path.insert(0, FLUTTER_SCRIPTS)

from template_catalog import _connect, list_templates, main, upsert_template
from template_recall import recall
import asset_catalog


class FlutterCatalogCompatibilityTests(unittest.TestCase):
    def _put(self, conn, owner, sdk, evidence_hash, license_name="mit"):
        fetched = datetime.now(timezone.utc).isoformat()
        upsert_template(
            conn, owner, "commerce", "checkout", {"verdict": "AUTO_APPROVE", "total": 90},
            {"evidence_hash": evidence_hash, "fetched_at": fetched,
             "constraints": {"license": {"status": "known", "value": license_name},
                             "sdk": {"status": "known", "value": sdk}}},
        )

    def test_identity_update_recalls_current_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            with closing(_connect(os.path.join(directory, "catalog.sqlite3"))) as conn:
                self._put(conn, "acme/app", ">=3.0", "evidence-v1")
                old_id = conn.execute("SELECT asset_id FROM templates WHERE owner_repo='acme/app'").fetchone()[0]
                asset_catalog.record_outcome_connection(conn, {"asset_id": old_id, "outcome": "used_successfully", "actor": "test", "provenance": {}})
                self._put(conn, "acme/app", ">=3.2", "evidence-v2")
                current_id = conn.execute("SELECT asset_id FROM templates WHERE owner_repo='acme/app'").fetchone()[0]
                status, rows = recall(conn, "commerce")
                self.assertEqual("HIT", status)
                self.assertEqual([current_id], [row["asset_id"] for row in rows])
                self.assertEqual(2, conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0])
                old = conn.execute("SELECT outcome FROM adoption_outcomes WHERE asset_id=?", (old_id,)).fetchall()
                self.assertEqual("used_successfully", old[0][0])

    def test_license_update_and_multiple_owners_obey_current_binding_and_top_n(self):
        with tempfile.TemporaryDirectory() as directory:
            with closing(_connect(os.path.join(directory, "catalog.sqlite3"))) as conn:
                self._put(conn, "acme/z", ">=3.0", "z1")
                self._put(conn, "acme/a", ">=3.0", "a1")
                self._put(conn, "acme/a", ">=3.0", "a2", "bsd-3-clause")
                status, rows = recall(conn, "commerce", top_n=1)
                self.assertEqual("HIT", status)
                self.assertEqual(["acme/a"], [row["owner_repo"] for row in rows])
                self.assertEqual(3, conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0])

    def test_broken_current_binding_is_a_setup_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with closing(_connect(os.path.join(directory, "catalog.sqlite3"))) as conn:
                self._put(conn, "acme/app", ">=3.2", "evidence-v2")
                conn.execute("DELETE FROM assets WHERE asset_id=(SELECT asset_id FROM templates WHERE owner_repo='acme/app')")
                self.assertEqual(("SETUP_ERROR", []), recall(conn, "commerce"))

    def test_current_binding_survives_reopen_and_schema_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "catalog.sqlite3")
            conn = _connect(database)
            self._put(conn, "acme/app", ">=3.0", "evidence-v1")
            old_id = conn.execute("SELECT asset_id FROM templates").fetchone()[0]
            asset_catalog.record_outcome_connection(conn, {"asset_id": old_id, "outcome": "used_successfully", "actor": "test", "provenance": {}})
            self._put(conn, "acme/app", ">=3.2", "evidence-v2")
            current_id = conn.execute("SELECT asset_id FROM templates").fetchone()[0]
            conn.close()
            with closing(_connect(database)) as reopened:
                status, rows = recall(reopened, "commerce")
                self.assertEqual("HIT", status)
                self.assertEqual([current_id], [row["asset_id"] for row in rows])
                self.assertEqual(2, reopened.execute("SELECT COUNT(*) FROM assets").fetchone()[0])
                self.assertEqual("used_successfully", reopened.execute("SELECT outcome FROM adoption_outcomes WHERE asset_id=?", (old_id,)).fetchone()[0])

    def test_flutter_upsert_writes_generic_identity_and_keeps_legacy_row(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "catalog.sqlite3")
            with closing(_connect(database)) as conn:
                upsert_template(
                    conn,
                    "acme/shop",
                    "commerce",
                    "checkout",
                    {"verdict": "DEVELOPER_DECISION", "total": 58},
                    {
                        "evidence_hash": "flutter-evidence-v1",
                        "fetched_at": "2026-09-30T12:00:00+00:00",
                        "constraints": {"license": {"status": "known", "value": "mit"}, "sdk": {"status": "known", "value": ">=3.0"}},
                    },
                )
                generic_table = conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='assets'"
                ).fetchone()[0]
                self.assertEqual(1, generic_table)
                self.assertEqual("acme/shop", list_templates(conn)[0]["owner_repo"])
                asset = conn.execute("SELECT ecosystem, name, evidence_hash FROM assets").fetchone()
                self.assertEqual(("flutter", "acme/shop", "flutter-evidence-v1"), tuple(asset))
                self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0])

    def test_legacy_cli_exit_codes_are_preserved_and_outcomes_are_recorded_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "catalog.sqlite3")
            score = os.path.join(directory, "score.json")
            with open(score, "w", encoding="utf-8") as handle:
                json.dump({"verdict": "AUTO_APPROVE", "total": 90}, handle)
            self.assertEqual(0, main(["--database", database, "add", "acme/shop", "commerce", "checkout", score]))
            self.assertEqual(0, main(["--database", database, "outcome", "acme/shop", "used_successfully"]))
            self.assertEqual(1, main(["--database", database, "outcome", "missing/shop", "used_successfully"]))
            with closing(sqlite3.connect(database)) as conn:
                table_exists = conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='adoption_outcomes'"
                ).fetchone()[0]
                self.assertEqual(1, table_exists)
                count = conn.execute("SELECT COUNT(*) FROM adoption_outcomes WHERE outcome='used_successfully'").fetchone()[0]
                legacy = conn.execute("SELECT adoption_history FROM templates WHERE owner_repo='acme/shop'").fetchone()[0]
            self.assertEqual(1, count)
            self.assertEqual("used_successfully", legacy)


if __name__ == "__main__":
    unittest.main()
