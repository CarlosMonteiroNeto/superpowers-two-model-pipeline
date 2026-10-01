"""Provider-neutral deterministic recall over normalized asset evidence."""

import importlib.util
import hashlib
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RECALL_SCRIPT = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts" / "asset_recall.py"
CATALOG_SCRIPT = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts" / "asset_catalog.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def item(name, *, hash_value=None, age_days=2, runtime="py311", dependencies=None, verdict="AUTO_APPROVE", vector=None):
    fetched = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
    evidence_hash = hash_value or name + "-evidence"
    record = {
        "ecosystem": "python",
        "name": name,
        "version": "1.0",
        "source": {"type": "fixture", "uri": "https://example.invalid/" + name},
        "license": {"status": "known", "value": "mit"},
        "evidence_hash": evidence_hash,
        "compatibility": {"runtime": runtime},
        "evidence": {
            "category": "storage",
            "fetched_at": fetched,
            "dependencies": dependencies or [],
            "score_report": {"verdict": verdict},
        },
    }
    if vector is not None:
        identity = hashlib.sha256(("fixture-model" + "\0" + evidence_hash).encode("utf-8")).hexdigest()
        record["derived"] = {
            "vector": {
                "value": {"model": "fixture-model", "source_hash": evidence_hash, "identity": identity, "vector": vector},
                "identity": identity,
            }
        }
    return record


class GenericRecallDeliverableTests(unittest.TestCase):
    def test_shared_asset_recall_module_exists(self):
        self.assertTrue(RECALL_SCRIPT.is_file(), "shared asset_recall.py contract has not been implemented")


@unittest.skipUnless(RECALL_SCRIPT.is_file(), "shared asset recall not created yet")
class GenericRecallTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_module("r5_recall_catalog", CATALOG_SCRIPT)
        self.recall = load_module("r5_asset_recall", RECALL_SCRIPT)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = str(Path(self.temp.name) / "assets.sqlite3")
        self.catalog.connect(self.database).close()

    def test_freshness_compatibility_and_dependency_overlap_are_filtered_and_ranked(self):
        self.catalog.upsert(self.database, item("acme/a", dependencies=["numpy", "requests"]))
        self.catalog.upsert(self.database, item("acme/b", dependencies=["requests"]))
        self.catalog.upsert(self.database, item("acme/stale", age_days=181, dependencies=["requests"]))
        self.catalog.upsert(self.database, item("acme/incompatible", runtime="py312", dependencies=["requests"]))
        self.catalog.upsert(self.database, item("acme/unreviewed", verdict="DEVELOPER_DECISION", dependencies=["requests"]))

        result = self.recall.query(
            self.database,
            {
                "ecosystem": "python",
                "category": "storage",
                "max_age_days": 180,
                "top_n": 3,
                "required_compatibility": {"runtime": "py311"},
                "dependencies": ["requests"],
                "evidence_filters": {"score_report.verdict": "AUTO_APPROVE"},
            },
        )
        self.assertEqual("HIT", result["status"])
        self.assertEqual(["acme/a", "acme/b"], [row["name"] for row in result["results"]])
        self.assertEqual(1, result["results"][0]["dependency_overlap"])

    def test_valid_miss_and_setup_error_are_distinct_and_read_does_not_create_database(self):
        missing = str(Path(self.temp.name) / "missing.sqlite3")
        result = self.recall.query(missing, {"ecosystem": "python", "category": "storage"})
        self.assertEqual("SETUP_ERROR", result["status"])
        self.assertFalse(Path(missing).exists())

        empty = self.recall.query(self.database, {"ecosystem": "python", "category": "absent"})
        self.assertEqual("MISS", empty["status"])
        invalid = self.recall.query(self.database, {"ecosystem": "python", "max_age_days": float("nan")})
        self.assertEqual("SETUP_ERROR", invalid["status"])

    def test_deterministic_only_mode_does_not_require_or_validate_vectors(self):
        self.catalog.upsert(self.database, item("acme/no-vector", dependencies=["requests"]))
        result = self.recall.query(self.database, {"ecosystem": "python", "category": "storage"})
        self.assertEqual("HIT", result["status"])
        self.assertEqual("acme/no-vector", result["results"][0]["name"])

    def test_asset_id_filter_limits_before_ranking_and_empty_selects_none(self):
        first = self.catalog.upsert(self.database, item("acme/a"))["asset_id"]
        self.catalog.upsert(self.database, item("acme/b"))
        result = self.recall.query(self.database, {"ecosystem": "python", "asset_ids": [first], "top_n": 1})
        self.assertEqual("HIT", result["status"])
        self.assertEqual([first], [row["asset_id"] for row in result["results"]])
        self.assertEqual("MISS", self.recall.query(self.database, {"ecosystem": "python", "asset_ids": []})["status"])

    def test_asset_id_filter_requires_nonempty_string_elements(self):
        for invalid in ([""], [1], [None], "asset-id"):
            with self.subTest(invalid=invalid):
                result = self.recall.query(self.database, {"ecosystem": "python", "asset_ids": invalid})
                self.assertEqual("SETUP_ERROR", result["status"])

    def test_filtered_out_malformed_history_does_not_abort_current_selection(self):
        old_id = self.catalog.upsert(self.database, item("acme/old"))["asset_id"]
        current_id = self.catalog.upsert(self.database, item("acme/current"))["asset_id"]
        with closing(self.catalog.connect(self.database)) as conn:
            conn.execute("UPDATE assets SET evidence_json='not-json' WHERE asset_id=?", (old_id,))
        result = self.recall.query(self.database, {"ecosystem": "python", "asset_ids": [current_id]})
        self.assertEqual("HIT", result["status"])
        self.assertEqual([current_id], [row["asset_id"] for row in result["results"]])

    def test_vector_identity_model_and_dimension_are_validated_when_requested(self):
        self.catalog.upsert(self.database, item("acme/vector", vector=[1.0, 0.0]))
        query = {
            "ecosystem": "python",
            "category": "storage",
            "query_vector": {"model": "fixture-model", "source_hash": "query-hash", "identity": self.recall.embedding_identity("fixture-model", "query-hash"), "vector": [1.0, 0.0]},
        }
        valid = self.recall.query(self.database, query)
        self.assertEqual("HIT", valid["status"])
        self.assertEqual(1.0, valid["results"][0]["similarity"])

        bad = dict(query, query_vector={**query["query_vector"], "model": "other-model"})
        self.assertEqual("SETUP_ERROR", self.recall.query(self.database, bad)["status"])


if __name__ == "__main__":
    unittest.main()
