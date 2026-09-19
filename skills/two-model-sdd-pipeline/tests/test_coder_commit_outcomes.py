"""Regression module for F4: the generic coder gate must distinguish gate
success from commit success.

The reviewed baseline exited 0 when a green gate had nothing to commit (or the
commit failed), so routing returned to CODER and the gate/provider ran again
forever. These tests drive the real coder-gate (and a real task-run path) with
gate/dispatch/git stubs and assert the explicit blockers.
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

# Hand-derived `go test -json` output: a named test ran and failed (a valid red
# for red-form-check). Not computed by the code under test.
GO_TEST_FAILURE = "\n".join([
    '{"Time":"2026-01-01T00:00:00Z","Action":"run",'
    '"Package":"example.com/foo","Test":"TestAdd"}',
    '{"Time":"2026-01-01T00:00:00Z","Action":"output",'
    '"Package":"example.com/foo","Test":"TestAdd",'
    '"Output":"    add_test.go:10: got 5, want 4\\n"}',
    '{"Time":"2026-01-01T00:00:00Z","Action":"fail",'
    '"Package":"example.com/foo","Test":"TestAdd","Elapsed":0.0}',
]) + "\n"


def write_stub(directory, name, body):
    p = pathlib.Path(directory) / name
    p.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    if os.name == "nt":
        subprocess.run([BASH, "-c", "chmod +x '{}'".format(p)],
                       capture_output=True)
    else:
        p.chmod(0o755)
    return str(p)


class CoderCommitOutcomesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="coder-commit-"))
        self.stub_dir = self._tmp / "stubs"
        self.stub_dir.mkdir()
        self.ws = self._tmp / "ws"
        self.ws.mkdir()
        (self.ws / "ledger.jsonl").write_text(json.dumps({
            "ts": "x", "type": "gate", "task": "-", "summary": "go",
            "test_cmd": "go test ./...", "analyze_cmd": "go vet ./...",
            "lang": "go"}) + "\n", encoding="utf-8")
        (self.ws / "task-1-brief.md").write_text("# Task 1\n", encoding="utf-8")
        (self.ws / "task-1-red.txt").write_text(GO_TEST_FAILURE,
                                                encoding="utf-8")
        self.repo = self._tmp / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(self.repo), check=True)
        subprocess.run(["git", "config", "user.email", "t@t"],
                       cwd=str(self.repo), check=True)
        subprocess.run(["git", "config", "user.name", "t"],
                       cwd=str(self.repo), check=True)
        (self.repo / "file.txt").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(self.repo), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"],
                       cwd=str(self.repo), check=True)
        self.gate_log = self._tmp / "gate.log"
        self.dispatch_log = self._tmp / "dispatch.log"

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def gate_ok(self):
        return write_stub(
            self.stub_dir, "run-gates",
            'echo "$*" >> "%s"\nexit 0\n' % self.gate_log)

    def dispatch_stub(self):
        return write_stub(
            self.stub_dir, "dispatch",
            'echo "$*" >> "%s"\nexit 0\n' % self.dispatch_log)

    def git_wrapper(self, name, condition):
        real = shutil.which("git")
        body = ('if %s; then exit %s; fi\nexec "%s" "$@"\n'
                % (condition[0], condition[1], real))
        return write_stub(self.stub_dir, name, body)

    def env(self, **extra):
        env = {
            "RUN_GATES_BIN": self.gate_ok(),
            "DISPATCH_BIN": self.dispatch_stub(),
            "GIT_BIN": "git",
        }
        env.update(extra)
        return env

    def run_coder_gate(self, **extra):
        env = dict(os.environ)
        env.update(self.env(**extra))
        return subprocess.run(
            [BASH, str(SCRIPTS / "coder-gate"), str(self.ws), "1"],
            cwd=str(self.repo), env=env, capture_output=True, text=True)

    def ledger_types(self):
        return [json.loads(line)["type"]
                for line in (self.ws / "ledger.jsonl").read_text(
                    encoding="utf-8").splitlines() if line.strip()]

    def commits(self):
        return subprocess.run(["git", "log", "--oneline"], cwd=str(self.repo),
                              capture_output=True, text=True).stdout

    def dispatch_calls(self):
        return (self.dispatch_log.read_text(encoding="utf-8")
                if self.dispatch_log.exists() else "")

    def test_empty_commit_blocks_without_review(self):
        # gate green, valid RED, but nothing changed in the working tree
        r = self.run_coder_gate()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("nothing to commit", (r.stdout + r.stderr).lower())
        self.assertNotIn("commit", self.ledger_types())
        self.assertNotIn("two-model-reviewer", self.dispatch_calls())
        self.assertEqual(self.commits().count("\n"), 1)  # base only
        self.assertEqual(self.gate_log.read_text(encoding="utf-8").count("\n"),
                         1, "the gate must run once, not loop")

    def test_verify_only_task_allows_empty_commit(self):
        """An empty-but-green gate is expected for a verify_only task (a check
        task owns an existing surface, it does not change it): record the
        intentional empty commit and proceed to the reviewer."""
        (self.ws / "plan.json").write_text(json.dumps({
            "feature": "f",
            "tasks": [{"id": 1, "title": "v", "touches": ["file.txt"],
                       "verify_only": True, "depends_on": []}],
        }), encoding="utf-8")
        r = self.run_coder_gate()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("commit", self.ledger_types())
        self.assertIn("two-model-reviewer", self.dispatch_calls())
        self.assertEqual(self.commits().count("\n"), 2)  # base + verify
        self.assertIn("verify",
                      subprocess.run(["git", "log", "--pretty=%s"],
                                     cwd=str(self.repo), capture_output=True,
                                     text=True).stdout.lower())

    def test_verify_only_false_still_blocks_empty_commit(self):
        """The flag must be present, not merely its absence tolerated: a task
        whose plan does not declare verify_only keeps the hard barrier."""
        (self.ws / "plan.json").write_text(json.dumps({
            "feature": "f",
            "tasks": [{"id": 1, "title": "v", "touches": ["file.txt"],
                       "verify_only": False, "depends_on": []}],
        }), encoding="utf-8")
        r = self.run_coder_gate()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("nothing to commit", (r.stdout + r.stderr).lower())
        self.assertEqual(self.commits().count("\n"), 1)  # base only

    def test_commit_failure_blocks_and_preserves_changes(self):
        (self.repo / "file.txt").write_text("green change\n", encoding="utf-8")
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        subprocess.run([BASH, "-c", "chmod +x '{}'".format(hook)],
                       capture_output=True)
        r = self.run_coder_gate()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("commit", (r.stdout + r.stderr).lower())
        self.assertNotIn("commit", self.ledger_types())
        self.assertNotIn("two-model-reviewer", self.dispatch_calls())
        self.assertEqual(self.commits().count("\n"), 1)
        # the change is preserved (still in the working tree), not discarded
        self.assertEqual(
            (self.repo / "file.txt").read_text(encoding="utf-8"),
            "green change\n")

    def test_staging_error_blocks(self):
        (self.repo / "file.txt").write_text("green change\n", encoding="utf-8")
        wrapper = self.git_wrapper(
            "git-add-fail", ('[ "${1:-}" = "add" ]', 1))
        r = self.run_coder_gate(GIT_BIN=wrapper)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("staging", (r.stdout + r.stderr).lower())
        self.assertNotIn("commit", self.ledger_types())
        self.assertNotIn("two-model-reviewer", self.dispatch_calls())
        self.assertEqual(
            (self.repo / "file.txt").read_text(encoding="utf-8"),
            "green change\n")

    def test_staged_diff_inspection_error_blocks(self):
        (self.repo / "file.txt").write_text("green change\n", encoding="utf-8")
        wrapper = self.git_wrapper(
            "git-diff-err",
            ('[ "${1:-}" = "diff" ] && [ "${2:-}" = "--cached" ]', 2))
        r = self.run_coder_gate(GIT_BIN=wrapper)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("staged diff", (r.stdout + r.stderr).lower())
        self.assertNotIn("commit", self.ledger_types())
        self.assertNotIn("two-model-reviewer", self.dispatch_calls())
        self.assertEqual(self.commits().count("\n"), 1)

    def test_successful_commit_control(self):
        (self.repo / "file.txt").write_text("green change\n", encoding="utf-8")
        r = self.run_coder_gate()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("commit", self.ledger_types())
        self.assertIn("two-model-reviewer", self.dispatch_calls())
        self.assertEqual(self.commits().count("\n"), 2)  # base + green

    def test_task_run_terminates_on_empty_commit_without_repeat(self):
        """The real task-run path must stop on the empty-commit blocker instead
        of routing back to CODER and re-running the gate/provider. The CODER
        branch is stubbed to a bound so the pre-fix loop cannot hang the suite;
        the RED wrapper records coder-gate's own exit status, which is the
        assertion that distinguishes the fix."""
        (self.ws / "plan.json").write_text(json.dumps({
            "feature": "f", "tasks": [
                {"id": 1, "title": "t", "summary": "s", "acceptance": ["a"],
                 "spec_refs": ["s"], "touches": ["file.txt"],
                 "depends_on": []}]}), encoding="utf-8")
        real_coder_gate = SCRIPTS / "coder-gate"
        ledger_append = SCRIPTS / "ledger-append"
        rc_file = self._tmp / "coder-gate.rc"
        # The wrapper ledgers red_check (as the real red-gate does) so route-next
        # emits CODER once coder-gate returns; the pre-fix empty-commit path then
        # reaches the bounded CODER stub instead of re-emitting RED forever.
        red_gate = write_stub(
            self.stub_dir, "red-gate-real",
            '"%s" "$1/ledger.jsonl" red_check 1 RED\n'
            '"%s" "$1" "$2"; rc=$?\n'
            'printf \'%%s\' "$rc" > "%s"\n'
            'exit "$rc"\n' % (ledger_append, real_coder_gate, rc_file))
        bounded_coder = write_stub(self.stub_dir, "coder-gate-bounded",
                                   "exit 1\n")
        env = dict(os.environ)
        env.update({
            "RED_GATE_BIN": red_gate,
            "CODER_GATE_BIN": bounded_coder,
            "RUN_GATES_BIN": self.gate_ok(),
            "DISPATCH_BIN": self.dispatch_stub(),
            "GIT_BIN": "git",
        })
        proc = subprocess.run(
            [BASH, str(SCRIPTS / "task-run"), str(self.ws), "1", "1"],
            cwd=str(self.repo), env=env, capture_output=True, text=True,
            timeout=90)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(rc_file.read_text(encoding="utf-8").strip(), "1",
                         "coder-gate must return nonzero on a no-change commit")
        self.assertEqual(self.gate_log.read_text(encoding="utf-8").count("\n"),
                         1, "the gate must not run again after the blocker")
        self.assertNotIn("two-model-reviewer", self.dispatch_calls())


if __name__ == "__main__":
    unittest.main()
