import pathlib
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent.parent


class TestReadmeLlmReflectsTemplateStage(unittest.TestCase):
    def setUp(self):
        self.readme = REPO / "README-LLM.md"

    def test_readme_exists(self):
        self.assertTrue(self.readme.exists(), "README-LLM.md is missing")

    def test_template_stage_documented(self):
        """README-LLM.md must reflect the new project-level template stage:
        template-search / template-score scripts."""
        text = self.readme.read_text(encoding="utf-8")
        self.assertIn("template-search", text)
        self.assertIn("template-score", text)

    def test_quality_score_reweighted(self):
        """The Quality Score table must show the re-weighted pkg-score
        (health signals 55): pub points × 20, not × 30."""
        text = self.readme.read_text(encoding="utf-8")
        self.assertIn("(points / 160) × 20", text)
        self.assertNotIn("(points / 160) × 30", text)

    def test_category_skeleton_documented(self):
        """README-LLM.md must mention the Category Skeleton elicitation."""
        text = self.readme.read_text(encoding="utf-8")
        self.assertIn("Category Skeleton", text)


class TestReadmeTxtReflectsTemplateStage(unittest.TestCase):
    def setUp(self):
        self.readme = REPO / "README.txt"

    def test_readme_exists(self):
        self.assertTrue(self.readme.exists(), "README.txt is missing")

    def test_template_scripts_listed(self):
        """README.txt's deterministic scripts list must include the new
        template-search / template-score scripts."""
        text = self.readme.read_text(encoding="utf-8")
        self.assertIn("template-search", text)
        self.assertIn("template-score", text)


if __name__ == "__main__":
    unittest.main()