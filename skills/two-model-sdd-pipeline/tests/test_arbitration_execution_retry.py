"""Regression module for F3: a resolved arbitration must start a NEW execution
attempt.

The reviewed baseline appended `arbitrate_resolved` even when the plan refresh
failed, and the router then fell through to CODER (re-running coder-gate against
pre-ruling RED evidence). These tests exercise the real router, red-gate, and
task-run with deterministic dispatch/gate stubs and prove:

* the router treats the latest `arbitrate_resolved` as an attempt boundary
  (pre-boundary red_check/commit/verdict never advances the new attempt);
* red-gate archives the prior attempt's evidence (never overwriting an earlier
  archive, keeping session records) and resumes the toolchain-selected coder;
* task-run appends `arbitrate_resolved` only after a successful refresh, blocks
  otherwise, and keeps a genuine re-escalation a bounded blocker.
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


def entry(etype, task, summary, **extra):
    e = {"ts": "2026-09-17T12:00:00Z", "type": etype, "task": str(task),
         "summary": summary}
    e.update(extra)
    return e


class RouteBoundaryTest(unittest.TestCase):
    """The router scopes an incomplete task's progress to the post-ruling
    attempt while completed tasks keep their terminal behavior."""

    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="arb-boundary-"))
        self.ws = self._tmp / "ws"
        self.ws.mkdir()
        (self.ws / "plan.json").write_text(json.dumps({"feature": "f", "tasks": [
            {"id": 3, "title": "t", "summary": "s", "acceptance": ["a"],
             "touches": ["src/a"], "depends_on": []},
            {"id": 4, "title": "t", "summary": "s", "acceptance": ["a"],
             "touches": ["src/b"], "depends_on": []},
        ]}), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def ledger(self, entries, partition=None):
        # route-next may self-migrate a per-task partition on the first call;
        # clear any stale partition so each scenario reads exactly its ledger.
        for stale in self.ws.glob("ledger-task-*.jsonl"):
            stale.unlink()
        text = "\n".join(json.dumps(e) for e in entries) + "\n"
        (self.ws / "ledger.jsonl").write_text(text, encoding="utf-8")
        if partition is not None:
            (self.ws / ("ledger-task-%s.jsonl" % partition)).write_text(
                text, encoding="utf-8")

    def routes(self, entries, task=3, total=None, partition=None):
        self.ledger(entries, partition=partition)
        args = [BASH, str(SCRIPTS / "route-next"), str(self.ws), str(task)]
        if total is not None:
            args.append(str(total))
        return subprocess.run(args, capture_output=True, text=True)

    def assert_action(self, r, action):
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), action, r.stdout + r.stderr)

    def test_precommit_defect_after_resolution_routes_red(self):
        r = self.routes([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("escalated", 3, "TEST_DEFECT reported by operador"),
            entry("arbitrate_resolved", 3, "diretor ruled", plan_sha="abc"),
            entry("brief_ready", 3, "rescaffolded"),
        ])
        self.assert_action(r, "RED 3")

    def test_postcommit_review_escalate_after_resolution_routes_red(self):
        r = self.routes([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("commit", 3, "green abc1234", commits="abc1234"),
            entry("review_outcome", 3, "ESCALATE"),
            entry("arbitrate_resolved", 3, "diretor ruled"),
            entry("brief_ready", 3, "rescaffolded"),
        ])
        self.assert_action(r, "RED 3")

    def test_ruling_without_rescaffold_routes_brief(self):
        r = self.routes([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("escalated", 3, "TEST_DEFECT"),
            entry("arbitrate_resolved", 3, "diretor ruled"),
        ])
        self.assert_action(r, "BRIEF 3")

    def test_new_attempt_progresses_red_coder_review(self):
        base = [
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("escalated", 3, "TEST_DEFECT"),
            entry("arbitrate_resolved", 3, "diretor ruled"),
            entry("brief_ready", 3, "rescaffolded"),
        ]
        self.assert_action(self.routes(base), "RED 3")
        self.assert_action(
            self.routes(base + [entry("red_check", 3, "RED")]), "CODER 3")
        self.assert_action(
            self.routes(base + [entry("red_check", 3, "RED"),
                                entry("commit", 3, "green x", commits="x")]),
            "REVIEW 3")

    def test_fresh_approval_after_ruling_advances(self):
        r = self.routes([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("commit", 3, "green a", commits="a"),
            entry("review_outcome", 3, "ESCALATE"),
            entry("arbitrate_resolved", 3, "diretor ruled"),
            entry("brief_ready", 3, "rescaffolded"),
            entry("red_check", 3, "RED"),
            entry("commit", 3, "green b", commits="b"),
            entry("review_outcome", 3, "APPROVED"),
        ], total=5)
        self.assert_action(r, "NEXT 4")

    def test_old_verdict_does_not_approve_the_new_attempt(self):
        """An APPROVED verdict before the ruling is history: the new attempt
        must still route to RED, not advance to NEXT."""
        r = self.routes([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("commit", 3, "green a", commits="a"),
            entry("review_outcome", 3, "APPROVED"),
            entry("arbitrate_resolved", 3, "diretor ruled"),
            entry("brief_ready", 3, "rescaffolded"),
        ])
        self.assert_action(r, "RED 3")

    def test_second_escalation_after_ruling_is_bounded_blocker(self):
        r = self.routes([
            entry("brief_ready", 3, "task"),
            entry("escalated", 3, "TEST_DEFECT"),
            entry("arbitrate_resolved", 3, "diretor ruled"),
            entry("escalated", 3, "TEST_DEFECT again"),
        ])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("did not resolve task 3", r.stderr)

    def test_completed_task_keeps_terminal_behavior(self):
        r = self.routes([
            entry("review_outcome", 3, "APPROVED"),
            entry("task_complete", 3, "APPROVED"),
            entry("arbitrate_resolved", 3, "diretor ruled"),
        ], total=5)
        self.assert_action(r, "NEXT 4")

    def test_partitioned_history_routes_identically(self):
        r = self.routes([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("escalated", 3, "TEST_DEFECT"),
            entry("arbitrate_resolved", 3, "diretor ruled"),
            entry("brief_ready", 3, "rescaffolded"),
        ], partition=3)
        self.assert_action(r, "RED 3")


class RedGateAttemptArchiveTest(unittest.TestCase):
    """red-gate archives prior attempt evidence and resumes the coder on the
    post-arbitration attempt, without touching session records."""

    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="arb-redgate-"))
        self.ws = self._tmp / "ws"
        self.ws.mkdir()
        (self.ws / "task-3-brief.md").write_text("# brief\n", encoding="utf-8")
        self.stub_dir = self._tmp / "stubs"
        self.stub_dir.mkdir()
        self.dispatch_log = self._tmp / "dispatch.log"
        self.coder_gate_log = self._tmp / "coder-gate.log"
        self.dispatch = write_stub(
            self.stub_dir, "dispatch",
            'printf "%%s\\n" "$*" >> "%s"\nexit %s\n'
            % (self.dispatch_log, "${DISPATCH_EXIT:-0}"))
        self.coder_gate = write_stub(
            self.stub_dir, "coder-gate",
            'printf "%%s\\n" "$*" >> "%s"\nexit 0\n' % (self.coder_gate_log,))

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def set_ledger(self, extra=()):
        gate = {"ts": "t", "type": "gate", "task": "-", "summary": "go",
                "lang": "python", "test_cmd": "true", "analyze_cmd": "true"}
        lines = [json.dumps(gate)] + [json.dumps(e) for e in extra]
        (self.ws / "ledger.jsonl").write_text("\n".join(lines) + "\n",
                                              encoding="utf-8")

    def seed_evidence(self, session=None):
        for name in ("task-3-coder.log", "task-3-reviewer.log",
                     "task-3-review.json", "task-3-red.txt"):
            (self.ws / name).write_text("old " + name + "\n", encoding="utf-8")
        if session:
            (self.ws / "task-3-two-model-coder-python-session.txt").write_text(
                session + "\n", encoding="utf-8")

    def run_red_gate(self, **env_extra):
        env = dict(os.environ)
        env.update({"DISPATCH_BIN": self.dispatch,
                    "CODER_GATE_BIN": self.coder_gate})
        env.update(env_extra)
        return subprocess.run(
            [BASH, str(SCRIPTS / "red-gate"), str(self.ws), "3", "true"],
            capture_output=True, text=True, env=env)

    def ledger_types(self):
        return [json.loads(line)["type"]
                for line in (self.ws / "ledger.jsonl").read_text(
                    encoding="utf-8").splitlines() if line.strip()]

    def test_first_attempt_does_not_archive_or_resume(self):
        self.set_ledger()
        self.seed_evidence(session="sess-1")
        r = self.run_red_gate()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.ws / "attempt-1").exists())
        argv = self.dispatch_log.read_text(encoding="utf-8")
        self.assertIn("--agent two-model-coder-python", argv)
        self.assertNotIn("--continue", argv)
        self.assertTrue(self.coder_gate_log.exists())

    def test_post_arbitration_archives_evidence_and_resumes(self):
        self.set_ledger([entry("arbitrate_resolved", 3, "diretor ruled")])
        self.seed_evidence(session="sess-abc")
        r = self.run_red_gate()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        arch = self.ws / "attempt-1"
        self.assertTrue(arch.is_dir())
        for name in ("task-3-coder.log", "task-3-reviewer.log",
                     "task-3-review.json", "task-3-red.txt"):
            self.assertTrue((arch / name).is_file(), name)
        # the active copies were moved away, so the new attempt cannot reuse them
        for name in ("task-3-coder.log", "task-3-reviewer.log",
                     "task-3-review.json", "task-3-red.txt"):
            self.assertFalse((self.ws / name).exists(), name)
        # session records are deliberately preserved for resume
        self.assertTrue(
            (self.ws / "task-3-two-model-coder-python-session.txt").is_file())
        argv = self.dispatch_log.read_text(encoding="utf-8").replace("\n", " ")
        self.assertIn("--agent two-model-coder-python", argv)
        self.assertIn("--continue sess-abc", argv)
        self.assertTrue(self.coder_gate_log.exists())

    def test_no_session_starts_fresh_after_arbitration(self):
        self.set_ledger([entry("arbitrate_resolved", 3, "diretor ruled")])
        self.seed_evidence()
        r = self.run_red_gate()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.ws / "attempt-1").is_dir())
        self.assertNotIn("--continue",
                         self.dispatch_log.read_text(encoding="utf-8"))

    def test_existing_archive_is_not_overwritten(self):
        self.set_ledger([entry("arbitrate_resolved", 3, "diretor ruled")])
        self.seed_evidence(session="s")
        arch = self.ws / "attempt-1"
        arch.mkdir()
        sentinel = arch / "task-3-red.txt"
        sentinel.write_text("PRIOR ATTEMPT\n", encoding="utf-8")
        r = self.run_red_gate()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "PRIOR ATTEMPT\n")
        self.assertTrue((self.ws / "attempt-1-1").is_dir())

    def test_interrupted_dispatch_does_not_enter_coder_gate(self):
        self.set_ledger([entry("arbitrate_resolved", 3, "diretor ruled")])
        self.seed_evidence(session="s")
        r = self.run_red_gate(DISPATCH_EXIT="124")
        self.assertEqual(r.returncode, 124, r.stdout + r.stderr)
        self.assertFalse(self.coder_gate_log.exists())
        self.assertIn("dispatch_interrupted", self.ledger_types())


class TaskRunArbitrationOrderingTest(unittest.TestCase):
    """task-run appends `arbitrate_resolved` only after a successful refresh,
    blocks on a refresh failure, and stays bounded on a re-escalation."""

    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="arb-taskrun-"))
        self.repo = self._tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "t")
        (self.repo / "README.md").write_text("x\n", encoding="utf-8")
        (self.repo / ".superpowers" / "two-model").mkdir(parents=True)
        (self.repo / ".superpowers" / "two-model" / ".gitignore").write_text(
            "*\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "base")

        self.plan = self.repo / "docs" / "recovery-plan.json"
        self.plan.parent.mkdir(parents=True)
        self.plan.write_text(json.dumps({"feature": "f", "tasks": [
            {"id": 3, "title": "t", "summary": "s", "acceptance": ["a"]}]}),
            encoding="utf-8")
        self.ws = self.repo / ".superpowers" / "two-model" / "recovery-plan"
        self.ws.mkdir(parents=True)
        (self.ws / "plan.json").write_text(self.plan.read_text(encoding="utf-8"),
                                           encoding="utf-8")

        self.stub_dir = self._tmp / "stubs"
        self.stub_dir.mkdir()
        self.dispatch_log = self._tmp / "dispatch.log"
        self.red_gate_log = self._tmp / "red-gate.log"
        self.dispatch = write_stub(
            self.stub_dir, "dispatch",
            'printf "%%s\\n" "$*" >> "%s"\nexit 0\n' % (self.dispatch_log,))
        self.coder_gate = write_stub(self.stub_dir, "coder-gate", "exit 0\n")
        self.red_gate = write_stub(
            self.stub_dir, "red-gate",
            'printf "%%s\\n" "$*" >> "%s"\nexit 124\n' % (self.red_gate_log,))

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def set_ledger(self, entries):
        (self.ws / "ledger.jsonl").write_text(
            "\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")

    def ledger_types(self):
        return [json.loads(line)["type"]
                for line in (self.ws / "ledger.jsonl").read_text(
                    encoding="utf-8").splitlines() if line.strip()]

    def run_task_run(self, **env_extra):
        env = dict(os.environ)
        env.update({"DISPATCH_BIN": self.dispatch,
                    "CODER_GATE_BIN": self.coder_gate,
                    "RED_GATE_BIN": self.red_gate,
                    "PLAN": str(self.plan)})
        env.update(env_extra)
        return subprocess.run(
            [BASH, str(SCRIPTS / "task-run"), str(self.ws), "3", "5"],
            capture_output=True, text=True, cwd=str(self.repo), env=env)

    def test_arbitrate_resolved_appended_after_successful_refresh(self):
        self.set_ledger([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("escalated", 3, "TEST_DEFECT"),
        ])
        r = self.run_task_run()
        # the run later blocks on the interrupted red-gate stub (exit 124)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("arbitrate_resolved", self.ledger_types())
        self.assertTrue(self.dispatch_log.exists())

    def test_refresh_failure_blocks_without_resolution(self):
        self.set_ledger([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("escalated", 3, "TEST_DEFECT"),
        ])
        missing = self.repo / "docs" / "missing-plan.json"
        r = self.run_task_run(PLAN=str(missing))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertNotIn("arbitrate_resolved", self.ledger_types())
        self.assertIn("refresh", (r.stdout + r.stderr).lower())

    def test_second_escalation_after_ruling_is_bounded(self):
        self.set_ledger([
            entry("brief_ready", 3, "task"),
            entry("escalated", 3, "TEST_DEFECT"),
            entry("arbitrate_resolved", 3, "diretor ruled"),
            entry("escalated", 3, "TEST_DEFECT again"),
        ])
        r = self.run_task_run()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
