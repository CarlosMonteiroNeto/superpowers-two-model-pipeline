import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
PY = sys.executable


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)


class KeepDiscardBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="keep-discard-tests-")
        self.ws = pathlib.Path(self._tmp) / "ws"
        self.ws.mkdir()
        self.repo = pathlib.Path(self._tmp) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "t")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "a.dart").write_text("void a() {}\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "base")

        self.plan = {
            "feature": "f",
            "tasks": [
                {"id": 3, "title": "t", "summary": "s", "touches": ["src/a.dart"], "depends_on": []}
            ],
        }
        (self.ws / "plan.json").write_text(json.dumps(self.plan, indent=2), encoding="utf-8")

        # RED tests committed at HEAD (separate test: commit), partial work is uncommitted.
        (self.repo / "test").mkdir()
        (self.repo / "test" / "task_3_test.dart").write_text("test\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "test: task 3 red")

        # The brief must exist (the gate checks for the artifact; it does not
        # parse RED-TESTS content - scope comes from plan.json touches only).
        (self.ws / "task-3-brief.md").write_text(
            "RED-TESTS:\nplaceholder -> placeholder\n",
            encoding="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def run_it(self):
        return subprocess.run(
            [PY, str(SCRIPTS / "keep-discard"), str(self.ws), "3"],
            capture_output=True, text=True, cwd=self.repo,
        )


class TestKeepDiscard(KeepDiscardBase):
    def test_no_partial_work_discards_with_distinct_code(self):
        """Empty work is DISCARD with its own code (3): the callers must be
        able to tell 'nothing to commit' from a real scope violation."""
        r = self.run_it()
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)

    def test_in_scope_work_keeps(self):
        (self.repo / "src" / "a.dart").write_text("void a() { x(); }\n", encoding="utf-8")
        r = self.run_it()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_in_scope_impl_plus_new_test_keeps(self):
        """H3: tests are `changed - touches`, so every honest task writes a
        test file outside touches. A newly authored test must not DISCARD."""
        (self.repo / "src" / "a.dart").write_text("void a() { x(); }\n", encoding="utf-8")
        (self.repo / "test" / "task_3_extra_test.dart").write_text(
            "test\n", encoding="utf-8")
        r = self.run_it()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_out_of_scope_work_discards(self):
        (self.repo / "other.dart").write_text("void other() {}\n", encoding="utf-8")
        r = self.run_it()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("other.dart", r.stdout + r.stderr)

    def test_tampered_test_file_discards(self):
        (self.repo / "test" / "task_3_test.dart").write_text("tampered\n", encoding="utf-8")
        r = self.run_it()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_generated_build_output_is_exempt(self):
        """C3: codegen output is derived, not authored scope. A whole-project
        generator run rewrites every drifted .freezed.dart/.g.dart; those must
        not DISCARD a task that legitimately changed a generated source."""
        (self.repo / "src" / "a.dart").write_text("void a() { x(); }\n", encoding="utf-8")
        (self.repo / "src" / "a.freezed.dart").write_text("// regen\n", encoding="utf-8")
        (self.repo / "src" / "b.g.dart").write_text("// regen\n", encoding="utf-8")
        r = self.run_it()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_committed_generated_output_is_exempt(self):
        """A regenerated committed generated file is exempt too - the drift is
        the generator version, not the task's authored scope."""
        (self.repo / "src" / "c.g.dart").write_text("// v1\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "add generated")
        (self.repo / "src" / "c.g.dart").write_text("// v2\n", encoding="utf-8")
        r = self.run_it()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_tracked_plan_change_is_exempt(self):
        """C3: the tracked plan is pipeline state the diretor edits during
        arbitration; it is never a task's authored scope."""
        d = self.repo / "docs" / "superpowers" / "plans"
        d.mkdir(parents=True, exist_ok=True)
        (d / "plan.json").write_text('{"feature":"f"}\n', encoding="utf-8")
        r = self.run_it()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_missing_plan_is_usage(self):
        (self.ws / "plan.json").unlink()
        r = self.run_it()
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()