"""Planning must resolve installed skills and only applicable reusable baselines."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FLOW = ROOT / "skills" / "two-model-sdd-pipeline" / "references" / "reusable-asset-planning.md"
GENERIC = ROOT / "skills" / "two-model-sdd-pipeline" / "profiles" / "generic.json"
FLUTTER = ROOT / "skills" / "two-model-sdd-pipeline" / "profiles" / "flutter-forms.json"


class PlanningReuseTests(unittest.TestCase):
    def test_flow_resolves_installed_first_and_requires_approval_before_install(self):
        self.assertTrue(FLOW.is_file(), "planning reuse flow is missing")
        text = FLOW.read_text(encoding="utf-8").lower()
        self.assertLess(text.index("installed skills"), text.index("external skills"))
        self.assertIn("explicit approval", text)
        self.assertIn("missing required skill", text)

    def test_generic_python_context_does_not_inherit_flutter_ui_requirements(self):
        generic = json.loads(GENERIC.read_text(encoding="utf-8"))
        flutter = json.loads(FLUTTER.read_text(encoding="utf-8"))
        self.assertEqual({}, generic["applicability"])
        self.assertEqual("flutter", flutter["applicability"]["ecosystem"])
        self.assertIn("python", FLOW.read_text(encoding="utf-8").lower())
        self.assertIn("flutter", FLOW.read_text(encoding="utf-8").lower())

    def test_flow_consolidates_applicable_baseline_and_limits_questions(self):
        text = FLOW.read_text(encoding="utf-8").lower()
        self.assertIn("consolidated baseline", text)
        self.assertIn("ambiguous", text)
        self.assertIn("conflict", text)
        self.assertIn("exception", text)
        self.assertIn("cached", text)

    def test_flow_documents_unresolved_dependency_and_cycle_questions(self):
        text = FLOW.read_text(encoding="utf-8")
        self.assertIn('"type":"unresolved_dependency"', text)
        self.assertIn('"type":"dependency_cycle"', text)
        self.assertIn("fixed point", text)
