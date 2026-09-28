"""R3.6 Codex entry documentation stays aligned with the canonical README."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
README = ROOT / "README.md"
RUNTIME_GUIDE = ROOT / "skills" / "two-model-sdd-pipeline" / "references" / "codex-runtime.md"
CODEX_TOOLS = ROOT / "skills" / "using-superpowers" / "references" / "codex-tools.md"


class CodexSkillEntryContractTests(unittest.TestCase):
    def test_canonical_readme_links_the_codex_runtime_guide(self):
        self.assertTrue(RUNTIME_GUIDE.is_file(), "R3.6 requires a packaged Codex runtime guide")
        readme = README.read_text(encoding="utf-8")
        self.assertIn("references/codex-runtime.md", readme)
        self.assertIn("single canonical", readme)
        self.assertFalse((ROOT / "docs" / "README.codex-pipeline.md").exists(),
                         "the confirmed single-README policy forbids a second manual")

    def test_codex_runtime_guide_covers_both_launchers_and_boundaries(self):
        guide = RUNTIME_GUIDE.read_text(encoding="utf-8")
        for required in (
            "run-codex-pipeline", "run-codex-pipeline.ps1", "--publication",
            "model_reasoning_effort", "local", "pull_request", "Codex CLI",
            "not a live support claim", "R4",
        ):
            with self.subTest(required=required):
                self.assertIn(required, guide)

    def test_codex_tools_reference_does_not_claim_pipeline_is_unwired(self):
        reference = CODEX_TOOLS.read_text(encoding="utf-8")
        self.assertIn("run-codex-pipeline", reference)
        self.assertIn("acceptance matrix", reference)
        self.assertNotIn("pipeline is not wired yet", reference)


if __name__ == "__main__":
    unittest.main()
