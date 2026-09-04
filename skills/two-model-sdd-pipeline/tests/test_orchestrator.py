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


def run_script(script, args, cwd, env_extra):
    env = dict(os.environ)
    env.update(env_extra)
    return subprocess.run(
        [BASH, str(SCRIPTS / script), *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
    )


class OrchestratorTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="orchestrator-tests-"))
        self.stub_dir = self._tmp / "stubs"
        self.stub_dir.mkdir()
        self.ws = self._tmp / "ws"
        self.ws.mkdir()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def ledger(self, entries):
        lines = [json.dumps(e) for e in entries]
        (self.ws / "ledger.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def entry(self, etype, task, summary, **extra):
        e = {"ts": "2026-09-02T00:00:00Z", "type": etype, "task": str(task), "summary": summary}
        e.update(extra)
        return e

    def stub(self, name, body):
        return write_stub(self.stub_dir, name, body)


class TestOrchestratorHandoff(OrchestratorTestBase):
    def test_empty_ledger_hands_off_brief(self):
        self.ledger([])
        r = run_script(
            "orchestrator", [str(self.ws), "3", "5"],
            cwd=self._tmp, env_extra={"RTK_ENABLED": "0"},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OUTCOME: BRIEF 3", r.stdout)

    def test_send_back_hands_off_corrective(self):
        self.ledger([
            self.entry("brief_ready", 3, "task"),
            self.entry("red_check", 3, "RED"),
            self.entry("coder_round", 3, "Coder"),
            self.entry("commit", 3, "Task", commits="a1b2c3"),
            self.entry("review_outcome", 3, "SEND_BACK", findings="1"),
        ])
        r = run_script(
            "orchestrator", [str(self.ws), "3", "5"],
            cwd=self._tmp, env_extra={"RTK_ENABLED": "0"},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OUTCOME: CORRECTIVE 3", r.stdout)

    def test_approved_hands_off_next(self):
        self.ledger([
            self.entry("brief_ready", 3, "task"),
            self.entry("red_check", 3, "RED"),
            self.entry("coder_round", 3, "Coder"),
            self.entry("commit", 3, "Task", commits="a1b2c3"),
            self.entry("review_outcome", 3, "APPROVED"),
            self.entry("task_complete", 3, "Task"),
        ])
        r = run_script(
            "orchestrator", [str(self.ws), "3", "5"],
            cwd=self._tmp, env_extra={"RTK_ENABLED": "0"},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OUTCOME: NEXT 4", r.stdout)

    def test_approved_next_cleans_that_tasks_sessions(self):
        # A completed task's sessions must be deleted (history hygiene) -
        # the task-N-session.txt files vanish and opencode gets a delete call.
        self.ledger([
            self.entry("brief_ready", 3, "task"),
            self.entry("red_check", 3, "RED"),
            self.entry("coder_round", 3, "Coder"),
            self.entry("commit", 3, "Task", commits="a1b2c3"),
            self.entry("review_outcome", 3, "APPROVED"),
            self.entry("task_complete", 3, "Task"),
        ])
        (self.ws / "task-3-two-model-coder-session.txt").write_text("ses_3c\n", encoding="utf-8")
        (self.ws / "task-3-two-model-reviewer-session.txt").write_text("ses_3r\n", encoding="utf-8")
        deleted = self._tmp / "deleted.log"
        opencode_stub = self.stub(
            "opencode",
            'echo "${3:-}" >> "${DELETED_LOG:?}"\n',
        )
        r = run_script(
            "orchestrator", [str(self.ws), "3", "5"],
            cwd=self._tmp,
            env_extra={"RTK_ENABLED": "0", "OPENCODE_BIN": opencode_stub,
                       "DELETED_LOG": str(deleted)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OUTCOME: NEXT 4", r.stdout)
        self.assertEqual(sorted(deleted.read_text(encoding="utf-8").strip().splitlines()),
                         ["ses_3c", "ses_3r"])
        self.assertFalse((self.ws / "task-3-two-model-coder-session.txt").exists())
        self.assertFalse((self.ws / "task-3-two-model-reviewer-session.txt").exists())


class TestOrchestratorExecutes(OrchestratorTestBase):
    def test_red_action_invokes_red_gate(self):
        """On route-next RED, the orchestrator must execute the action by
        invoking the red-gate script (which dispatches C on success), then
        re-route and hand the outcome back to B."""
        self.ledger([self.entry("brief_ready", 3, "task")])
        red_log = self._tmp / "red.log"
        red_stub = self.stub(
            "red-gate",
            'echo "RED-GATE CALLED $*" >> "${RED_LOG:?}"; exit "${RED_EXIT:-0}"\n',
        )
        r = run_script(
            "orchestrator", [str(self.ws), "3", "5"],
            cwd=self._tmp,
            env_extra={"RTK_ENABLED": "0", "RED_GATE_BIN": red_stub,
                       "RED_LOG": str(red_log)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("RED-GATE CALLED", red_log.read_text(encoding="utf-8"))
        # after red-gate runs (stub exits 0 without ledgering), the next
        # route is still CODER via red_check? no - the stub added no ledger
        # entry, so route-next still emits RED -> orchestrator loops? It must
        # NOT loop forever: it executes RED once and re-routes.
        self.assertIn("OUTCOME:", r.stdout)

    def test_coder_round_hands_off(self):
        """route-next CODER is owned by the per-task scripts (red-gate already
        dispatched C); the orchestrator records the outcome and hands back."""
        self.ledger([
            self.entry("brief_ready", 3, "task"),
            self.entry("red_check", 3, "RED"),
        ])
        r = run_script(
            "orchestrator", [str(self.ws), "3", "5"],
            cwd=self._tmp, env_extra={"RTK_ENABLED": "0"},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OUTCOME: CODER 3 1", r.stdout)


class TestOrchestratorUsage(OrchestratorTestBase):
    def test_missing_args_is_usage(self):
        r = run_script("orchestrator", [], cwd=self._tmp, env_extra={})
        self.assertEqual(r.returncode, 2)

    def test_missing_ledger_is_error(self):
        r = run_script("orchestrator", [str(self.ws), "3", "5"], cwd=self._tmp, env_extra={})
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()