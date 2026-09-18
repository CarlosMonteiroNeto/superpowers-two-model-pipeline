"""Regression module for F1: integrate must refuse to run from a dirty
integration checkout.

The reviewed baseline could emit `git reset --hard` on the batch fallback and
silently delete an unrelated tracked edit. These tests reconstruct disposable
Git repositories and prove the entry guard blocks before any mutation, preserves
the checkout (HEAD, index, bytes, branches, worktrees), and ledgers an
`integration_failed` dirty-worktree reason for every requested task.
"""

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
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True)


def write_stub(directory, name, body):
    p = pathlib.Path(directory) / name
    p.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    if os.name == "nt":
        subprocess.run([BASH, "-c", "chmod +x '{}'".format(p)],
                       capture_output=True)
    else:
        p.chmod(0o755)
    return str(p)


class IntegrateDirtyGuardTest(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="integrate-dirty-"))
        self.repo = self._tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "t")
        (self.repo / "lib").mkdir()
        (self.repo / "lib" / "a.go").write_text("package a\n", encoding="utf-8")
        (self.repo / ".superpowers" / "two-model").mkdir(parents=True)
        (self.repo / ".superpowers" / "two-model" / ".gitignore").write_text(
            "*\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "base")

        self.ws = self.repo / ".superpowers" / "two-model" / "plan"
        self.ws.mkdir(parents=True)
        (self.ws / "plan.json").write_text(
            json.dumps({"feature": "f", "tasks": []}), encoding="utf-8")
        gate = {"ts": "t", "type": "gate", "task": "-", "summary": "go",
                "lang": "go", "test_cmd": "true", "analyze_cmd": "true"}
        (self.ws / "ledger.jsonl").write_text(json.dumps(gate) + "\n",
                                              encoding="utf-8")
        self.stub_dir = self._tmp / "stubs"
        self.stub_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    # --- helpers ---------------------------------------------------------

    def alloc(self, n):
        r = subprocess.run(
            [BASH, str(SCRIPTS / "worktree-alloc"), str(self.ws), str(n)],
            capture_output=True, text=True, cwd=str(self.repo))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def wt(self, n):
        return (self.repo / ".superpowers" / "two-model" / "worktrees"
                / ("task-%d" % n))

    def wt_ws(self, n):
        return self.wt(n) / ".superpowers" / "two-model" / "plan"

    def task_commit(self, n, relpath, content):
        w = self.wt(n)
        p = w / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        git(w, "add", "-A")
        git(w, "commit", "-qm", "task %d" % n)

    def shard_complete(self, n):
        with open(self.wt_ws(n) / "ledger.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": "t", "type": "task_complete",
                                 "task": str(n), "summary": "APPROVED"}) + "\n")

    def ledger(self):
        return [json.loads(line)
                for line in (self.ws / "ledger.jsonl").read_text(
                    encoding="utf-8").splitlines() if line.strip()]

    def entries(self, etype):
        return [e for e in self.ledger() if e.get("type") == etype]

    def head(self):
        return git(self.repo, "rev-parse", "HEAD").stdout.strip()

    def branches(self):
        return git(self.repo, "branch", "--list",
                   "--format=%(refname:short)").stdout

    def staged_blobs(self):
        return git(self.repo, "diff", "--cached", "--binary").stdout

    def run_integrate(self, *args, **env_extra):
        env = dict(os.environ)
        env.update(env_extra)
        return subprocess.run(
            [BASH, str(SCRIPTS / "integrate"), str(self.ws), *map(str, args)],
            capture_output=True, text=True, cwd=str(self.repo), env=env)

    def gate_ok(self):
        return write_stub(self.stub_dir, "gate-ok", "exit 0\n")

    def gate_fail(self):
        return write_stub(self.stub_dir, "gate-fail", "exit 1\n")

    def assert_dirty_failed(self, *tasks):
        fails = self.entries("integration_failed")
        failed_tasks = sorted(str(e["task"]) for e in fails)
        self.assertEqual(failed_tasks, sorted(str(t) for t in tasks), fails)
        for e in fails:
            self.assertIn("dirty", e["summary"])
            self.assertIn("worktree", e["summary"])

    # --- tests -----------------------------------------------------------

    def test_unstaged_tracked_edit_blocks_single_task(self):
        self.alloc(1)
        self.task_commit(1, "lib/task1.go", "package lib\n")
        self.shard_complete(1)
        (self.repo / "lib" / "a.go").write_text(
            "package a // user edit\n", encoding="utf-8")
        head_before = self.head()
        blobs_before = self.staged_blobs()

        r = self.run_integrate(1, RUN_GATES_BIN=self.gate_ok())

        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("dirty", (r.stdout + r.stderr).lower())
        self.assert_dirty_failed(1)
        self.assertEqual(self.head(), head_before)
        self.assertEqual(self.staged_blobs(), blobs_before)
        self.assertEqual(
            (self.repo / "lib" / "a.go").read_text(encoding="utf-8"),
            "package a // user edit\n")
        self.assertNotIn("integrated", [e["type"] for e in self.ledger()])
        self.assertNotIn("worktree_release",
                         [e["type"] for e in self.ledger()])
        self.assertIn("task/1", self.branches())
        self.assertTrue(self.wt(1).exists())

    def test_staged_tracked_change_blocks_and_preserves_index(self):
        self.alloc(1)
        self.task_commit(1, "lib/task1.go", "package lib\n")
        self.shard_complete(1)
        (self.repo / "lib" / "a.go").write_text(
            "package a // staged edit\n", encoding="utf-8")
        git(self.repo, "add", "lib/a.go")
        head_before = self.head()
        blobs_before = self.staged_blobs()
        self.assertNotEqual(blobs_before, "")

        r = self.run_integrate(1, RUN_GATES_BIN=self.gate_ok())

        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assert_dirty_failed(1)
        self.assertEqual(self.head(), head_before)
        self.assertEqual(self.staged_blobs(), blobs_before)
        self.assertNotIn("integrated", [e["type"] for e in self.ledger()])
        self.assertIn("task/1", self.branches())
        self.assertTrue(self.wt(1).exists())

    def test_untracked_nonignored_file_blocks(self):
        self.alloc(1)
        self.task_commit(1, "lib/task1.go", "package lib\n")
        self.shard_complete(1)
        (self.repo / "scratch.txt").write_text("notes\n", encoding="utf-8")
        head_before = self.head()

        r = self.run_integrate(1, RUN_GATES_BIN=self.gate_ok())

        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assert_dirty_failed(1)
        self.assertEqual(self.head(), head_before)
        self.assertTrue((self.repo / "scratch.txt").is_file())
        self.assertNotIn("integrated", [e["type"] for e in self.ledger()])
        self.assertIn("task/1", self.branches())

    def test_ignored_workspace_artifacts_do_not_block(self):
        self.alloc(1)
        self.task_commit(1, "lib/task1.go", "package lib\n")
        self.shard_complete(1)
        porcelain = git(self.repo, "status", "--porcelain").stdout.strip()
        self.assertEqual(porcelain, "")

        r = self.run_integrate(1, RUN_GATES_BIN=self.gate_ok())

        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([str(e["task"]) for e in self.entries("integrated")],
                         ["1"])
        self.assertNotIn("task/1", self.branches())

    def test_status_command_failure_blocks(self):
        """A failing `git status` must block instead of being read as a clean
        checkout. A corrupt index makes status exit nonzero while rev-parse,
        branch, and file assertions keep working."""
        self.alloc(1)
        self.task_commit(1, "lib/task1.go", "package lib\n")
        self.shard_complete(1)
        head_before = self.head()
        index = self.repo / ".git" / "index"
        self.assertTrue(index.is_file())
        index.write_bytes(b"not a valid git index\n")

        r = self.run_integrate(1, RUN_GATES_BIN=self.gate_ok())

        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(self.head(), head_before)
        fails = self.entries("integration_failed")
        self.assertEqual(len(fails), 1, fails)
        self.assertIn("dirty", fails[0]["summary"])
        self.assertNotIn("integrated", [e["type"] for e in self.ledger()])
        self.assertIn("task/1", self.branches())
        self.assertTrue(self.wt(1).exists())

    def test_batch_dirty_does_not_reset_unrelated_user_edit(self):
        """The F1 reproduction: a two-task batch whose gate fails used to
        `git reset --hard` the whole checkout, deleting an unrelated edit."""
        self.alloc(1)
        self.alloc(2)
        self.task_commit(1, "lib/task1.go", "package lib\n")
        self.task_commit(2, "lib/task2.go", "package lib\n")
        self.shard_complete(1)
        self.shard_complete(2)
        (self.repo / "lib" / "a.go").write_text(
            "package a // precious user edit\n", encoding="utf-8")
        head_before = self.head()

        r = self.run_integrate(1, 2, RUN_GATES_BIN=self.gate_fail())

        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assert_dirty_failed(1, 2)
        self.assertEqual(self.head(), head_before)
        self.assertEqual(
            (self.repo / "lib" / "a.go").read_text(encoding="utf-8"),
            "package a // precious user edit\n")
        self.assertFalse((self.repo / "lib" / "task1.go").exists())
        self.assertFalse((self.repo / "lib" / "task2.go").exists())
        self.assertNotIn("integrated", [e["type"] for e in self.ledger()])
        self.assertIn("task/1", self.branches())
        self.assertIn("task/2", self.branches())
        self.assertTrue(self.wt(1).exists())
        self.assertTrue(self.wt(2).exists())

    def test_approved_noop_dirty_checkout_blocks(self):
        self.alloc(1)
        self.shard_complete(1)
        (self.repo / "scratch.txt").write_text("notes\n", encoding="utf-8")
        head_before = self.head()

        r = self.run_integrate(1, RUN_GATES_BIN=self.gate_fail())

        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assert_dirty_failed(1)
        self.assertEqual(self.head(), head_before)
        self.assertNotIn("integrated", [e["type"] for e in self.ledger()])
        self.assertNotIn("worktree_release",
                         [e["type"] for e in self.ledger()])
        self.assertIn("task/1", self.branches())
        self.assertTrue(self.wt(1).exists())

    def test_clean_checkout_still_integrates_good_task_when_sibling_gate_red(self):
        """The guard is an entry check, not a behavior change: a clean batch
        whose gate fails still bisects and lands the independently valid task."""
        self.alloc(1)
        self.alloc(2)
        self.task_commit(1, "lib/task1.go", "package lib\n")
        self.task_commit(2, "lib/task2.go", "package lib\n")
        self.shard_complete(1)
        self.shard_complete(2)
        counter = self._tmp / "gate-count"
        stub = write_stub(
            self.stub_dir, "gate-task2-red",
            "n=$(cat \"%s\" 2>/dev/null || echo 0)\n"
            "n=$((n+1))\n"
            "printf '%%s' \"$n\" > \"%s\"\n"
            "[ -f lib/task2.go ] && exit 1\n"
            "exit 0\n" % (counter, counter))

        r = self.run_integrate(1, 2, RUN_GATES_BIN=stub)

        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        pairs = [(e["type"], str(e["task"])) for e in self.ledger()]
        self.assertIn(("integrated", "1"), pairs)
        self.assertIn(("integration_failed", "2"), pairs)
        self.assertTrue((self.repo / "lib" / "task1.go").is_file())
        self.assertNotIn("task/1", self.branches())
        self.assertIn("task/2", self.branches())

    def test_usage_no_args(self):
        r = subprocess.run([BASH, str(SCRIPTS / "integrate")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
