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


class InterfaceCheckBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="interface-check-tests-")
        self.ws = pathlib.Path(self._tmp) / "ws"
        self.ws.mkdir()
        self.repo = pathlib.Path(self._tmp) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "t")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "a.dart").write_text("void a() {}\n", encoding="utf-8")
        (self.repo / "src" / "b.dart").write_text("void b() {}\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "base")
        self.base = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()

        self.plan = {
            "feature": "f",
            "tasks": [
                {"id": 1, "touches": ["src/a.dart", "test/a_test.dart"], "depends_on": []},
                {"id": 2, "touches": ["src/b.dart"], "depends_on": ["src/a.dart"]},
            ],
        }
        (self.ws / "plan.json").write_text(json.dumps(self.plan, indent=2), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def run_it(self, task, base=None):
        return subprocess.run(
            [PY, str(SCRIPTS / "interface-check"), str(self.ws), str(task), base or self.base],
            capture_output=True, text=True, cwd=self.repo,
        )


class TestInterfaceCheck(InterfaceCheckBase):
    def test_touching_consumed_interface_emits_change(self):
        (self.repo / "src" / "a.dart").write_text("void a() { z(); }\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "t1")
        r = self.run_it(1)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("consumed by task(s) 2", r.stdout + r.stderr)

    def test_no_cross_task_interface_touched(self):
        (self.repo / "src" / "b.dart").write_text("void b() { y(); }\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "t2")
        r = self.run_it(2)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_missing_plan_is_usage(self):
        (self.ws / "plan.json").unlink()
        r = self.run_it(1)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()