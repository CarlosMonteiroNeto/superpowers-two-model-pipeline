import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"


def run_scaffold(ws, task):
    env = dict(os.environ)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "brief-scaffold"), str(ws), str(task)],
        capture_output=True, text=True, env=env,
    )


def plan_with(task):
    return {
        "feature": "t",
        "tasks": [task],
    }


FULL_TASK = {
    "id": 3,
    "title": "Add export",
    "summary": "Export invoices to CSV.",
    "spec_refs": ["§2.1", "§2.4"],
    "touches": ["lib/export.dart"],
    "depends_on": [1],
    "acceptance": ["CSV has header row", "rows match invoices"],
    "expected_red": "MissingExport",
}


class BriefScaffoldTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="brief-scaffold-"))
        self.ws = self._tmp / "ws"
        self.ws.mkdir()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def write_plan(self, plan):
        (self.ws / "plan.json").write_text(json.dumps(plan), encoding="utf-8")


class TestBriefScaffold(BriefScaffoldTestBase):
    def test_scaffold_writes_brief_from_plan(self):
        self.write_plan(plan_with(FULL_TASK))
        r = run_scaffold(self.ws, 3)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = (self.ws / "task-3-brief.md").read_text(encoding="utf-8")
        self.assertIn("Add export", text)
        self.assertIn("Export invoices to CSV.", text)
        self.assertIn("lib/export.dart", text)
        self.assertIn("CSV has header row", text)
        self.assertIn("MissingExport", text)
        self.assertIn("writing-good-tests.md", text)
        self.assertIn("§2.1", text)

    def test_brief_names_red_evidence_file(self):
        """The brief tells the operador where to save the RED run output so
        coder-gate can verify the expected failure (coder-owned RED)."""
        self.write_plan(plan_with(FULL_TASK))
        r = run_scaffold(self.ws, 3)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = (self.ws / "task-3-brief.md").read_text(encoding="utf-8")
        self.assertIn("task-3-red.txt", text)
        self.assertIn("run", text.lower())

    def test_missing_spec_refs_omits_section(self):
        task = dict(FULL_TASK)
        del task["spec_refs"]
        self.write_plan(plan_with(task))
        r = run_scaffold(self.ws, 3)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = (self.ws / "task-3-brief.md").read_text(encoding="utf-8")
        self.assertNotIn("§2.1", text)

    def test_scaffold_overwrites_transient_brief(self):
        self.write_plan(plan_with(FULL_TASK))
        (self.ws / "task-3-brief.md").write_text("stale\n", encoding="utf-8")
        r = run_scaffold(self.ws, 3)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("stale", (self.ws / "task-3-brief.md").read_text(encoding="utf-8"))

    def test_missing_task_is_usage(self):
        self.write_plan(plan_with(FULL_TASK))
        r = run_scaffold(self.ws, 99)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertFalse((self.ws / "task-99-brief.md").exists())

    def test_task_missing_fields_is_usage(self):
        thin = {"id": 3, "title": "Add export", "summary": "x"}
        self.write_plan(plan_with(thin))
        r = run_scaffold(self.ws, 3)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("acceptance", r.stderr)
        self.assertIn("expected_red", r.stderr)

    def test_missing_plan_is_violation(self):
        r = run_scaffold(self.ws, 3)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_bad_args_is_usage(self):
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "brief-scaffold")],
            capture_output=True, text=True, env=dict(os.environ),
        )
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
