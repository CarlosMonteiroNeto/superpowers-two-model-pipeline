import pathlib
import unittest

SKILLS = pathlib.Path(__file__).resolve().parent.parent.parent


class TestAppleDesignSkillVendored(unittest.TestCase):
    """The interface-design skill is vendored into the pipeline repo so the
    superpowers plugin registers it (config.skills.paths) with no global
    install. Layout: skills/apple-design/SKILL.md."""

    def setUp(self):
        self.skill = SKILLS / "apple-design" / "SKILL.md"

    def test_skill_exists(self):
        self.assertTrue(
            self.skill.exists(), "apple-design/SKILL.md is missing from the repo"
        )

    def test_frontmatter_name(self):
        text = self.skill.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^name:\s*apple-design\s*$")

    def test_frontmatter_description(self):
        text = self.skill.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^description:\s*\S+")

    def test_has_real_interface_design_content(self):
        """Guard against a stub: the vendored skill must carry the actual
        Apple-principles content, not just frontmatter."""
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("damping", text)
        self.assertIn("interrupt", text)


if __name__ == "__main__":
    unittest.main()
