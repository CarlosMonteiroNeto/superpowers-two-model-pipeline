"""Controller-owned Task 6 cross-backend runtime contract documentation."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]


class BackendContractParityTests(unittest.TestCase):
    def test_codex_subagent_guide_matches_native_exec_resume_contract(self):
        guide = ROOT / "skills" / "using-superpowers" / "references" / "codex-tools.md"
        self.assertTrue(guide.is_file())
        text = guide.read_text(encoding="utf-8").casefold()
        self.assertIn("codex exec", text)
        self.assertIn("exec resume", text)
        self.assertIn("session id", text)
        self.assertIn("not", text)

    def test_readme_distinguishes_worker_backend_from_unfinished_r3_launcher(self):
        text = " ".join((ROOT / "README.md").read_text(encoding="utf-8").casefold().split())
        self.assertIn("codex worker", text)
        self.assertIn("r3", text)
        self.assertIn("no silent fallback", text)
        self.assertNotIn("r1 does not yet supply a working codex pipeline", text)

    def test_readme_scopes_continue_session_syntax_to_opencode(self):
        text = " ".join((ROOT / "README.md").read_text(encoding="utf-8").casefold().split())
        self.assertIn("opencode within-task resume via `--continue --session`", text)
        self.assertIn("codex resume uses explicit identity-checked session ids", text)
        self.assertIn("legacy opencode headless launcher", text)

    def test_compatibility_matrix_disclaims_live_permission_validation(self):
        guide = ROOT / "skills" / "two-model-sdd-pipeline" / "references" / "worker-runtime.md"
        self.assertTrue(guide.is_file())
        text = guide.read_text(encoding="utf-8").casefold()
        self.assertIn("fixture", text)
        self.assertIn("permission", text)
        self.assertIn("does not prove", text)
