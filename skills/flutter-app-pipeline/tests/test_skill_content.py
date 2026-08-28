import pathlib
import unittest

SKILLS = pathlib.Path(__file__).resolve().parent.parent.parent


class TestFlutterAppPipelineSkill(unittest.TestCase):
    def setUp(self):
        self.skill = SKILLS / "flutter-app-pipeline" / "SKILL.md"

    def test_skill_exists(self):
        self.assertTrue(self.skill.exists(), "flutter-app-pipeline/SKILL.md is missing")

    def test_layers_on_two_model_pipeline(self):
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("two-model-sdd-pipeline", text)

    def test_score_formula_normalizes_by_160(self):
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("(points / 160) × 30", text)

    def test_phase_2c_uses_writing_plans(self):
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("writing-plans", text)

    def test_graphify_before_llm_invariant(self):
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("graphify-regen", text)
        self.assertIn("graphify-package", text)

    def test_deterministic_gate_scripts_referenced(self):
        text = self.skill.read_text(encoding="utf-8")
        for script in ("green-gate", "red-gate", "pub-sync", "pkg-score"):
            self.assertIn(script, text, f"{script} missing from skill")

    def test_gate_thresholds_documented(self):
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("70", text)
        self.assertIn("50", text)


class TestTwoModelLayering(unittest.TestCase):
    def test_two_model_skill_cross_references_flutter_layer(self):
        skill = SKILLS / "two-model-sdd-pipeline" / "SKILL.md"
        self.assertTrue(skill.exists())
        text = skill.read_text(encoding="utf-8")
        self.assertIn("flutter-app-pipeline", text)


if __name__ == "__main__":
    unittest.main()