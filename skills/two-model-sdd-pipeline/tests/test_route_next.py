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

    def test_red_check_emits_coder(self):
        self.ledger([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
        ])
        r = run_route(self.ws, 3)
        self.assert_action(r, "CODER 3")


class TestRouteNextRounds(RouteNextTestBase):
    def test_coder_rounds_keep_emitting_coder(self):
        """Failed rounds never change the route: RED-verified without a
        commit always routes back to CODER - no counting, no budget."""
        self.ledger([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("coder_round", 3, "Coder"),
        ])
        r = run_route(self.ws, 3)
        self.assert_action(r, "CODER 3")

    def test_many_coder_rounds_still_emit_coder(self):
        self.ledger([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("coder_round", 3, "Coder"),
            entry("coder_round", 3, "Coder"),
            entry("coder_round", 3, "Coder"),
        ])
        r = run_route(self.ws, 3)
        self.assert_action(r, "CODER 3")


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

    def test_many_failed_rounds_never_arbitrate_on_count(self):
        """The Coder loop is unbounded and uncounted: even after many failed
        rounds the router keeps emitting CODER - never ARBITRATE on round
        count. Only TEST_DEFECT (escalated) or a review verdict leaves the
        loop."""
        self.ledger([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("coder_round", 3, "Coder"),
            entry("coder_round", 3, "Coder"),
            entry("coder_round", 3, "Coder"),
            entry("coder_round", 3, "Coder"),
            entry("coder_round", 3, "Coder"),
            entry("coder_round", 3, "Coder"),
        ])
        r = run_route(self.ws, 3)
        self.assert_action(r, "CODER 3")


class TestRouteNextArbitrationResolution(RouteNextTestBase):
    """An arbitration that resolves must be observable to the router, or the
    ARBITRATE action loops forever at Strategic-tier cost."""

    def test_escalation_after_resolution_emits_brief(self):
        self.ledger([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("escalated", 3, "TEST_DEFECT"),
            entry("arbitrate_resolved", 3, "diretor ruled", plan_sha="abc"),
        ])
        r = run_route(self.ws, 3)
        self.assert_action(r, "BRIEF 3")

    def test_review_escalate_after_resolution_emits_brief(self):
        self.ledger([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("commit", 3, "Task", commits="a1b2c3"),
            entry("review_outcome", 3, "ESCALATE"),
            entry("arbitrate_resolved", 3, "diretor ruled"),
        ])
        r = run_route(self.ws, 3)
        self.assert_action(r, "BRIEF 3")

    def test_brief_rescaffolded_after_resolution_falls_through(self):
        """Once the brief is re-scaffolded the pre-ruling escalation is
        consumed: normal flow resumes (no BRIEF loop)."""
        self.ledger([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("escalated", 3, "TEST_DEFECT"),
            entry("arbitrate_resolved", 3, "diretor ruled"),
            entry("brief_ready", 3, "rescaffolded"),
        ])
        r = run_route(self.ws, 3)
        self.assert_action(r, "CODER 3")

    def test_second_escalation_after_resolution_is_human_blocker(self):
        self.ledger([
            entry("brief_ready", 3, "task"),
            entry("escalated", 3, "TEST_DEFECT"),
            entry("arbitrate_resolved", 3, "diretor ruled"),
            entry("escalated", 3, "TEST_DEFECT again"),
        ])
        r = run_route(self.ws, 3)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("did not resolve task 3", r.stderr)


class TestRouteNextScopeViolation(RouteNextTestBase):
    def test_scope_violation_emits_arbitrate(self):
        """C2: an out-of-scope commit attempt escalates to the diretor, exactly
        like TEST_DEFECT - never a silent commit."""
        self.ledger([
            entry("brief_ready", 3, "task"),
            entry("red_check", 3, "RED"),
            entry("scope_violation", 3, "out-of-scope changes"),
        ])
        r = run_route(self.ws, 3)
        self.assert_action(r, "ARBITRATE 3")


class TestRouteNextTaskCount(RouteNextTestBase):
    def test_nested_id_fields_do_not_overcount_tasks(self):
        """The plan task count must come from JSON, not a raw `"id"` grep:
        nested id fields would inflate the count and FINAL_REVIEW would never
        be emitted."""
        plan = {"tasks": [
            {"id": 1, "acceptance": {"id": "inner"}},
            {"id": 2, "acceptance": "done"},
        ]}
        (self.ws / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        self.ledger([
            entry("brief_ready", 2, "task"),
            entry("commit", 2, "Task", commits="a1b2c3"),
            entry("review_outcome", 2, "APPROVED"),
            entry("task_complete", 2, "Task"),
        ])
        r = run_route(self.ws, 2)
        self.assert_action(r, "FINAL_REVIEW")


class TestRouteNextUsage(RouteNextTestBase):
    def test_missing_workspace_is_usage_error(self):
        r = run_route(pathlib.Path(self._tmp) / "nonexistent", 3)
        self.assertEqual(r.returncode, 2)

    def test_missing_args_is_usage_error(self):
        r = subprocess.run([BASH, str(SCRIPTS / "route-next")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()