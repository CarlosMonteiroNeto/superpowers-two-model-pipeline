"""Atomic generic evidence refresh and compatibility-wrapper parity."""

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RECALL_SCRIPT = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts" / "asset_recall.py"
CATALOG_SCRIPT = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts" / "asset_catalog.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record(hash_value="old", *, derived=None):
    return {
        "ecosystem": "python",
        "name": "acme/refreshable",
        "version": "1.0",
        "source": {"type": "git", "uri": "https://example.invalid/acme/refreshable"},
        "license": {"status": "known", "value": "apache-2.0"},
        "evidence_hash": hash_value,
        "compatibility": {"runtime": "py311"},
        "evidence": {"category": "storage", "fetched_at": datetime.now(timezone.utc).isoformat(), "dependencies": ["requests"]},
        **({"derived": derived} if derived is not None else {}),
    }


def asset_state(database, asset_id):
    with closing(sqlite3.connect(database)) as conn:
        row = conn.execute("SELECT evidence_hash, derived_json FROM assets WHERE asset_id=?", (asset_id,)).fetchone()
    return {"evidence_hash": row[0], "derived": json.loads(row[1])}


class RefreshDeliverableTests(unittest.TestCase):
    def test_shared_refresh_contract_exists(self):
        self.assertTrue(RECALL_SCRIPT.is_file(), "shared refresh API has not been implemented")


@unittest.skipUnless(RECALL_SCRIPT.is_file(), "shared asset refresh not created yet")
class RefreshParityTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_module("r5_refresh_catalog", CATALOG_SCRIPT)
        self.recall = load_module("r5_refresh_asset_recall", RECALL_SCRIPT)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = str(Path(self.temp.name) / "assets.sqlite3")

    def test_invalid_refresh_preserves_existing_asset_and_does_not_write(self):
        original = self.catalog.upsert(self.database, record(derived={"triage": {"decision": "review"}}))
        before = asset_state(self.database, original["asset_id"])
        with self.assertRaises(ValueError):
            self.recall.refresh(self.database, dict(record("new"), evidence_hash=""))
        after = asset_state(self.database, original["asset_id"])
        self.assertEqual(before, after)

    def test_valid_refresh_updates_identity_evidence_and_invalidates_derived_state(self):
        original = self.catalog.upsert(self.database, record(derived={"triage": {"decision": "review"}}))
        refreshed = self.recall.refresh(self.database, record("new"))
        self.assertEqual(original["asset_id"], refreshed["asset_id"])
        self.assertTrue(refreshed["evidence_changed"])
        self.assertEqual("new", refreshed["evidence_hash"])
        self.assertEqual({}, refreshed["derived"])
        self.assertEqual("new", asset_state(self.database, original["asset_id"])["evidence_hash"])

    def test_refresh_failure_leaves_original_database_bytes_unchanged(self):
        database = Path(self.temp.name) / "legacy.sqlite3"
        with closing(sqlite3.connect(database)) as conn:
            conn.execute("CREATE TABLE templates(owner_repo TEXT PRIMARY KEY, category TEXT, project TEXT, score_report TEXT)")
            conn.execute("INSERT INTO templates VALUES('broken/source','x','x','not-json')")
            conn.commit()
        before = database.read_bytes()
        with self.assertRaises(ValueError):
            self.recall.refresh(str(database), record("new"))
        self.assertEqual(before, database.read_bytes())


if __name__ == "__main__":
    unittest.main()
