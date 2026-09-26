import pathlib
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent.parent


class TestReadmeReflectsTemplateStage(unittest.TestCase):
    def setUp(self):
        self.readme = REPO / "README.md"

    def test_readme_exists(self):
        self.assertTrue(self.readme.exists(), "README.md is missing")

    def test_template_stage_documented(self):
        """README.md must reflect the new project-level template stage:
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
        """README.md must mention the Category Skeleton elicitation."""
        text = self.readme.read_text(encoding="utf-8")
        self.assertIn("Category Skeleton", text)

    def test_apple_design_skill_documented(self):
        """README.md must document the vendored apple-design skill that
        governs interface design."""
        text = self.readme.read_text(encoding="utf-8")
        self.assertIn("apple-design", text)

    def test_no_duplicated_manual(self):
        """The retired agent manual must be gone: no README-LLM.md file
        and no live README-LLM.md reference in the canonical README."""
        self.assertFalse(
            (REPO / "README-LLM.md").exists(),
            "retired README-LLM.md must not exist alongside README.md")
        text = self.readme.read_text(encoding="utf-8")
        self.assertIn("single canonical", text)


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

    def test_apple_design_skill_listed(self):
        """README.txt must list the vendored apple-design skill."""
        text = self.readme.read_text(encoding="utf-8")
        self.assertIn("apple-design", text)

    def test_readme_txt_points_at_canonical(self):
        """README.txt must defer to the canonical README.md instead of
        the retired manual."""
        text = self.readme.read_text(encoding="utf-8")
        self.assertIn("README.md", text)
        self.assertNotIn(
            "README-LLM.md         harness reference", text)


if __name__ == "__main__":
    unittest.main()
