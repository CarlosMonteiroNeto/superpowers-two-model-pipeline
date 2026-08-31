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
    def test_no_partial_work_discards(self):
        r = self.run_it()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_in_scope_work_keeps(self):
        (self.repo / "src" / "a.dart").write_text("void a() { x(); }\n", encoding="utf-8")
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

    def test_missing_plan_is_usage(self):
        (self.ws / "plan.json").unlink()
        r = self.run_it()
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()