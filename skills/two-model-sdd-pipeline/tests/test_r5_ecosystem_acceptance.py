"""Cross-ecosystem contracts and package inclusion remain explicit."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INVENTORY = ROOT / "skills" / "two-model-sdd-pipeline" / "stage-capabilities.json"
PACKAGE = ROOT / "scripts" / "package-codex-plugin.sh"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EcosystemAcceptanceTests(unittest.TestCase):
    def test_flutter_and_python_fixtures_use_generic_contracts_without_support_claims(self):
        base = ROOT / "skills" / "two-model-sdd-pipeline"
        resolver = load("accept_requirement_profiles", base / "scripts" / "requirement_profiles.py")
        adoption = load("accept_template_adoption", base / "scripts" / "template_adoption.py")
        profiles = [json.loads((base / "profiles" / name).read_text(encoding="utf-8")) for name in ("generic.json", "user-interface.json", "flutter-forms.json")]
        python = resolver.resolve({"ecosystem": "python", "ui": False}, profiles)
        flutter = resolver.resolve({"ecosystem": "flutter", "ui": True, "product_type": "form"}, profiles)
        self.assertNotIn("form-validation", [item["id"] for item in python["requirements"]])
        self.assertIn("form-validation", [item["id"] for item in flutter["requirements"]])
        python_ui = resolver.resolve({"ecosystem": "python", "ui": True, "product_type": "tool"}, profiles)
        self.assertIn("accessibility", [item["id"] for item in python_ui["requirements"]])
        self.assertNotIn("form-validation", [item["id"] for item in python_ui["requirements"]])
        fixture = adoption.prepare({"requirements": ["api"]}, {"source": "local-fixture", "license": {"status": "known", "value": "mit"}, "compatibility": "compatible", "checks": {"api": True}, "files": {"src/main.py": "ok"}})
        self.assertEqual("adopted", fixture["status"])
        inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
        self.assertNotIn("supports Python", json.dumps(inventory))

    def test_packager_archives_all_skill_subtrees_including_profiles_schemas_and_wrappers(self):
        script = PACKAGE.read_text(encoding="utf-8")
        archive_args = script.split('| tar -xpf - -C "$STAGE"', 1)[0]
        self.assertIn('archive --format=tar "$REF" --', archive_args)
        self.assertIn("  skills \\\n", archive_args)
        for path in ("profiles/generic.json", "profiles/flutter-forms.json", "schemas/requirements-profile.schema.json", "scripts/asset_recall.py", "scripts/template_adoption.py"):
            self.assertTrue((ROOT / "skills" / "two-model-sdd-pipeline" / path).is_file(), path)
        self.assertTrue((ROOT / "skills" / "flutter-app-pipeline" / "scripts" / "template-recall").is_file())


if __name__ == "__main__":
    unittest.main()
