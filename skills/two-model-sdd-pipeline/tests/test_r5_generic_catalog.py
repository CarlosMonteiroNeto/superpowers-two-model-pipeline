"""Generic asset catalog contracts, independent of any search provider."""

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts" / "asset_catalog.py"
SCHEMA = ROOT / "skills" / "two-model-sdd-pipeline" / "schemas" / "asset.schema.json"


def load_catalog():
    spec = importlib.util.spec_from_file_location("r5_asset_catalog", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evidence(**overrides):
    record = {
        "ecosystem": "python",
        "name": "acme/example-service",
        "version": "1.2.0",
        "source": {"type": "git", "uri": "https://example.invalid/acme/example-service", "revision": "abc123"},
        "license": {"status": "known", "value": "mit"},
        "evidence_hash": "evidence-one",
        "compatibility": {"runtime": "python>=3.11"},
        "evidence": {"readme": "fixture evidence", "dependencies": ["requests"]},
    }
    record.update(overrides)
    return record


class CatalogDeliverableTests(unittest.TestCase):
    def test_shared_asset_catalog_module_exists(self):
        self.assertTrue(SCRIPT.is_file(), "shared asset_catalog.py contract has not been implemented")


@unittest.skipUnless(SCRIPT.is_file(), "shared asset catalog not created yet")
class GenericCatalogTests(unittest.TestCase):
    def test_identity_includes_ecosystem_name_version_source_license_and_compatibility(self):
        catalog = load_catalog()
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "assets.sqlite3")
            first = catalog.upsert(database, evidence())
            same = catalog.upsert(database, evidence(evidence_hash="evidence-two"))
            self.assertEqual(first["asset_id"], same["asset_id"])
            self.assertEqual("evidence-two", same["evidence_hash"])
            self.assertTrue(same["evidence_changed"])

            changed_compatibility = catalog.upsert(database, evidence(compatibility={"runtime": "python>=3.12"}))
            self.assertNotEqual(same["asset_id"], changed_compatibility["asset_id"])

    def test_evidence_changes_invalidate_derived_metadata_but_keep_outcomes_separate(self):
        catalog = load_catalog()
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "assets.sqlite3")
            original = catalog.upsert(
                database,
                evidence(derived={"triage": {"decision": "review"}, "vector": {"identity": "model:evidence-one"}}),
            )
            event = catalog.record_outcome(
                database,
                {"asset_id": original["asset_id"], "outcome": "used_successfully", "actor": "developer", "provenance": {"project": "demo-app"}},
            )
            refreshed = catalog.upsert(database, evidence(evidence_hash="evidence-two"))
            self.assertEqual(original["asset_id"], refreshed["asset_id"])
            self.assertEqual({}, refreshed["derived"])
            self.assertEqual(event["outcome_id"], catalog.list_outcomes(database, original["asset_id"])[0]["outcome_id"])
            self.assertEqual("used_successfully", catalog.list_outcomes(database, original["asset_id"])[0]["outcome"])

    def test_python_fixture_uses_generic_identity_without_claiming_provider_search(self):
        catalog = load_catalog()
        with tempfile.TemporaryDirectory() as directory:
            result = catalog.upsert(str(Path(directory) / "assets.sqlite3"), evidence())
            self.assertEqual("python", result["identity"]["ecosystem"])
            self.assertEqual("acme/example-service", result["identity"]["name"])
            self.assertEqual("evidence-one", result["identity"]["evidence_hash"])

    def test_invalid_identity_is_rejected_before_persistence(self):
        catalog = load_catalog()
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "assets.sqlite3")
            with self.assertRaises(ValueError):
                catalog.upsert(database, evidence(license="MIT"))
            self.assertFalse(Path(database).exists())

    def test_asset_schema_describes_required_identity_and_provenance_fields(self):
        self.assertTrue(SCHEMA.is_file(), "generic asset schema has not been created")
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        required = set(schema["required"])
        self.assertTrue({"ecosystem", "name", "version", "source", "license", "evidence_hash", "compatibility", "evidence"}.issubset(required))
        self.assertIn("derived", schema["properties"])


if __name__ == "__main__":
    unittest.main()
