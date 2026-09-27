"""Controller-owned R3.3 corrective family/session safety tests."""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"


class CorrectiveFamilyTests(unittest.TestCase):
    def test_task_run_does_not_resume_operator_outside_recorded_family(self):
        source = (SCRIPTS / "task-run").read_text(encoding="utf-8")
        self.assertIn("task_family", source)
        self.assertIn("family", source.lower())
        self.assertNotIn("--continue-director", source)

    def test_director_prompt_requests_proposals_not_direct_plan_or_ledger_edits(self):
        prompt = (SCRIPTS / "director_prompt.py").read_text(encoding="utf-8").lower()
        self.assertIn("proposal", prompt)
        self.assertTrue("read-only" in prompt or "read only" in prompt)
        self.assertTrue("plan" in prompt and "ledger" in prompt)

