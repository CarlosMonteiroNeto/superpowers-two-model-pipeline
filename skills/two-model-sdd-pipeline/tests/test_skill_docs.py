import pathlib
import unittest

SKILLS = pathlib.Path(__file__).resolve().parent.parent.parent
REPO = SKILLS.parent


class TestParseReviewWiredInDocs(unittest.TestCase):
    def test_readme_llm_documents_parse_review(self):
        text = (REPO / "README-LLM.md").read_text(encoding="utf-8")
        self.assertIn("parse-review", text)

    def test_readme_txt_documents_parse_review(self):
        text = (REPO / "README.txt").read_text(encoding="utf-8")
        self.assertIn("parse-review", text)

    def test_skill_documents_parse_review(self):
        text = (SKILLS / "two-model-sdd-pipeline" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("parse-review", text)

    def test_skill_owner_consistent(self):
        """SKILL.md must not claim Script A runs parse-review (B does)."""
        text = (SKILLS / "two-model-sdd-pipeline" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("Script A after D's log lands", text)
        self.assertNotIn("(B does not run it)", text)

    def test_corrective_path_convention_documented(self):
        """The corrective brief must go to task-N-corrective.md (distinct path,
        never overwriting task-N-brief.md)."""
        skill = (SKILLS / "two-model-sdd-pipeline" / "SKILL.md").read_text(encoding="utf-8")
        brief = (SKILLS / "two-model-sdd-pipeline" / "controller-brief-prompt.md").read_text(encoding="utf-8")
        self.assertIn("task-N-corrective.md", skill)
        self.assertIn("task-N-corrective.md", brief)


if __name__ == "__main__":
    unittest.main()