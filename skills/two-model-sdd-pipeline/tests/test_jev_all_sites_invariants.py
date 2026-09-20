import pathlib
import unittest


REPO = pathlib.Path(__file__).resolve().parents[3]
GENERIC = REPO / "skills" / "two-model-sdd-pipeline"
FLUTTER = REPO / "skills" / "flutter-app-pipeline"


class Site4AllSitesInvariantTests(unittest.TestCase):
    def test_review_package_is_the_single_shared_guidance_boundary(self):
        package = (GENERIC / "scripts" / "review-package").read_text(encoding="utf-8")
        self.assertIn("review-guidance", package)
        self.assertEqual(package.count("review-guidance"), 1)
        self.assertIn("two-model-reviewer", (GENERIC / "scripts" / "coder-gate").read_text(encoding="utf-8"))
        green = (FLUTTER / "scripts" / "green-gate").read_text(encoding="utf-8")
        self.assertIn("two-model-sdd-pipeline/scripts/review-package", green)
        self.assertIn("two-model-reviewer", green)

    def test_review_dispatch_and_verdict_pipeline_are_retained(self):
        for path in (GENERIC / "scripts" / "coder-gate", FLUTTER / "scripts" / "green-gate"):
            text = path.read_text(encoding="utf-8")
            self.assertIn("--agent two-model-reviewer", text)
            self.assertIn("--prompt-file", text)
        parse = (GENERIC / "scripts" / "parse-review").read_text(encoding="utf-8")
        self.assertIn("parse_review", parse)

    def test_advisory_docs_forbid_bypass_and_prediction(self):
        prompt = (GENERIC / "reviewer-prompt.md").read_text(encoding="utf-8").lower()
        self.assertIn("full brief", prompt)
        self.assertIn("full diff", prompt)
        self.assertIn("sole", prompt)
        self.assertIn("no model/agent substitution", prompt)
        self.assertIn("no predicted verdict", prompt)


if __name__ == "__main__":
    unittest.main()
