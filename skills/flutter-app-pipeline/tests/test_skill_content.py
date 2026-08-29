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

    def test_expected_red_reason_documented(self):
        """red-gate now verifies the failure reason, not just the exit code:
        the skill must document the EXPECTED-RED brief convention."""
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("EXPECTED-RED", text)

    def test_graphify_update_subcommand_documented(self):
        """The skill must document the corrected graphify invocation
        (`graphify update <root>`) so users do not reintroduce the wrapper."""
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("update", text)


class TestTwoModelLayering(unittest.TestCase):
    def test_two_model_skill_cross_references_flutter_layer(self):
        skill = SKILLS / "two-model-sdd-pipeline" / "SKILL.md"
        self.assertTrue(skill.exists())
        text = skill.read_text(encoding="utf-8")
        self.assertIn("flutter-app-pipeline", text)

    def test_route_next_documented(self):
        """The deterministic router (review outcome -> next action) must be
        documented in the two-model skill."""
        skill = SKILLS / "two-model-sdd-pipeline" / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        self.assertIn("route-next", text)

    def test_no_approval_gate_after_decisions(self):
        """After the gate and Phase 2 selection, the branch runs to
        completion without approval check-ins - the skill must say so."""
        skill = SKILLS / "two-model-sdd-pipeline" / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        self.assertIn("no approval", text)

    def test_models_pre_defined_or_asked_when_not_installed(self):
        """Tiers are pre-configured locally; the gate asks the user only
        when the pipeline is not installed."""
        skill = SKILLS / "two-model-sdd-pipeline" / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        self.assertIn("pre-configured", text)


if __name__ == "__main__":
    unittest.main()