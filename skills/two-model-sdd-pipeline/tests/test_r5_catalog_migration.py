"""Transactional migration and backup tests for the generic asset catalog."""

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts" / "asset_catalog.py"


def load_catalog():
    spec = importlib.util.spec_from_file_location("r5_asset_catalog_migration", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_evidence():
    return {
        "ecosystem": "python",
        "name": "acme/new",
        "version": "1.0",
        "source": {"type": "git", "uri": "https://example.invalid/acme/new"},
        "license": {"status": "known", "value": "apache-2.0"},
        "evidence_hash": "new-evidence",
        "compatibility": {"runtime": "python>=3.10"},
        "evidence": {"summary": "fixture"},
    }


@unittest.skipUnless(SCRIPT.is_file(), "shared asset catalog not created yet")
class CatalogMigrationTests(unittest.TestCase):
    def _legacy_db(self, path, report='{"verdict":"AUTO_APPROVE"}'):
        with closing(sqlite3.connect(path)) as connection:
            connection.execute(
                "CREATE TABLE templates (owner_repo TEXT PRIMARY KEY, category TEXT, project TEXT, score_report TEXT, evidence_hash TEXT)"
            )
            connection.execute(
                "INSERT INTO templates VALUES (?, ?, ?, ?, ?)",
                ("acme/legacy", "generic", "legacy project", report, "legacy-hash"),
            )
            connection.commit()

    def test_migration_creates_version_and_backup_and_is_idempotent(self):
        catalog = load_catalog()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "catalog.sqlite3"
            self._legacy_db(database)
            migrated = catalog.upsert(str(database), valid_evidence())
            self.assertTrue(migrated["asset_id"])
            self.assertEqual(1, catalog.schema_version(str(database)))
            backup = catalog.backup_path(str(database))
            self.assertTrue(Path(backup).is_file())
            with closing(sqlite3.connect(backup)) as connection:
                self.assertEqual(0, connection.execute("PRAGMA user_version").fetchone()[0])
                self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM templates").fetchone()[0])
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(2, connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0])
                self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM templates").fetchone()[0])
            catalog.upsert(str(database), valid_evidence())
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(2, connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0])

    def test_failed_migration_rolls_back_and_preserves_original_database_and_backup(self):
        catalog = load_catalog()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "catalog.sqlite3"
            self._legacy_db(database, report="not-json")
            before = database.read_bytes()
            with self.assertRaises(ValueError):
                catalog.upsert(str(database), valid_evidence())

            backup = Path(catalog.backup_path(str(database)))
            self.assertTrue(backup.is_file())
            self.assertEqual(before, database.read_bytes())
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(0, connection.execute("PRAGMA user_version").fetchone()[0])
                self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM templates").fetchone()[0])
                self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='assets'").fetchone())


if __name__ == "__main__":
    unittest.main()
