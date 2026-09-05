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

    def test_score_formula_normalizes_by_160_and_weight_20(self):
        """Re-weighted (spec Section 6): pub points now weight 20, not 30."""
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("(points / 160) × 20", text)
        self.assertNotIn("(points / 160) × 30", text)

    def test_health_signals_55_documented(self):
        """The skill must state the health signals (recency + SDK + issue
        ratio) sum to 55 of 100 after the re-weight."""
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("55", text)

    def test_phase_2c_uses_writing_plans(self):
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("writing-plans", text)

    def test_graphify_before_llm_invariant(self):
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("graphify-regen", text)
        self.assertIn("graphify-package", text)

    def test_graphify_is_update_before_commit_and_subgraph(self):
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("graphify-subgraph", text)
        self.assertIn("never per Coder iteration", text)

    def test_rtk_compression_invariant(self):
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("scripts/cmd", text)
        self.assertIn("RTK_ENABLED", text)
        self.assertIn("RTK_BIN", text)

    def test_deterministic_gate_scripts_referenced(self):
        text = self.skill.read_text(encoding="utf-8")
        for script in ("green-gate", "red-gate", "pub-sync", "pkg-score"):
            self.assertIn(script, text, f"{script} missing from skill")

    def test_template_scripts_referenced(self):
        """The new project-level template stage must be documented: both the
        orchestrator and the scorer are referenced."""
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("template-search", text)
        self.assertIn("template-score", text)

    def test_template_search_order_and_stop_rule_documented(self):
        """The skill must document the template search order (specific first,
        stars descending) and the 3-AUTO_APPROVE stop rule."""
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("specific", text)
        self.assertIn("3", text)

    def test_template_adoption_flow_documented(self):
        """Phase 2c change: the adopted template is cloned + graphified into a
        template gap analysis that seeds the plan tasks (Section 7)."""
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("gap analysis", text)
        self.assertIn("clone", text)

    def test_no_code_downloaded_invariant_relaxed_for_template(self):
        """The 'no code downloaded' invariant is relaxed ONLY for the adopted
        template (clone + graphify); package downloads stay lockfile-only in
        Phase 2c."""
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("template", text)

    def test_gate_thresholds_documented(self):
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("70", text)
        self.assertIn("50", text)

    def test_expected_red_reason_documented(self):
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("EXPECTED-RED", text)

    def test_graphify_update_subcommand_documented(self):
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("update", text)


class TestTwoModelLayering(unittest.TestCase):
    def test_two_model_skill_cross_references_flutter_layer(self):
        skill = SKILLS / "two-model-sdd-pipeline" / "SKILL.md"
        self.assertTrue(skill.exists())
        text = skill.read_text(encoding="utf-8")
        self.assertIn("flutter-app-pipeline", text)

    def test_route_next_documented(self):
        skill = SKILLS / "two-model-sdd-pipeline" / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        self.assertIn("route-next", text)

    def test_no_approval_gate_after_decisions(self):
        skill = SKILLS / "two-model-sdd-pipeline" / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        self.assertIn("no approval", text)

    def test_models_pre_defined_or_asked_when_not_installed(self):
        skill = SKILLS / "two-model-sdd-pipeline" / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        self.assertIn("pre-configured", text)


if __name__ == "__main__":
    unittest.main()