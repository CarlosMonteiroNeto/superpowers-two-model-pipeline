import pathlib
import unittest

SKILLS = pathlib.Path(__file__).resolve().parent.parent.parent


class TestTwoModelCacheAwareResume(unittest.TestCase):
    def setUp(self):
        self.dir = SKILLS / "two-model-sdd-pipeline"
        self.skill = self.dir / "SKILL.md"

    def test_coder_resume_rule_present(self):
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("Resume rule", text)

    def test_resume_limited_to_within_task(self):
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("WITHIN a task", text)

    def test_fresh_dispatch_when_task_changes(self):
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("fresh", text.lower())
        self.assertIn("task changes", text)

    def test_arbitration_and_final_review_stay_fresh(self):
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("arbitration", text)
        self.assertIn("final review", text)
        self.assertIn("fresh", text.lower())

    def test_cache_prefix_rule_documented(self):
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("cached prefix", text)
        self.assertIn("append", text)

    def test_coder_prompt_allows_resume(self):
        prompt = (self.dir / "coder-prompt.md").read_text(encoding="utf-8")
        self.assertIn("resume", prompt.lower())
        self.assertNotIn("never resume", prompt.lower())

    def test_cmd_runner_documented(self):
        """Every LLM-invoked command runs through scripts/cmd: full output to
        a file, RTK-compressed stdout, RTK_ENABLED/RTK_BIN envs."""
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("scripts/cmd", text)
        self.assertIn("RTK_ENABLED", text)
        self.assertIn("RTK_BIN", text)

    def test_run_gates_documented(self):
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("run-gates", text)

    def test_coder_prompt_is_write_only(self):
        """The Coder is write-only (ADR-0002): it must NOT route commands
        through scripts/cmd — Script A runs all gates. The prompt must say
        NEVER run test/analysis commands and preserve the TEST_DEFECT rule."""
        prompt = (self.dir / "coder-prompt.md").read_text(encoding="utf-8")
        self.assertIn("Write code ONLY", prompt)
        self.assertIn("NEVER run test", prompt)
        self.assertIn("TEST_DEFECT", prompt)

    def test_strategic_coder_prompt_removed(self):
        """The Strategic Coder role is removed (ADR-0001): escalation is B
        arbitration (ARBITRATE), so the prompt template must not exist."""
        self.assertFalse((self.dir / "strategic-coder-prompt.md").exists())

    def test_reviewer_prompt_is_json_verdict(self):
        """The Reviewer (D) returns a structured JSON verdict (Item 2/3) and
        reviews compiler-approved code only — never runs test/analyze."""
        prompt = (self.dir / "reviewer-prompt.md").read_text(encoding="utf-8")
        self.assertIn("JSON", prompt)
        self.assertIn("compiler-approved", prompt)
        self.assertIn("verdict", prompt)

    def test_reviewer_checks_spec_alignment(self):
        """A loose plan must not pass review: the revisor verifies the diff
        covers the brief's cited spec sections, and a task with no spec
        anchor is a SEND_BACK finding."""
        prompt = (self.dir / "reviewer-prompt.md").read_text(encoding="utf-8")
        self.assertIn("Spec refs", prompt)
        self.assertIn("SEND_BACK", prompt)

    def test_controller_brief_is_b_side_guidance(self):
        """Brief writing moved into the strategist session (Item 1): the
        controller-brief template is guidance for B, not a dispatch template."""
        text = (self.dir / "controller-brief-prompt.md").read_text(encoding="utf-8")
        self.assertIn("NOT a dispatch template", text)
        self.assertIn("Strategist Session", text)

    def test_red_authorship_follows_writing_good_tests(self):
        """Agente operador authors the RED tests (per writing-good-tests.md),
        specified by Agente diretor — so the skill must point at TDD's
        writing-good-tests.md, and so must the brief-writing guidance."""
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("writing-good-tests.md", text)
        prompt = (self.dir / "controller-brief-prompt.md").read_text(encoding="utf-8")
        self.assertIn("writing-good-tests.md", prompt)

    def test_no_graphify_in_process(self):
        """The knowledge graph is fully out of the pipeline: no stage
        invokes it, so the skill must not mention graphify anywhere."""
        text = self.skill.read_text(encoding="utf-8")
        self.assertNotIn("graphify", text.lower())

    def test_coder_runs_unbounded_until_green(self):
        """The Coder loop has no round budget: coder-gate retries until the
        gate passes, so the skill must document the unbounded loop and must
        not promise arbitration on round exhaustion."""
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("unbounded", text.lower())
        self.assertNotIn("4 attempts", text)
        self.assertNotIn("4/4", text)


if __name__ == "__main__":
    unittest.main()
