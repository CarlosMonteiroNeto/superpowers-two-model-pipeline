"""Controller-owned R3.3 corrective family/session safety tests."""
import importlib.util
import pathlib
import json
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"


class CorrectiveFamilyTests(unittest.TestCase):
    def test_task_run_does_not_resume_operator_outside_recorded_family(self):
        source = (SCRIPTS / "task-run").read_text(encoding="utf-8")
        self.assertIn("task_family", source)
        self.assertIn("family", source.lower())
        self.assertNotIn("--continue-director", source)

    def test_new_codex_corrective_task_does_not_forward_parent_session(self):
        source = (SCRIPTS / "task-run").read_text(encoding="utf-8")
        self.assertIn('if [ "${PIPELINE_BACKEND:-opencode}" != codex ] && [ -n "$orig_session" ]; then', source)

    def test_family_resume_identity_accepts_only_actual_descendants(self):
        helper=SCRIPTS/"family_identity.py"
        plan={"tasks":[{"id":1,"corrects":None},{"id":2,"corrects":1},{"id":3,"corrects":2},{"id":4,"corrects":None}]}
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/"plan.json"; path.write_text(json.dumps(plan),encoding="utf-8")
            good=subprocess.run(["python",str(helper),"--is-descendant",str(path),"3","1"],capture_output=True)
            unrelated=subprocess.run(["python",str(helper),"--is-descendant",str(path),"4","1"],capture_output=True)
            self.assertEqual(good.returncode,0)
            self.assertEqual(unrelated.returncode,1)

    def test_director_prompt_requests_proposals_not_direct_plan_or_ledger_edits(self):
        prompt = (ROOT / "skills" / "two-model-sdd-pipeline" / "task-generator-prompt.md").read_text(encoding="utf-8").lower()
        self.assertIn("proposal", prompt)
        self.assertTrue("read-only" in prompt or "read only" in prompt)
        self.assertTrue("plan" in prompt and "ledger" in prompt)
