import pathlib
import unittest

SKILLS = pathlib.Path(__file__).resolve().parent.parent.parent
REPO = SKILLS.parent


class TestParseReviewWiredInDocs(unittest.TestCase):
    def test_readme_documents_parse_review(self):
        text = (REPO / "README.md").read_text(encoding="utf-8")
        self.assertIn("parse-review", text)

    def test_readme_txt_documents_parse_review(self):
        text = (REPO / "README.txt").read_text(encoding="utf-8")
        self.assertIn("parse-review", text)

    def test_readme_is_single_source(self):
        """README.md is the single canonical reference; the retired
        duplicate manual must be gone."""
        self.assertTrue((REPO / "README.md").is_file())
        self.assertFalse((REPO / "README-LLM.md").exists())
        text = (REPO / "README.md").read_text(encoding="utf-8")
        self.assertIn("single canonical", text)

    def test_skill_documents_parse_review(self):
        text = (SKILLS / "two-model-sdd-pipeline" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("parse-review", text)

    def test_skill_owner_consistent(self):
        """SKILL.md must not claim Script A runs parse-review (B does)."""
        text = (SKILLS / "two-model-sdd-pipeline" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("Script A after D's log lands", text)
        self.assertNotIn("(B does not run it)", text)

    def test_corrective_task_convention_documented(self):
        """Correctives are new plan tasks (`corrects: N`), not corrective
        brief files: Agente diretor appends the task, brief-scaffold builds
        the brief, the same operador session resumes."""
        skill = (SKILLS / "two-model-sdd-pipeline" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("corrects", skill)
        self.assertIn("same operador session", skill.lower())

    def test_r4_graph_lifecycle_documents_private_cache_and_identity_verification(self):
        skill = (SKILLS / "two-model-sdd-pipeline" / "SKILL.md").read_text(encoding="utf-8")
        markdown = (REPO / "README.md").read_text(encoding="utf-8")
        self.assertIn("private external run cache", " ".join(skill.lower().split()))
        self.assertIn("no graph context", markdown.lower())
        self.assertIn("recapturing input identities only", markdown.lower())
        self.assertIn("not skipped", skill.lower())
        self.assertIn("closing gates", skill.lower())
        self.assertNotIn("graphify update", skill.lower())
        self.assertNotIn("graphify update", markdown.lower())

if __name__ == "__main__":
    unittest.main()
