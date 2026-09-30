"""Integrity and reuse contracts for the run-scoped Graphify evidence cache."""

import concurrent.futures
import hashlib
import json
import pathlib
import sys
import tempfile
import threading
import unittest
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from test_dependency_cache import (
    cleanup_owned_root,
    create_owned_root,
    get_or_build,
    make_key,
)


def cache_inputs():
    return {
        "repository_namespace": "https://example.invalid/acme/repo.git",
        "snapshot_inventory": [
            {"path": "src/app.py", "sha256": hashlib.sha256(b"source").hexdigest(), "mode": 33188},
            {"path": "pyproject.toml", "sha256": hashlib.sha256(b"resolution").hexdigest(), "mode": 33188},
        ],
        "resolution_inputs": {"python-dependencies": ["pytest"]},
        "extractor_identity": {"version": "0.9.50", "schema": 1, "binary_sha256": "1" * 64},
        "adapter_identity": "2" * 64,
        "policy_identity": {"version": "r4-impact-1"},
    }


def complete_evidence():
    return {
        "complete": True,
        "forward_edges": {"src/app.py": ["tests/test_app.py"]},
        "reverse_edges": {"src/app.py": ["tests/test_app.py"]},
        "graphify_version": "0.9.50",
        "graph_digest": "a" * 64,
        "source_inventory_hash": "b" * 64,
        "diagnostics": [],
    }


class DependencyCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name) / "cache"
        self.root.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def test_same_snapshot_reuses_one_validated_build(self):
        calls = []

        def build():
            calls.append(True)
            return complete_evidence()

        key = make_key(cache_inputs())
        first = get_or_build(self.root, key, build)
        second = get_or_build(self.root, key, build)

        self.assertEqual(first, complete_evidence())
        self.assertEqual(second, first)
        self.assertEqual(len(calls), 1)

    def test_content_resolution_extractor_adapter_policy_and_repository_change_keys(self):
        original = cache_inputs()
        variations = [
            ("snapshot_inventory", [{"path": "src/app.py", "sha256": "3" * 64, "mode": 33188}]),
            ("resolution_inputs", {"python-dependencies": ["pytest", "ruff"]}),
            ("extractor_identity", {"version": "0.9.51", "schema": 1, "binary_sha256": "1" * 64}),
            ("adapter_identity", "4" * 64),
            ("policy_identity", {"version": "r4-impact-2"}),
            ("repository_namespace", "https://example.invalid/other/repo.git"),
        ]
        original_key = make_key(original)
        for field, changed in variations:
            with self.subTest(field=field):
                candidate = dict(original)
                candidate[field] = changed
                self.assertNotEqual(original_key, make_key(candidate))

    def test_corrupt_schema_payload_and_incomplete_entries_rebuild(self):
        key = make_key(cache_inputs())
        calls = []

        def build():
            calls.append(True)
            return complete_evidence()

        get_or_build(self.root, key, build)
        entry = self.root / (key + ".json")
        entry.write_text("{truncated", encoding="utf-8")
        self.assertEqual(get_or_build(self.root, key, build), complete_evidence())
        self.assertEqual(len(calls), 2)
        payload = json.loads(entry.read_text(encoding="utf-8"))
        payload["schema_version"] = 999
        entry.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(get_or_build(self.root, key, build), complete_evidence())
        self.assertEqual(len(calls), 3)

        incomplete = dict(complete_evidence(), complete=False, diagnostics=["missing source"])
        incomplete_key = make_key(dict(cache_inputs(), repository_namespace="incomplete"))
        self.assertEqual(get_or_build(self.root, incomplete_key, lambda: incomplete), incomplete)
        self.assertFalse((self.root / (incomplete_key + ".json")).exists())

    def test_concurrent_publication_never_exposes_partial_entries(self):
        key = make_key(cache_inputs())
        barrier = threading.Barrier(6)

        def build():
            barrier.wait(timeout=5)
            return complete_evidence()

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _index: get_or_build(self.root, key, build), range(6)))

        self.assertTrue(all(item == complete_evidence() for item in results))
        cached = json.loads((self.root / (key + ".json")).read_text(encoding="utf-8"))
        self.assertEqual(cached["evidence"], complete_evidence())

    def test_cache_write_failure_keeps_fresh_complete_evidence(self):
        key = make_key(cache_inputs())
        expected = complete_evidence()
        with mock.patch("test_dependency_cache.os.replace", side_effect=OSError("read-only cache")):
            result = get_or_build(self.root, key, lambda: expected)
        self.assertEqual(result, expected)
        self.assertFalse((self.root / (key + ".json")).exists())

    def test_cleanup_removes_only_an_owned_temporary_root(self):
        owned = create_owned_root()
        arbitrary = pathlib.Path(self.temporary.name) / "caller-owned"
        arbitrary.mkdir()

        self.assertTrue(cleanup_owned_root(owned))
        self.assertFalse(owned.exists())
        self.assertFalse(cleanup_owned_root(arbitrary))
        self.assertTrue(arbitrary.exists())


if __name__ == "__main__":
    unittest.main()
