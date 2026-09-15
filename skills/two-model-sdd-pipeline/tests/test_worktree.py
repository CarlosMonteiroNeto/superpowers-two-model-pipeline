import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
if os.name == "nt":
    _gb = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
    BASH = str(_gb) if _gb.exists() else "bash"
else:
    BASH = "bash"


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)


class WorktreeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="worktree-"))
        self.repo = self._tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "t")
        (self.repo / "lib").mkdir()
        (self.repo / "lib" / "a.go").write_text("package a\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "base")
        self.ws = self.repo / ".superpowers" / "two-model" / "plan"
        self.ws.mkdir(parents=True)
        (self.repo / ".superpowers" / "two-model" / ".gitignore").write_text("*\n", encoding="utf-8")
        (self.ws / "plan.json").write_text(json.dumps({"feature": "f", "tasks": []}),
                                           encoding="utf-8")
        gate = {"ts": "t", "type": "gate", "task": "-", "summary": "go", "lang": "go",
                "test_cmd": "true", "analyze_cmd": "true"}
        (self.ws / "ledger.jsonl").write_text(json.dumps(gate) + "\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def run_it(self, script, *args):
        return subprocess.run([BASH, str(SCRIPTS / script), str(self.ws), *map(str, args)],
                              capture_output=True, text=True, cwd=self.repo)

    def test_alloc_creates_worktree_branch_and_workspace(self):
        r = self.run_it("worktree-alloc", 3)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        wt = self.repo / ".superpowers" / "two-model" / "worktrees" / "task-3"
        self.assertTrue((wt / "lib" / "a.go").is_file())
        self.assertIn("task/3", subprocess.run(
            ["git", "-C", str(self.repo), "branch"], capture_output=True,
            text=True).stdout)
        wt_ws = wt / ".superpowers" / "two-model" / "plan"
        self.assertTrue((wt_ws / "plan.json").is_file())
        self.assertIn('"type": "gate"', (wt_ws / "ledger.jsonl").read_text(encoding="utf-8"))
        self.assertIn("worktree_alloc",
                      (self.ws / "ledger.jsonl").read_text(encoding="utf-8"))

    def test_alloc_leaves_integration_tree_clean(self):
        self.run_it("worktree-alloc", 3)
        out = subprocess.run(["git", "-C", str(self.repo), "status", "--porcelain"],
                             capture_output=True, text=True).stdout
        self.assertEqual(out.strip(), "")

    def test_second_alloc_is_one(self):
        self.run_it("worktree-alloc", 3)
        self.assertEqual(self.run_it("worktree-alloc", 3).returncode, 1)

    def test_usage(self):
        r = subprocess.run([BASH, str(SCRIPTS / "worktree-alloc")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_release_after_merge_removes_branch_and_tree(self):
        self.run_it("worktree-alloc", 3)
        wt = self.repo / ".superpowers" / "two-model" / "worktrees" / "task-3"
        (wt / "lib" / "a.go").write_text("package a // x\n", encoding="utf-8")
        git(wt, "add", "-A")
        git(wt, "commit", "-qm", "task3")
        git(self.repo, "merge", "--no-ff", "-m", "merge 3", "task/3")
        r = self.run_it("worktree-release", 3)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(wt.exists())
        branches = subprocess.run(["git", "-C", str(self.repo), "branch"],
                                  capture_output=True, text=True).stdout
        self.assertNotIn("task/3", branches)
        self.assertIn("worktree_release",
                      (self.ws / "ledger.jsonl").read_text(encoding="utf-8"))

    def test_release_unmerged_is_one_and_keeps_tree(self):
        self.run_it("worktree-alloc", 3)
        r = self.run_it("worktree-release", 3)
        self.assertEqual(r.returncode, 1)
        self.assertTrue((self.repo / ".superpowers" / "two-model" / "worktrees"
                         / "task-3").exists())


if __name__ == "__main__":
    unittest.main()
