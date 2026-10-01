"""Acceptance tests for the source-backed R5 Flutter capability inventory."""

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
FLUTTER_SCRIPTS = ROOT / "skills" / "flutter-app-pipeline" / "scripts"
INVENTORY_PATH = ROOT / "skills" / "two-model-sdd-pipeline" / "stage-capabilities.json"
SCHEMA_PATH = ROOT / "skills" / "two-model-sdd-pipeline" / "schemas" / "stage-capability.schema.json"
REVIEW_PATH = ROOT / "docs" / "superpowers" / "reviews" / "flutter-stage-generalization.md"


def assert_matches_schema(test_case, value, schema, root_schema=None):
    root_schema = root_schema or schema
    if "$ref" in schema:
        target = root_schema
        for segment in schema["$ref"][2:].split("/"):
            segment = segment.replace("~1", "/").replace("~0", "~")
            target = target[segment]
        return assert_matches_schema(test_case, value, target, root_schema)

    expected_type = schema.get("type")
    type_checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "boolean": lambda item: isinstance(item, bool),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
    }
    if expected_type:
        test_case.assertTrue(type_checks[expected_type](value), f"expected {expected_type}: {value!r}")
    if "const" in schema:
        test_case.assertEqual(schema["const"], value)
    if "enum" in schema:
        test_case.assertIn(value, schema["enum"])
    if "pattern" in schema:
        test_case.assertRegex(value, schema["pattern"])
    if "minLength" in schema:
        test_case.assertGreaterEqual(len(value), schema["minLength"])
    if expected_type == "array":
        test_case.assertGreaterEqual(len(value), schema.get("minItems", 0))
        if "maxItems" in schema:
            test_case.assertLessEqual(len(value), schema["maxItems"])
        if schema.get("uniqueItems"):
            encoded = [json.dumps(item, sort_keys=True) for item in value]
            test_case.assertEqual(len(encoded), len(set(encoded)), "array items must be unique")
        for item in value:
            assert_matches_schema(test_case, item, schema["items"], root_schema)
    if expected_type == "object":
        test_case.assertTrue(set(schema.get("required", [])).issubset(value))
        if schema.get("additionalProperties") is False:
            test_case.assertLessEqual(set(value), set(schema.get("properties", {})))
        for name, child_schema in schema.get("properties", {}).items():
            if name in value:
                assert_matches_schema(test_case, value[name], child_schema, root_schema)


class StageInventoryTests(unittest.TestCase):
    def test_inventory_and_schema_are_delivered(self):
        self.assertTrue(INVENTORY_PATH.is_file(), "R5 stage-capabilities.json has not been created")
        self.assertTrue(SCHEMA_PATH.is_file(), "R5 stage capability schema has not been created")

    def test_review_records_dispositions_and_scope_limits(self):
        self.assertTrue(REVIEW_PATH.is_file(), "R5 Flutter generalization review has not been written")
        review = " ".join(REVIEW_PATH.read_text(encoding="utf-8").split())
        self.assertIn("stage-capabilities.json", review)
        self.assertIn("phase-0", review)
        self.assertIn("phase-8", review)
        self.assertIn("24 scripts", review)
        self.assertIn("does not claim new ecosystem support", review)

    @unittest.skipUnless(INVENTORY_PATH.is_file() and SCHEMA_PATH.is_file(), "inventory/schema not created yet")
    def test_inventory_declares_every_flutter_phase_zero_through_eight(self):
        inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            [f"phase-{number}" for number in range(9)],
            inventory["stages"],
        )

    @unittest.skipUnless(INVENTORY_PATH.is_file() and SCHEMA_PATH.is_file(), "inventory/schema not created yet")
    def test_inventory_schema_references_resolve_and_capability_contract_is_present(self):
        inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        required = {"stage", "source", "current_owner", "disposition", "target_owner", "plan_task", "evidence", "callers"}
        self.assertEqual("object", schema["type"])
        self.assertTrue(required.issubset(set(schema["$defs"]["capability"]["required"])))

        def resolve_pointer(reference):
            self.assertTrue(reference.startswith("#/"), reference)
            value = schema
            for segment in reference[2:].split("/"):
                segment = segment.replace("~1", "/").replace("~0", "~")
                value = value[segment]
            return value

        def visit(value):
            if isinstance(value, dict):
                if "$ref" in value:
                    self.assertIsInstance(resolve_pointer(value["$ref"]), dict)
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(schema)
        self.assertEqual("#/$defs/capability", schema["properties"]["capabilities"]["items"]["$ref"])

    @unittest.skipUnless(INVENTORY_PATH.is_file() and SCHEMA_PATH.is_file(), "inventory/schema not created yet")
    def test_inventory_covers_every_flutter_script_with_source_and_caller_evidence(self):
        inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        capabilities = inventory["capabilities"]
        represented = {
            source
            for capability in capabilities
            for source in capability["source"]
            if source.startswith("skills/flutter-app-pipeline/scripts/")
        }
        actual = {
            path.relative_to(ROOT).as_posix()
            for path in FLUTTER_SCRIPTS.iterdir()
            if path.is_file()
        }
        self.assertEqual(actual, represented)

        for capability in capabilities:
            self.assertTrue(capability["evidence"], capability)
            self.assertTrue(capability["callers"], capability)
            for source in capability["source"] + capability["evidence"] + capability["callers"]:
                path = source.split("#", 1)[0]
                self.assertTrue((ROOT / path).is_file(), f"missing source evidence: {source}")

    @unittest.skipUnless(INVENTORY_PATH.is_file() and SCHEMA_PATH.is_file(), "inventory/schema not created yet")
    def test_every_disposition_has_an_r5_task_or_accepted_round_owner(self):
        inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        for capability in inventory["capabilities"]:
            task = capability["plan_task"]
            self.assertRegex(task, r"^(R5\.[2-7]|R[1-4]\.[1-9])$", capability)
            self.assertIn(
                capability["disposition"],
                {"shared", "flutter-specific", "adaptation-required"},
                capability,
            )

    @unittest.skipUnless(INVENTORY_PATH.is_file() and SCHEMA_PATH.is_file(), "inventory/schema not created yet")
    def test_inventory_does_not_claim_new_ecosystem_support(self):
        inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        self.assertFalse(inventory["claims_new_ecosystem_support"])
        self.assertTrue(inventory["generic_fixtures_are_contract_only"])

    @unittest.skipUnless(INVENTORY_PATH.is_file() and SCHEMA_PATH.is_file(), "inventory/schema not created yet")
    def test_inventory_instance_matches_its_schema_contract(self):
        inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        assert_matches_schema(self, inventory, schema)

        invalid_inventory = dict(inventory, undeclared_field=True)
        with self.assertRaises(AssertionError):
            assert_matches_schema(self, invalid_inventory, schema)


if __name__ == "__main__":
    unittest.main()
