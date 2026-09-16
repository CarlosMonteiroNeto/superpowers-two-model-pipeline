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


class IntegrateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="integrate-"))
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

    def shard_append(self, n, entry):
        with open(self.wt_ws(n) / "ledger.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    def shard_complete(self, n):
        # Approval evidence: integrate only merges a task whose shard holds
        # `task_complete` (coder-gate commits before the revisor runs, so a
        # committed-but-unapproved shard must never be merged).
        self.shard_append(n, {"ts": "t", "type": "task_complete",
                              "task": str(n), "summary": "APPROVED"})

    def ledger(self):
        return [json.loads(line)
                for line in (self.ws / "ledger.jsonl").read_text(
                    encoding="utf-8").splitlines() if line.strip()]

    def entries(self, etype):
        return [e for e in self.ledger() if e.get("type") == etype]

    def head(self):
        return git(self.repo, "rev-parse", "HEAD").stdout.strip()

    def task_tree(self, n):
        return git(self.repo, "rev-parse", "task/%d^{tree}" % n).stdout.strip()

    def make_flutter_gate(self):
        gate = {"ts": "t", "type": "gate", "task": "-", "summary": "go",
                "lang": "flutter", "test_cmd": "flutter test",
                "analyze_cmd": "flutter analyze"}
        rest = [line for line in (self.ws / "ledger.jsonl").read_text(
                    encoding="utf-8").splitlines()
                if line.strip() and not json.loads(line).get("type") == "gate"]
        (self.ws / "ledger.jsonl").write_text(
            json.dumps(gate) + "\n" + "\n".join(rest) + "\n", encoding="utf-8")

    def branches(self):
        return git(self.repo, "branch", "--list",
                   "--format=%(refname:short)").stdout

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

    # --- tests -----------------------------------------------------------

    def test_clean_merge_integrates_branch_and_shard(self):
        self.alloc(1)
        self.task_commit(1, "lib/task1.go", "package lib\n")
        self.shard_complete(1)
        self.shard_append(1, {"ts": "t", "type": "review_outcome", "task": "1",
                              "summary": "APPROVED", "findings": "0"})
        r = self.run_integrate(1, RUN_GATES_BIN=self.gate_ok())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("INTEGRATE: wave integrated", r.stdout)
        integrated = self.entries("integrated")
        self.assertEqual(len(integrated), 1, integrated)
        self.assertEqual(str(integrated[0]["task"]), "1")
        self.assertTrue(integrated[0].get("commits"), integrated)
        # the shard's entry was folded into the integration ledger
        shard_types = [(e["type"], str(e["task"])) for e in self.ledger()]
        self.assertIn(("review_outcome", "1"), shard_types)
        # branch + worktree released
        self.assertNotIn("task/1", self.branches())
        self.assertFalse(self.wt(1).exists())
        self.assertTrue((self.repo / "lib" / "task1.go").is_file())

    def test_unapproved_shard_is_not_merged_or_released(self):
        """Critical: coder-gate commits BEFORE the revisor runs, so a shard
        without `task_complete` is a committed-but-unapproved task. integrate
        must ledger `integration_failed N not approved`, leave the integration
        HEAD untouched, and NOT release the worktree (the only debug copy)."""
        self.alloc(1)
        self.task_commit(1, "lib/task1.go", "package lib\n")
        head_before = self.head()
        r = self.run_integrate(1, RUN_GATES_BIN=self.gate_ok())
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        fails = self.entries("integration_failed")
        self.assertEqual(len(fails), 1, fails)
        self.assertEqual(str(fails[0]["task"]), "1")
        self.assertIn("not approved", fails[0]["summary"])
        self.assertEqual(self.head(), head_before)
        self.assertNotIn("integrated", [e["type"] for e in self.ledger()])
        self.assertNotIn("worktree_release", [e["type"] for e in self.ledger()])
        self.assertFalse((self.repo / "lib" / "task1.go").exists())
        self.assertIn("task/1", self.branches())
        self.assertTrue(self.wt(1).exists())

    def test_approved_shard_still_integrates(self):
        """The approval precheck must not block the happy path: a shard with
        `task_complete` merges, is ledgered `integrated`, and is released."""
        self.alloc(1)
        self.task_commit(1, "lib/task1.go", "package lib\n")
        self.shard_complete(1)
        r = self.run_integrate(1, RUN_GATES_BIN=self.gate_ok())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("INTEGRATE: wave integrated", r.stdout)
        self.assertEqual([str(e["task"]) for e in self.entries("integrated")],
                         ["1"])
        self.assertIn("task_complete",
                      [e["type"] for e in self.ledger()])
        self.assertNotIn("task/1", self.branches())
        self.assertTrue((self.repo / "lib" / "task1.go").is_file())

    def test_conflict_signals_and_leaves_head_and_branch(self):
        self.alloc(1)
        (self.repo / "lib" / "a.go").write_text(
            "package a // integration\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "integration edit")
        head_before = self.head()
        self.task_commit(1, "lib/a.go", "package a // task1\n")
        self.shard_complete(1)
        r = self.run_integrate(1, RUN_GATES_BIN=self.gate_ok())
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        fails = self.entries("integration_failed")
        self.assertEqual(len(fails), 1, fails)
        self.assertEqual(str(fails[0]["task"]), "1")
        self.assertIn("conflict", fails[0]["summary"])
        self.assertEqual(self.head(), head_before)
        self.assertIn("task/1", self.branches())
        self.assertTrue(self.wt(1).exists())
        self.assertEqual(
            (self.repo / "lib" / "a.go").read_text(encoding="utf-8"),
            "package a // integration\n")

    def test_conflict_then_second_clean_task_integrates(self):
        self.alloc(1)
        self.alloc(2)
        (self.repo / "lib" / "a.go").write_text(
            "package a // integration\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "integration edit")
        self.task_commit(1, "lib/a.go", "package a // task1\n")
        self.task_commit(2, "lib/task2.go", "package lib\n")
        self.shard_complete(1)
        self.shard_complete(2)
        r = self.run_integrate(1, 2, RUN_GATES_BIN=self.gate_ok())
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        pairs = [(e["type"], str(e["task"])) for e in self.ledger()]
        self.assertIn(("integration_failed", "1"), pairs)
        self.assertIn(("integrated", "2"), pairs)
        # task 1's conflicting edit was aborted; task 2's change landed
        self.assertEqual(
            (self.repo / "lib" / "a.go").read_text(encoding="utf-8"),
            "package a // integration\n")
        self.assertTrue((self.repo / "lib" / "task2.go").is_file())
        self.assertIn("task/1", self.branches())
        self.assertNotIn("task/2", self.branches())

    def test_gate_red_signals_and_leaves_head(self):
        self.alloc(1)
        self.task_commit(1, "lib/task1.go", "package lib\n")
        self.shard_complete(1)
        head_before = self.head()
        r = self.run_integrate(1, RUN_GATES_BIN=self.gate_fail())
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        fails = self.entries("integration_failed")
        self.assertEqual(len(fails), 1, fails)
        self.assertIn("gates", fails[0]["summary"])
        self.assertIn("rc=1", fails[0]["summary"])
        self.assertEqual(self.head(), head_before)
        self.assertNotIn("integrated", [e["type"] for e in self.ledger()])
        self.assertIn("task/1", self.branches())
        self.assertTrue(self.wt(1).exists())
        # the aborted merge must leave no half-merged state behind
        self.assertEqual(git(self.repo, "status", "--porcelain").stdout.strip(), "")
        self.assertFalse((self.repo / ".git" / "MERGE_HEAD").exists())

    def test_commit_failure_signals_and_aborts_merge(self):
        self.alloc(1)
        self.task_commit(1, "lib/task1.go", "package lib\n")
        self.shard_complete(1)
        head_before = self.head()
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        subprocess.run([BASH, "-c", "chmod +x '{}'".format(hook)],
                       capture_output=True)
        r = self.run_integrate(1, RUN_GATES_BIN=self.gate_ok())
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        fails = self.entries("integration_failed")
        self.assertEqual(len(fails), 1, fails)
        self.assertIn("commit", fails[0]["summary"])
        self.assertIn("rc=", fails[0]["summary"])
        self.assertEqual(self.head(), head_before)
        self.assertNotIn("integrated", [e["type"] for e in self.ledger()])
        # the failed commit must not leave the merge staged (MERGE_HEAD/clean)
        self.assertEqual(git(self.repo, "status", "--porcelain").stdout.strip(), "")
        self.assertFalse((self.repo / ".git" / "MERGE_HEAD").exists())
        self.assertIn("task/1", self.branches())
        self.assertTrue(self.wt(1).exists())

    def test_flutter_lang_runs_green_gate_argv(self):
        self.alloc(1)
        self.task_commit(1, "lib/task1.go", "package lib\n")
        self.shard_complete(1)
        gate = {"ts": "t", "type": "gate", "task": "-", "summary": "go",
                "lang": "flutter", "test_cmd": "flutter test",
                "analyze_cmd": "flutter analyze"}
        # replace just the first gate line; keep worktree_alloc (base=) intact
        rest = [line for line in (self.ws / "ledger.jsonl").read_text(
                    encoding="utf-8").splitlines()
                if line.strip() and not json.loads(line).get("type") == "gate"]
        (self.ws / "ledger.jsonl").write_text(
            json.dumps(gate) + "\n" + "\n".join(rest) + "\n", encoding="utf-8")
        argv_log = self._tmp / "green-gate-argv"
        stub = write_stub(
            self.stub_dir, "green-gate",
            "printf '%%s\\n' \"$*\" >> \"%s\"\nexit 0\n" % (argv_log,))
        r = self.run_integrate(1, GREEN_GATE_BIN=stub,
                               RUN_GATES_BIN=self.gate_fail())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(argv_log.read_text(encoding="utf-8").strip(),
                         "--no-commit -w %s -t 1" % self.ws)
        self.assertEqual(len(self.entries("integrated")), 1, self.ledger())

    def test_batch_merges_the_wave_and_gates_once(self):
        """S2: a >=2-task wave merges all its branches first and runs the full
        gate exactly ONCE; the common uncoupled case stops paying one suite per
        merge."""
        self.alloc(1)
        self.alloc(2)
        self.task_commit(1, "lib/task1.go", "package lib\n")
        self.task_commit(2, "lib/task2.go", "package lib\n")
        self.shard_complete(1)
        self.shard_complete(2)
        counter = self._tmp / "gate-count"
        stub = write_stub(
            self.stub_dir, "gate-count",
            "n=$(cat \"%s\" 2>/dev/null || echo 0)\n"
            "n=$((n+1))\n"
            "printf '%%s' \"$n\" > \"%s\"\n"
            "exit 0\n" % (counter, counter))
        r = self.run_integrate(1, 2, RUN_GATES_BIN=stub)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(counter.read_text(encoding="utf-8").strip(), "1")
        self.assertEqual(
            sorted(str(e["task"]) for e in self.entries("integrated")), ["1", "2"])
        self.assertTrue((self.repo / "lib" / "task1.go").is_file())
        self.assertTrue((self.repo / "lib" / "task2.go").is_file())
        self.assertNotIn("task/1", self.branches())
        self.assertNotIn("task/2", self.branches())

    def test_batch_gate_red_falls_back_to_per_merge(self):
        """A red batch gate resets and bisects with the per-merge loop, which
        still lands both tasks when each merge is individually green."""
        self.alloc(1)
        self.alloc(2)
        self.task_commit(1, "lib/task1.go", "package lib\n")
        self.task_commit(2, "lib/task2.go", "package lib\n")
        self.shard_complete(1)
        self.shard_complete(2)
        counter = self._tmp / "gate-count"
        stub = write_stub(
            self.stub_dir, "gate-first-red",
            "n=$(cat \"%s\" 2>/dev/null || echo 0)\n"
            "n=$((n+1))\n"
            "printf '%%s' \"$n\" > \"%s\"\n"
            "[ \"$n\" -eq 1 ] && exit 1\n"
            "exit 0\n" % (counter, counter))
        r = self.run_integrate(1, 2, RUN_GATES_BIN=stub)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(counter.read_text(encoding="utf-8").strip(), "3")
        self.assertEqual(
            sorted(str(e["task"]) for e in self.entries("integrated")), ["1", "2"])
        self.assertNotIn("integration_failed",
                         [e["type"] for e in self.ledger()])
        self.assertTrue((self.repo / "lib" / "task1.go").is_file())
        self.assertTrue((self.repo / "lib" / "task2.go").is_file())

    def test_batch_red_then_bisect_isolates_a_bad_task(self):
        """The bisect still leaves a genuinely bad task out: when only task 2's
        tree is red, task 1 integrates and task 2 is integration_failed."""
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
        self.assertFalse((self.repo / "lib" / "task2.go").exists())
        self.assertNotIn("task/1", self.branches())
        self.assertIn("task/2", self.branches())

    def test_ff_equivalent_merge_skips_green_gate(self):
        """ADR-0013: when HEAD is an ancestor of task/N and the branch tip's
        tree equals the tree green-gate already validated (recorded as `tree=`
        on the shard's commit entry), the post-merge suite is redundant and
        must be skipped, ledgered `integrate_suite_skipped`; the merge still
        lands, commits, and releases the worktree."""
        self.alloc(1)
        self.task_commit(1, "lib/task1.go", "package lib\n")
        self.shard_complete(1)
        tree = self.task_tree(1)
        self.shard_append(1, {"ts": "t", "type": "commit", "task": "1",
                              "summary": "green deadbee", "commits": "deadbee",
                              "tree": tree})
        self.make_flutter_gate()
        argv_log = self._tmp / "green-gate-argv"
        stub = write_stub(
            self.stub_dir, "green-gate",
            "printf '%%s\\n' \"$*\" >> \"%s\"\nexit 0\n" % (argv_log,))
        r = self.run_integrate(1, GREEN_GATE_BIN=stub,
                               RUN_GATES_BIN=self.gate_fail())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(argv_log.exists(), "green-gate must not run")
        skipped = self.entries("integrate_suite_skipped")
        self.assertEqual(len(skipped), 1, self.ledger())
        self.assertEqual(str(skipped[0]["task"]), "1")
        self.assertIn(tree, skipped[0]["summary"])
        self.assertEqual(len(self.entries("integrated")), 1, self.ledger())
        self.assertTrue((self.repo / "lib" / "task1.go").is_file())
        self.assertNotIn("task/1", self.branches())

    def test_non_equivalent_merge_runs_green_gate(self):
        """The skip is guarded: a recorded gated tree that does not match the
        branch tip means the suite must run (the safe default)."""
        self.alloc(1)
        self.task_commit(1, "lib/task1.go", "package lib\n")
        self.shard_complete(1)
        self.shard_append(1, {"ts": "t", "type": "commit", "task": "1",
                              "summary": "green deadbee", "commits": "deadbee",
                              "tree": "0" * 40})
        self.make_flutter_gate()
        argv_log = self._tmp / "green-gate-argv"
        stub = write_stub(
            self.stub_dir, "green-gate",
            "printf '%%s\\n' \"$*\" >> \"%s\"\nexit 0\n" % (argv_log,))
        r = self.run_integrate(1, GREEN_GATE_BIN=stub,
                               RUN_GATES_BIN=self.gate_fail())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(argv_log.exists(), "green-gate must run")
        self.assertEqual(argv_log.read_text(encoding="utf-8").strip(),
                         "--no-commit -w %s -t 1" % self.ws)
        self.assertNotIn("integrate_suite_skipped",
                         [e["type"] for e in self.ledger()])

    def test_usage_no_args(self):
        r = subprocess.run([BASH, str(SCRIPTS / "integrate")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("usage", r.stderr.lower())

    def test_usage_one_arg(self):
        r = subprocess.run(
            [BASH, str(SCRIPTS / "integrate"), str(self.ws)],
            capture_output=True, text=True, cwd=str(self.repo))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
