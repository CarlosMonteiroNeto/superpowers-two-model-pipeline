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


def write_ledger(directory, entries):
    """Write a JSONL ledger. entries = list of dicts (ts, type, task, summary)."""
    p = pathlib.Path(directory) / "ledger.jsonl"
    lines = [json.dumps(e) for e in entries]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def entry(etype, task, summary, ts="2026-08-29T12:00:00Z", **extra):
    e = {"ts": ts, "type": etype, "task": str(task), "summary": summary}
    e.update(extra)
    return e


def run_route(ws, task, total=None):
    args = [BASH, str(SCRIPTS / "route-next"), str(ws), str(task)]
    if total is not None:
        args.append(str(total))
    r = subprocess.run(args, capture_output=True, text=True)
    return r


class RouteNextTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="route-next-tests-")
        self.ws = pathlib.Path(self._tmp) / "ws"
        self.ws.mkdir()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def ledger(self, entries):
        return write_ledger(self.ws, entries)

    def assert_action(self, r, action, msg=""):
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), action, msg or (r.stdout + r.stderr))


class TestRouteNextStart(RouteNextTestBase):
    def test_no_entries_emits_brief(self):
        self.ledger([])
        r = run_route(self.ws, 3)
        self.assert_action(r, "BRIEF 3")

    def test_brief_ready_emits_red(self):
        self.ledger([entry("brief_ready", 3, "task")])
        r = run_route(self.ws, 3)
        self.assert_action(r, "RED 3")

    def test_red_check_emits_coder_round_one(self):
        self.ledger([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
        ])
        r = run_route(self.ws, 3)
        self.assert_action(r, "CODER 3 1")


class TestRouteNextRounds(RouteNextTestBase):
    def test_one_coder_round_emits_coder_round_two(self):
        self.ledger([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("coder_round", 3, "Coder", round="1/2"),
        ])
        r = run_route(self.ws, 3)
        self.assert_action(r, "CODER 3 2")

    def test_two_coder_rounds_emits_coder_round_three(self):
        self.ledger([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("coder_round", 3, "Coder", round="1/4"),
            entry("coder_round", 3, "Coder", round="2/4"),
        ])
        r = run_route(self.ws, 3)
        self.assert_action(r, "CODER 3 3")


class TestRouteNextWrapUp(RouteNextTestBase):
    def test_commit_emits_review(self):
        self.ledger([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("coder_round", 3, "Coder"),
            entry("commit", 3, "Task", commits="a1b2c3"),
        ])
        r = run_route(self.ws, 3)
        self.assert_action(r, "REVIEW 3")

    def test_review_approved_emits_next(self):
        self.ledger([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("coder_round", 3, "Coder"),
            entry("commit", 3, "Task", commits="a1b2c3"),
            entry("review_outcome", 3, "APPROVED"),
            entry("task_complete", 3, "Task"),
        ])
        r = run_route(self.ws, 3, total=5)
        self.assert_action(r, "NEXT 4")

    def test_review_approved_last_task_emits_final_review(self):
        self.ledger([
            entry("brief_ready", 5, "task"),
            entry("red_check", 5, "RED"),
            entry("coder_round", 5, "Coder"),
            entry("commit", 5, "Task", commits="a1b2c3"),
            entry("review_outcome", 5, "APPROVED"),
            entry("task_complete", 5, "Task"),
        ])
        r = run_route(self.ws, 5, total=5)
        self.assert_action(r, "FINAL_REVIEW")


class TestRouteNextFixAndEscalation(RouteNextTestBase):
    def test_review_send_back_emits_corrective(self):
        self.ledger([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("coder_round", 3, "Coder"),
            entry("commit", 3, "Task", commits="a1b2c3"),
            entry("review_outcome", 3, "SEND_BACK", findings="1", severity="Critical"),
        ])
        r = run_route(self.ws, 3)
        self.assert_action(r, "CORRECTIVE 3")

    def test_review_escalate_emits_arbitrate(self):
        self.ledger([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("coder_round", 3, "Coder"),
            entry("commit", 3, "Task", commits="a1b2c3"),
            entry("review_outcome", 3, "ESCALATE"),
        ])
        r = run_route(self.ws, 3)
        self.assert_action(r, "ARBITRATE 3")

    def test_escalated_without_commit_emits_arbitrate(self):
        self.ledger([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("coder_round", 3, "Coder"),
            entry("coder_round", 3, "Coder"),
            entry("escalated", 3, "coder failed rounds"),
        ])
        r = run_route(self.ws, 3)
        self.assert_action(r, "ARBITRATE 3")

    def test_three_coder_rounds_emits_coder_round_four(self):
        self.ledger([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("coder_round", 3, "Coder", round="1/4"),
            entry("coder_round", 3, "Coder", round="2/4"),
            entry("coder_round", 3, "Coder", round="3/4"),
        ])
        r = run_route(self.ws, 3)
        self.assert_action(r, "CODER 3 4")

    def test_four_coder_rounds_emits_arbitrate(self):
        self.ledger([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("coder_round", 3, "Coder", round="1/4"),
            entry("coder_round", 3, "Coder", round="2/4"),
            entry("coder_round", 3, "Coder", round="3/4"),
            entry("coder_round", 3, "Coder", round="4/4"),
        ])
        r = run_route(self.ws, 3)
        self.assert_action(r, "ARBITRATE 3")


class TestRouteNextUsage(RouteNextTestBase):
    def test_missing_workspace_is_usage_error(self):
        r = run_route(pathlib.Path(self._tmp) / "nonexistent", 3)
        self.assertEqual(r.returncode, 2)

    def test_missing_args_is_usage_error(self):
        r = subprocess.run([BASH, str(SCRIPTS / "route-next")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()