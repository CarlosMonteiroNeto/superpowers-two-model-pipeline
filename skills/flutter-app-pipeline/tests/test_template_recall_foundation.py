import datetime
import json
import pathlib
import sqlite3
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

from template_catalog import _connect, list_templates, upsert_template
from template_embed import embedding_identity
from template_evidence import EvidenceCollectionError, collect_evidence
from template_recall import recall
from template_refresh import refresh_one


class RecallFoundationTests(unittest.TestCase):
    def test_filters_stale_before_top_n_and_ranks_overlap_then_repo(self):
        conn = _connect(":memory:")
        fresh = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=10)).isoformat()
        old = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=181)).isoformat()
        for repo, stamp, packages in [("z/fresh", fresh, ["a"]), ("a/fresh", fresh, ["a"]), ("m/stale", old, ["a", "b"])]:
            upsert_template(conn, repo, "cat", repo, {"verdict": "AUTO_APPROVE", "total": 80}, {"evidence_hash": repo, "fetched_at": stamp})
            conn.execute("UPDATE templates SET package_names=? WHERE owner_repo=?", (str(packages), repo))
        status, rows = recall(conn, "cat", packages=["a", "b"], top_n=1)
        self.assertEqual(status, "HIT")
        self.assertEqual(rows[0]["owner_repo"], "a/fresh")

    def test_invalid_inputs_are_setup_failures(self):
        conn = _connect(":memory:")
        self.assertEqual(recall(conn, "cat", top_n=0)[0], "SETUP_ERROR")
        self.assertEqual(recall(conn, "cat", max_age_days=float("nan"))[0], "SETUP_ERROR")
        self.assertEqual(recall(conn, "cat", query_vector=[0.0], model="model-a")[0], "SETUP_ERROR")
        self.assertEqual(recall(conn, "cat", query_vector=[float("nan")], model="model-a")[0], "SETUP_ERROR")

    def test_missing_or_malformed_evidence_dates_never_support_a_hit(self):
        conn = _connect(":memory:")
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        upsert_template(conn, "missing/hash", "cat", "missing", {"verdict": "AUTO_APPROVE"}, {"fetched_at": now})
        upsert_template(conn, "bad/date", "cat", "bad", {"verdict": "AUTO_APPROVE"}, {"evidence_hash": "bad", "fetched_at": "not-a-date"})
        upsert_template(conn, "future/date", "cat", "future", {"verdict": "AUTO_APPROVE"}, {"evidence_hash": "future", "fetched_at": "2999-01-01T00:00:00+00:00"})
        self.assertEqual(recall(conn, "cat")[0], "MISS")

    def _vector_row(self, conn, vector=None, *, source_hash="source-a", model="model-a", identity=None):
        fetched = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).isoformat()
        upsert_template(
            conn,
            "acme/vector",
            "cat",
            "vector",
            {"verdict": "AUTO_APPROVE"},
            {"evidence_hash": source_hash, "fetched_at": fetched},
        )
        identity = identity or embedding_identity(model, source_hash)
        conn.execute(
            "UPDATE templates SET vector=?, vector_identity=? WHERE owner_repo=?",
            (json.dumps({"model": model, "source_hash": source_hash, "identity": identity, "vector": vector or [1.0, 0.0]}), identity, "acme/vector"),
        )

    def test_vector_identity_is_recomputed_from_model_and_source_hash(self):
        conn = _connect(":memory:")
        self._vector_row(conn, identity="arbitrary-but-consistent")
        self.assertEqual(recall(conn, "cat", query_vector=[1.0, 0.0], model="model-a")[0], "SETUP_ERROR")

        conn = _connect(":memory:")
        self._vector_row(conn, source_hash="source-a", model="model-b")
        self.assertEqual(recall(conn, "cat", query_vector=[1.0, 0.0], model="model-a")[0], "SETUP_ERROR")

    def test_invalid_stored_vectors_are_setup_errors_when_requested(self):
        cases = (
            "not-json",
            json.dumps([1.0, 0.0]),
            json.dumps({"model": "model-a", "source_hash": "source-a", "identity": embedding_identity("model-a", "source-a"), "vector": [0.0, 0.0]}),
            json.dumps({"model": "model-a", "source_hash": "source-a", "identity": embedding_identity("model-a", "source-a"), "vector": [float("nan"), 0.0]}),
            json.dumps({"model": "model-a", "source_hash": "source-a", "identity": embedding_identity("model-a", "source-a"), "vector": [1.0]}),
        )
        for stored in cases:
            with self.subTest(stored=stored):
                conn = _connect(":memory:")
                self._vector_row(conn)
                identity = embedding_identity("model-a", "source-a")
                conn.execute("UPDATE templates SET vector=?, vector_identity=? WHERE owner_repo=?", (stored, identity, "acme/vector"))
                self.assertEqual(recall(conn, "cat", query_vector=[1.0, 0.0], model="model-a")[0], "SETUP_ERROR")

    def test_valid_vector_identity_and_dimensions_produce_a_hit(self):
        conn = _connect(":memory:")
        self._vector_row(conn)
        status, rows = recall(conn, "cat", query_vector=[1.0, 0.0], model="model-a")
        self.assertEqual(status, "HIT")
        self.assertEqual(rows[0]["owner_repo"], "acme/vector")

    def test_refresh_preserves_existing_row_on_collection_or_validation_failure(self):
        conn = _connect(":memory:")
        fetched = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).isoformat()
        upsert_template(conn, "acme/keep", "cat", "keep", {"verdict": "AUTO_APPROVE", "total": 80}, {"evidence_hash": "old", "fetched_at": fetched})
        before = list_templates(conn)
        entry = {"owner_repo": "acme/keep", "category": "cat", "project": "keep"}

        def unavailable(*_args):
            raise EvidenceCollectionError("offline")

        with self.assertRaises(EvidenceCollectionError):
            refresh_one(conn, entry, collect=unavailable)
        self.assertEqual(list_templates(conn), before)

        with self.assertRaises(ValueError):
            refresh_one(conn, entry, collect=lambda *_args: {"owner_repo": "acme/keep", "score_report": {"verdict": "AUTO_APPROVE"}, "evidence_hash": "new"})
        self.assertEqual(list_templates(conn), before)

    def test_collection_failure_is_not_converted_to_a_default_score(self):
        def offline(*_args):
            raise OSError("offline")

        with self.assertRaises(EvidenceCollectionError):
            collect_evidence("acme/offline", fetch_json=offline)


if __name__ == "__main__":
    unittest.main()
