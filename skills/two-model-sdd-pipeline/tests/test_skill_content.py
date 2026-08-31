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

    def test_resume_limited_to_same_tier_and_task(self):
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("same tier", text)
        self.assertIn("same task", text)

    def test_fresh_dispatch_when_role_or_task_changes(self):
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("fresh", text.lower())
        self.assertIn("role or task changes", text)

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


if __name__ == "__main__":
    unittest.main()