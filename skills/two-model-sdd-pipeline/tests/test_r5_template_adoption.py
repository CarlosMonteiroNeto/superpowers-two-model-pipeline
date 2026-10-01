"""Evidence- and compatibility-gated template adoption."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts" / "template_adoption.py"


def load_module():
    spec = importlib.util.spec_from_file_location("r5_template_adoption", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TemplateAdoptionTests(unittest.TestCase):
    def setUp(self): self.adoption = load_module()

    def test_technical_and_requirement_checks_allow_adoption_regardless_of_score(self):
        request = {"requirements": ["api", "tests"], "target_files": {"lib/local.py": "local"}}
        evidence = {"source": "https://example.invalid/template", "license": {"status": "known", "value": "mit"}, "compatibility": "compatible", "checks": {"api": True, "tests": True}, "files": {"lib/main.py": "candidate"}, "score": 0}
        result = self.adoption.prepare(request, evidence)
        self.assertEqual("adopted", result["status"])
        self.assertEqual("local", result["preserved_local"]["lib/local.py"])

    def test_missing_ambiguous_or_conflicting_evidence_questions_and_incompatibility_blocks(self):
        self.assertEqual("question", self.adoption.prepare({"requirements": ["api"]}, {"source": "x"})["status"])
        evidence = {"source": "x", "license": {"status": "known", "value": "mit"}, "compatibility": "compatible", "checks": {"api": True}, "conflicts": ["config"]}
        self.assertEqual("question", self.adoption.prepare({"requirements": ["api"]}, evidence)["status"])
        evidence["conflicts"] = []
        evidence["files"] = {"config.json": "candidate"}
        self.assertEqual("question", self.adoption.prepare({"requirements": ["api"], "target_files": {"config.json": "local"}}, evidence)["status"])
        evidence["compatibility"] = "incompatible"
        self.assertEqual("block", self.adoption.prepare({"requirements": ["api"]}, evidence)["status"])
