import pathlib
import unittest


REPO = pathlib.Path(__file__).resolve().parents[3]


class FlutterReviewPathTests(unittest.TestCase):
    def test_flutter_gate_uses_shared_review_package_and_keeps_reviewer(self):
        text = (REPO / "skills" / "flutter-app-pipeline" / "scripts" / "green-gate").read_text(encoding="utf-8")
        self.assertIn("two-model-sdd-pipeline/scripts/review-package", text)
        self.assertIn('"$DISPATCH_BIN" --agent two-model-reviewer', text)
        self.assertIn('--prompt-file "$pkg"', text)

    def test_flutter_skill_documents_mandatory_site4_review(self):
        text = (REPO / "skills" / "flutter-app-pipeline" / "SKILL.md").read_text(encoding="utf-8").lower()
        self.assertIn("review-package", text)
        self.assertIn("focused_review", text)
        self.assertIn("standard_review", text)
        self.assertIn("always runs", text)


if __name__ == "__main__":
    unittest.main()
