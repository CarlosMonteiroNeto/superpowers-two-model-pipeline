import pathlib
import unittest

SKILLS = pathlib.Path(__file__).resolve().parent.parent.parent
REPO = SKILLS.parent


class TestCategorySkeletonInBrainstorming(unittest.TestCase):
    def setUp(self):
        self.skill = SKILLS / "brainstorming" / "SKILL.md"

    def test_skill_exists(self):
        self.assertTrue(self.skill.exists(), "brainstorming/SKILL.md is missing")

    def test_required_elicitation_step_documented(self):
        """Phase 1a must gain a REQUIRED elicitation step for the Category
        Skeleton (spec Section 3)."""
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("Category Skeleton", text)

    def test_three_fields_in_exact_order(self):
        """The elicitation order is fixed: generic category -> specific
        category -> original implementations."""
        text = self.skill.read_text(encoding="utf-8")
        idx_generic = text.find("generic category")
        idx_specific = text.find("specific category")
        idx_original = text.find("original implementations")
        self.assertGreaterEqual(idx_generic, 0, "generic category field missing")
        self.assertGreaterEqual(idx_specific, 0, "specific category field missing")
        self.assertGreaterEqual(idx_original, 0, "original implementations field missing")
        self.assertLess(idx_generic, idx_specific, "generic category must precede specific category")
        self.assertLess(idx_specific, idx_original, "specific category must precede original implementations")

    def test_required_fields_persist_to_context(self):
        """The three fields are REQUIRED outputs of Phase 1a, persisted to
        CONTEXT.md; the spec cannot be written without them."""
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("REQUIRED", text)
        self.assertIn("CONTEXT.md", text)


class TestCategorySkeletonInContext(unittest.TestCase):
    def setUp(self):
        self.context = REPO / "CONTEXT.md"

    def test_context_exists(self):
        self.assertTrue(self.context.exists(), "CONTEXT.md is missing")

    def test_category_skeleton_fields_documented(self):
        """CONTEXT.md must document the Category Skeleton fields (generic
        category, specific category, original implementations)."""
        text = self.context.read_text(encoding="utf-8")
        self.assertIn("Category Skeleton", text)
        self.assertIn("generic category", text)
        self.assertIn("specific category", text)
        self.assertIn("original implementations", text)


if __name__ == "__main__":
    unittest.main()