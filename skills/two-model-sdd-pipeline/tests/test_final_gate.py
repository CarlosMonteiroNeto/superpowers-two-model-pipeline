import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"

if os.name == "nt":
    git_bash = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
    BASH = str(git_bash) if git_bash.exists() else "bash"
else:
    BASH = "bash"


def write_stub(directory, name, body):
    p = pathlib.Path(directory) / name
    p.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    if os.name == "nt":
        subprocess.run([BASH, "-c", "chmod +x '{}'".format(p)], capture_output=True)
    else:
        p.chmod(0o755)
    return str(p)


class FinalGateBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="final-gate-tests-")
        self.ws = pathlib.Path(self._tmp) / "ws"
        self.ws.mkdir()
        self.stub_dir = pathlib.Path(self._tmp) / "stubs"
        self.stub_dir.mkdir()
        # forward slashes: the ledger stores command strings; Windows backslashes
        # would be JSON-escaped and break tokenization.
        self.test_stub = write_stub(self.stub_dir, "tcmd", 'echo "tests ok"; exit "${STUB_TEST_EXIT:-0}"').replace("\\", "/")
        self.analyze_stub = write_stub(self.stub_dir, "acmd", 'echo "analyze ok"; exit "${STUB_ANALYZE_EXIT:-0}"').replace("\\", "/")
        self.env = {"STUB_TEST_EXIT": "0", "STUB_ANALYZE_EXIT": "0"}
        self.ledger = self.ws / "ledger.jsonl"

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def write_ledger(self, entries):
        self.ledger.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")

    def gate_entry(self):
        return {"ts": "t", "type": "gate", "task": "-", "summary": "gate",
                "test": self.test_stub, "analyze": self.analyze_stub}

    def review(self, task, verdict):
        return {"ts": "t", "type": "review_outcome", "task": str(task), "summary": verdict}

    def complete(self, task, parked=None, severity=None):
        e = {"ts": "t", "type": "task_complete", "task": str(task), "summary": "ok"}
        if parked:
            e["PARKED"] = parked
        if severity:
            e["PARKED_SEVERITY"] = severity
        return e

    def run_it(self, total="3"):
        return subprocess.run(
            [BASH, str(SCRIPTS / "final-gate"), str(self.ws), total],
            capture_output=True, text=True, env={**os.environ, **self.env},
        )


class TestFinalGate(FinalGateBase):
    def test_ready_when_all_complete_and_green(self):
        self.write_ledger([
            self.gate_entry(),
            self.review(1, "APPROVED"), self.complete(1),
            self.review(2, "APPROVED"), self.complete(2),
            self.review(3, "APPROVED"), self.complete(3),
        ])
        r = self.run_it()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_missing_task_complete_blocks(self):
        self.write_ledger([
            self.gate_entry(),
            self.review(1, "APPROVED"), self.complete(1),
            self.review(2, "APPROVED"),
        ])
        r = self.run_it(total="3")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("task 3", r.stdout + r.stderr)

    def test_unresolved_send_back_blocks(self):
        self.write_ledger([
            self.gate_entry(),
            self.review(1, "SEND_BACK", ),
        ])
        r = self.run_it()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("SEND_BACK", r.stdout + r.stderr)

    def test_parked_critical_blocks(self):
        self.write_ledger([
            self.gate_entry(),
            self.review(1, "APPROVED"),
            self.complete(1, parked="sev=Critical", severity="Critical"),
        ])
        r = self.run_it()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_parked_minor_does_not_block(self):
        self.write_ledger([
            self.gate_entry(),
            self.review(1, "APPROVED"),
            self.complete(1, parked="sev=Minor", severity="Minor"),
        ])
        r = self.run_it(total="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_parked_prose_mentioning_important_does_not_block(self):
        """M7: severity is a field, not a substring - a parked Minor whose
        note says 'not important, cosmetic only' must not block the branch."""
        self.write_ledger([
            self.gate_entry(),
            self.review(1, "APPROVED"),
            self.complete(1, parked="not important, cosmetic only",
                          severity="Minor"),
        ])
        r = self.run_it(total="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_legacy_prose_parked_does_not_block(self):
        """M7: a legacy task_complete with only free-text PARKED (no severity
        field) is not a structured blocking finding."""
        self.write_ledger([
            self.gate_entry(),
            self.review(1, "APPROVED"),
            self.complete(1, parked="Critical-looking prose, no field"),
        ])
        r = self.run_it(total="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_failing_test_command_blocks(self):
        self.write_ledger([
            self.gate_entry(),
            self.review(1, "APPROVED"), self.complete(1),
        ])
        self.env["STUB_TEST_EXIT"] = "1"
        r = self.run_it(total="1")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def _git_repo(self):
        repo = pathlib.Path(self._tmp) / "repo"
        repo.mkdir(exist_ok=True)
        subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), check=True)
        (repo / "file.txt").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "green"], cwd=str(repo), check=True)
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(repo),
                             capture_output=True, text=True, check=True).stdout.strip()
        return repo, sha

    def _new_keys_gate(self):
        return {"ts": "t", "type": "gate", "task": "-", "summary": "gate",
                "test_cmd": self.test_stub, "analyze_cmd": self.analyze_stub}

    def _run_in(self, repo, total="1"):
        return subprocess.run(
            [BASH, str(SCRIPTS / "final-gate"), str(self.ws), total],
            capture_output=True, text=True, cwd=str(repo),
            env={**os.environ, **self.env},
        )

    def test_unchanged_tree_skips_rerun(self):
        """Clean tree + HEAD == last ledger green commit: the last task's
        gates already proved this tree — even failing commands must not run."""
        repo, sha = self._git_repo()
        self.write_ledger([
            self._new_keys_gate(),
            self.review(1, "APPROVED"), self.complete(1),
            {"ts": "t", "type": "commit", "task": "1", "summary": "green",
             "commits": sha},
        ])
        self.env["STUB_TEST_EXIT"] = "1"
        self.env["STUB_ANALYZE_EXIT"] = "1"
        r = self._run_in(repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("skipping", r.stdout + r.stderr)

    def test_unchanged_tree_skips_rerun_after_integration(self):
        """After a wave, HEAD is a merge commit and the newest green entry is
        `integrated`, not `commit`; the skip must still fire (S2)."""
        repo, _ = self._git_repo()
        base = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                              cwd=str(repo), capture_output=True, text=True,
                              check=True).stdout.strip()
        subprocess.run(["git", "checkout", "-q", "-b", "feature"], cwd=str(repo), check=True)
        (repo / "other.txt").write_text("y\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "task 1"], cwd=str(repo), check=True)
        subprocess.run(["git", "checkout", "-q", base], cwd=str(repo), check=True)
        subprocess.run(["git", "merge", "-q", "--no-ff", "-m", "merge task/1", "feature"],
                       cwd=str(repo), check=True)
        merge_sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(repo),
            capture_output=True, text=True, check=True).stdout.strip()
        self.write_ledger([
            self._new_keys_gate(),
            self.review(1, "APPROVED"), self.complete(1),
            {"ts": "t", "type": "integrated", "task": "1", "summary": "merged",
             "commits": merge_sha, "sha": merge_sha},
        ])
        self.env["STUB_TEST_EXIT"] = "1"
        self.env["STUB_ANALYZE_EXIT"] = "1"
        r = self._run_in(repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("skipping", r.stdout + r.stderr)

    def test_changed_tree_runs_commands(self):
        """Dirty tree: the re-run happens (and a failing command blocks)."""
        repo, sha = self._git_repo()
        (repo / "file.txt").write_text("changed\n", encoding="utf-8")
        self.write_ledger([
            self._new_keys_gate(),
            self.review(1, "APPROVED"), self.complete(1),
            {"ts": "t", "type": "commit", "task": "1", "summary": "green",
             "commits": sha},
        ])
        self.env["STUB_TEST_EXIT"] = "1"
        r = self._run_in(repo)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertNotIn("skipping", r.stdout + r.stderr)

    def test_unmatched_worktree_alloc_blocks(self):
        """A wave that allocated a worktree but never released it means a
        parallel task never closed out - not ready for final review."""
        repo, _ = self._git_repo()
        self.write_ledger([
            self._new_keys_gate(),
            self.review(1, "APPROVED"), self.complete(1),
            {"ts": "t", "type": "worktree_alloc", "task": "1", "summary": "alloc"},
        ])
        r = self._run_in(repo)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("worktree", r.stdout + r.stderr)

    def test_released_worktree_does_not_block(self):
        repo, _ = self._git_repo()
        self.write_ledger([
            self._new_keys_gate(),
            self.review(1, "APPROVED"), self.complete(1),
            {"ts": "t", "type": "worktree_alloc", "task": "1", "summary": "alloc"},
            {"ts": "t", "type": "worktree_release", "task": "1", "summary": "release"},
        ])
        r = self._run_in(repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_leftover_task_branch_blocks(self):
        repo, _ = self._git_repo()
        subprocess.run(["git", "branch", "task/2"], cwd=str(repo), check=True)
        self.write_ledger([
            self._new_keys_gate(),
            self.review(1, "APPROVED"), self.complete(1),
        ])
        r = self._run_in(repo)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("task/2", r.stdout + r.stderr)

    def test_failed_integration_after_completion_blocks(self):
        repo, _ = self._git_repo()
        self.write_ledger([
            self._new_keys_gate(),
            self.review(1, "APPROVED"), self.complete(1),
            {"ts": "t", "type": "integration_failed", "task": "1", "summary": "gates"},
        ])
        r = self._run_in(repo)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("task 1", r.stdout + r.stderr)

    def test_integration_failed_then_complete_does_not_block(self):
        """A failure that was later re-run and closed out is not a blocker."""
        repo, _ = self._git_repo()
        self.write_ledger([
            self._new_keys_gate(),
            self.review(1, "APPROVED"),
            {"ts": "t", "type": "integration_failed", "task": "1", "summary": "gates"},
            self.review(1, "APPROVED"), self.complete(1),
            {"ts": "t", "type": "integrated", "task": "1", "summary": "integrated"},
        ])
        r = self._run_in(repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_clean_serial_ledger_does_not_fire_new_checks(self):
        repo, _ = self._git_repo()
        self.write_ledger([
            self._new_keys_gate(),
            self.review(1, "APPROVED"), self.complete(1),
            self.review(2, "APPROVED"), self.complete(2),
            self.review(3, "APPROVED"), self.complete(3),
        ])
        r = self._run_in(repo, total="3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_missing_ledger_is_usage(self):
        r = self.run_it()
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()