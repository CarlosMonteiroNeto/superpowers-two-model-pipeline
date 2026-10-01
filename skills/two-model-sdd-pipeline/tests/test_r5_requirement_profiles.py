"""Applicable requirement profile resolution and conflict handling."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts" / "requirement_profiles.py"
SCHEMA = ROOT / "skills" / "two-model-sdd-pipeline" / "schemas" / "requirements-profile.schema.json"
UI_PROFILE = ROOT / "skills" / "two-model-sdd-pipeline" / "profiles" / "user-interface.json"
FLUTTER_PROFILE = ROOT / "skills" / "two-model-sdd-pipeline" / "profiles" / "flutter-forms.json"


def load_module():
    spec = importlib.util.spec_from_file_location("r5_requirement_profiles", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RequirementProfileDeliverables(unittest.TestCase):
    def test_shared_resolver_and_schema_exist(self):
        self.assertTrue(SCRIPT.is_file(), "shared profile resolver is missing")
        self.assertTrue(SCHEMA.is_file(), "profile schema is missing")
        self.assertTrue(UI_PROFILE.is_file(), "applicable UI overlay is missing")


@unittest.skipUnless(SCRIPT.is_file(), "resolver not implemented")
class RequirementProfileTests(unittest.TestCase):
    def setUp(self):
        self.resolver = load_module()
        self.profiles = [
            {"profile_id": "generic", "version": "1", "applicability": {}, "requirements": [
                {"id": "errors", "description": "Handle errors", "checks": ["error-path"], "dependencies": []},
                {"id": "auth", "description": "Authentication", "checks": ["identity"], "dependencies": []},
            ]},
            {"profile_id": "user-interface", "version": "1", "applicability": {"ui": True}, "requirements": [
                {"id": "accessibility", "description": "Support accessible interactions", "checks": ["a11y"], "dependencies": []},
            ]},
            {"profile_id": "flutter-forms", "version": "2", "applicability": {"ui": True, "product_type": "form"}, "requirements": [
                {"id": "validation", "description": "Validate fields", "checks": ["field-validation"], "dependencies": []},
                {"id": "mask", "description": "Format input", "checks": ["formatting"], "dependencies": []},
            ]},
            {"profile_id": "br", "version": "1", "applicability": {"locale": "pt-BR"}, "requirements": [
                {"id": "locale-copy", "description": "Use Brazilian Portuguese", "checks": ["locale"], "dependencies": []},
            ]},
        ]

    def test_generic_overlay_and_locale_are_deterministic(self):
        result = self.resolver.resolve({"ui": True, "product_type": "form", "locale": "pt-BR"}, self.profiles)
        self.assertEqual(["accessibility", "auth", "errors", "locale-copy", "mask", "validation"], [r["id"] for r in result["requirements"]])
        self.assertEqual([], result["exceptions"])
        self.assertEqual([], result["questions"])

    def test_non_ui_skips_form_profile_and_opt_out_is_a_reasoned_exception(self):
        result = self.resolver.resolve({"ui": False, "product_type": "api", "opt_outs": {"auth": "existing identity provider"}}, self.profiles)
        self.assertEqual(["errors"], [r["id"] for r in result["requirements"]])
        self.assertEqual("existing identity provider", result["exceptions"][0]["reason"])

    def test_non_flutter_ui_gets_accessibility_without_flutter_form_requirements(self):
        result = self.resolver.resolve({"ecosystem": "python", "ui": True, "product_type": "tool"}, self.profiles)
        ids = [item["id"] for item in result["requirements"]]
        self.assertIn("accessibility", ids)
        self.assertNotIn("validation", ids)
        self.assertNotIn("mask", ids)

    def test_conflicting_applicable_overlays_are_reported_as_questions(self):
        conflict = {"profile_id": "other", "version": "1", "applicability": {"ui": True}, "requirements": [
            {"id": "errors", "description": "Ignore failures", "checks": ["none"], "dependencies": []},
        ]}
        result = self.resolver.resolve({"ui": True, "product_type": "form"}, self.profiles + [conflict])
        self.assertNotIn("errors", [r["id"] for r in result["requirements"]])
        self.assertTrue(any("errors" in str(question) for question in result["questions"]))

    def test_masks_remain_separate_from_validation_and_no_boundaries_are_inferred(self):
        result = self.resolver.resolve({"ui": True, "product_type": "form"}, self.profiles)
        by_id = {item["id"]: item for item in result["requirements"]}
        self.assertEqual("formatting", by_id["mask"]["checks"][0])
        self.assertNotIn("server-validation", str(result["requirements"]))
        self.assertNotIn("payment", str(result))

    def test_packaged_form_opt_out_blocks_dependent_mask(self):
        import json
        profiles = [json.loads(FLUTTER_PROFILE.read_text(encoding="utf-8"))]
        result = self.resolver.resolve(
            {"ecosystem": "flutter", "ui": True, "product_type": "form",
             "opt_outs": {"form-validation": "handled upstream"}}, profiles)
        self.assertNotIn("input-mask", [r["id"] for r in result["requirements"]])
        self.assertIn({"type": "unresolved_dependency", "requirement_id": "input-mask",
                       "dependencies": ["form-validation"]}, result["questions"])
        self.assertEqual("handled upstream", result["exceptions"][0]["reason"])

    def test_missing_transitive_dependency_is_propagated_deterministically(self):
        profile = {"profile_id": "chain", "version": "1", "applicability": {}, "requirements": [
            {"id": "a", "description": "A", "checks": [], "dependencies": ["b"]},
            {"id": "b", "description": "B", "checks": [], "dependencies": ["c"]},
        ]}
        result = self.resolver.resolve({}, [profile])
        self.assertEqual([], result["requirements"])
        self.assertEqual([
            {"type": "unresolved_dependency", "requirement_id": "a", "dependencies": ["b"]},
            {"type": "unresolved_dependency", "requirement_id": "b", "dependencies": ["c"]},
        ], result["questions"])

    def test_conflicted_and_inapplicable_dependencies_are_unresolved(self):
        profiles = [
            {"profile_id": "consumer", "version": "1", "applicability": {}, "requirements": [
                {"id": "uses-conflict", "description": "Uses conflict", "checks": [], "dependencies": ["shared"]},
                {"id": "uses-inapplicable", "description": "Uses omitted", "checks": [], "dependencies": ["mobile-only"]},
            ]},
            {"profile_id": "one", "version": "1", "applicability": {}, "requirements": [
                {"id": "shared", "description": "Shared one", "checks": [], "dependencies": []},
            ]},
            {"profile_id": "two", "version": "1", "applicability": {}, "requirements": [
                {"id": "shared", "description": "Shared two", "checks": [], "dependencies": []},
            ]},
            {"profile_id": "mobile", "version": "1", "applicability": {"mobile": True}, "requirements": [
                {"id": "mobile-only", "description": "Mobile", "checks": [], "dependencies": []},
            ]},
        ]
        result = self.resolver.resolve({"mobile": False}, profiles)
        self.assertEqual([], result["requirements"])
        unresolved = [q for q in result["questions"] if q["type"] == "unresolved_dependency"]
        self.assertEqual([
            {"type": "unresolved_dependency", "requirement_id": "uses-conflict", "dependencies": ["shared"]},
            {"type": "unresolved_dependency", "requirement_id": "uses-inapplicable", "dependencies": ["mobile-only"]},
        ], unresolved)
        self.assertTrue(all(set(r["dependencies"]).issubset({x["id"] for x in result["requirements"]})
                            for r in result["requirements"]))

    def test_cycles_exclude_members_and_downstream_with_stable_question(self):
        profile = {"profile_id": "cycle", "version": "1", "applicability": {}, "requirements": [
            {"id": "downstream", "description": "D", "checks": [], "dependencies": ["b"]},
            {"id": "b", "description": "B", "checks": [], "dependencies": ["a"]},
            {"id": "a", "description": "A", "checks": [], "dependencies": ["b"]},
        ]}
        forward = self.resolver.resolve({}, [profile])
        reverse = self.resolver.resolve({}, [dict(profile, requirements=list(reversed(profile["requirements"])))])
        self.assertEqual([], forward["requirements"])
        self.assertEqual(forward, reverse)
        self.assertIn({"type": "dependency_cycle", "requirement_ids": ["a", "b"]}, forward["questions"])


if __name__ == "__main__":
    unittest.main()
