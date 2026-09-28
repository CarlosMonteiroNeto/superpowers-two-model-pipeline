import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import ctypes

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"


def run_scaffold(ws, task, cwd=None):
    env = dict(os.environ)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "brief-scaffold"), str(ws), str(task)],
        capture_output=True, text=True, env=env, cwd=cwd,
    )


def plan_with(task):
    return {
        "feature": "t",
        "tasks": [task],
    }


# Complete task per design §3: acceptance-driven, no expected_red.
FULL_TASK = {
    "id": 3,
    "title": "Add export",
    "summary": "Export invoices to CSV.",
    "spec_refs": ["§2.1", "§2.4"],
    "touches": ["lib/export.dart"],
    "depends_on": [1],
    "acceptance": ["CSV has header row", "rows match invoices"],
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
    def test_brief_uses_worktree_relative_workspace_for_runner_commands(self):
        project = self._tmp / "project with spaces"
        workspace = project / ".superpowers" / "two-model" / "acceptance"
        workspace.mkdir(parents=True)
        (workspace / "plan.json").write_text(json.dumps(plan_with(FULL_TASK)), encoding="utf-8")

        result = run_scaffold(workspace, 3, cwd=project)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        text = (workspace / "task-3-brief.md").read_text(encoding="utf-8")
        self.assertIn("bash ", text)
        self.assertIn("scoped-run .superpowers/two-model/acceptance 3 red", text)
        self.assertNotIn(str(workspace).replace("\\", "/"), text)

    @unittest.skipUnless(os.name == "nt", "Windows 8.3 path alias behavior")
    def test_brief_normalizes_short_workspace_alias_before_relative_path_check(self):
        project = self._tmp / "project with spaces"
        workspace = project / ".superpowers" / "two-model" / "acceptance"
        workspace.mkdir(parents=True)
        (workspace / "plan.json").write_text(json.dumps(plan_with(FULL_TASK)), encoding="utf-8")
        short = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetShortPathNameW(
            str(workspace), short, len(short))
        if not length or short.value == str(workspace):
            self.skipTest("filesystem does not provide a distinct 8.3 alias")

        result = run_scaffold(short.value, 3, cwd=project)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        text = (workspace / "task-3-brief.md").read_text(encoding="utf-8")
        self.assertIn("scoped-run .superpowers/two-model/acceptance 3 red", text)

    def test_task_without_expected_red_scaffolds(self):
        """brief-scaffold must not require expected_red."""
        self.write_plan(plan_with(FULL_TASK))
        r = run_scaffold(self.ws, 3)
        self.assertEqual(
            r.returncode, 0,
            "brief-scaffold must not require expected_red: "
            + r.stdout + r.stderr,
        )
        text = (self.ws / "task-3-brief.md").read_text(encoding="utf-8")
        self.assertIn("Add export", text)
        self.assertIn("Export invoices to CSV.", text)
        self.assertIn("lib/export.dart", text)

    def test_brief_lists_acceptance_and_spec_refs(self):
        self.write_plan(plan_with(FULL_TASK))
        r = run_scaffold(self.ws, 3)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = (self.ws / "task-3-brief.md").read_text(encoding="utf-8")
        self.assertIn("## Acceptance", text)
        self.assertIn("CSV has header row", text)
        self.assertIn("rows match invoices", text)
        self.assertIn("## Spec refs", text)
        self.assertIn("§2.1", text)
        self.assertIn("§2.4", text)

    def test_brief_has_no_expected_failure_section(self):
        self.write_plan(plan_with(FULL_TASK))
        r = run_scaffold(self.ws, 3)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = (self.ws / "task-3-brief.md").read_text(encoding="utf-8")
        self.assertNotIn("Expected failure", text)
        self.assertNotIn("expected_red", text)

    def test_brief_requires_machine_readable_red_evidence(self):
        """The operador must save the RED run in the runner's machine-readable
        format so red-form-check can classify it (design §4)."""
        self.write_plan(plan_with(FULL_TASK))
        r = run_scaffold(self.ws, 3)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = (self.ws / "task-3-brief.md").read_text(encoding="utf-8")
        self.assertIn("machine-readable", text)
        self.assertIn("task-3-red.txt", text)

    def test_brief_drops_the_reason_declaration_step(self):
        """The declare/confirm step was dead work - no script read the
        declaration. The brief keeps the machine-readable evidence
        requirement, which red-form-check does read."""
        self.write_plan(plan_with(FULL_TASK))
        r = run_scaffold(self.ws, 3)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = (self.ws / "task-3-brief.md").read_text(encoding="utf-8")
        self.assertIn("task-3-red.txt", text)
        lower = text.lower()
        self.assertNotIn("declare", lower)
        self.assertNotIn("declaration", lower)
        self.assertNotIn("confirm", lower)

    def test_brief_offers_the_backend_neutral_scoped_runner(self):
        """Worker briefs use the shared scoped runner, not the Flutter-only
        runner; task-scoped execution still writes RED evidence."""
        self.write_plan(plan_with(FULL_TASK))
        r = run_scaffold(self.ws, 3)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = (self.ws / "task-3-brief.md").read_text(encoding="utf-8")
        self.assertIn("scoped-run", text)
        self.assertIn("3 red", text)
        self.assertIn("red <test-file...>", text)
        self.assertIn("task-3-red.txt", text)
        self.assertNotIn("flutter-app-pipeline", text)
        self.assertNotIn("rtk-run", text)
        lower = text.lower()
        self.assertIn("optional", lower)
        self.assertNotIn("do not run the full test suite", lower)

    def test_legacy_expected_red_is_ignored(self):
        """Bootstrap: this branch's tasks still carry expected_red; it must
        scaffold without error and never leak into the brief."""
        task = dict(FULL_TASK, expected_red="MissingExport")
        self.write_plan(plan_with(task))
        r = run_scaffold(self.ws, 3)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = (self.ws / "task-3-brief.md").read_text(encoding="utf-8")
        self.assertNotIn("MissingExport", text)
        self.assertNotIn("expected_red", text)

    def test_test_like_touches_is_usage(self):
        task = dict(FULL_TASK, touches=["tests/test_export.py"])
        self.write_plan(plan_with(task))
        r = run_scaffold(self.ws, 3)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("test files", r.stderr)
        self.assertFalse((self.ws / "task-3-brief.md").exists())

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

    def test_task_missing_acceptance_is_usage(self):
        thin = {"id": 3, "title": "Add export", "summary": "x"}
        self.write_plan(plan_with(thin))
        r = run_scaffold(self.ws, 3)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("acceptance", r.stderr)
        self.assertNotIn("expected_red", r.stderr)

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
