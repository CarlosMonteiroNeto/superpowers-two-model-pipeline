"""Tests for the benchmark analyzer (bench_report).

The analyzer is the only non-trivial deterministic logic in the benchmark
harness: it turns the pipeline's own artifacts (the per-task dispatch JSON
event logs and the JSONL ledger) into per-stage metrics. These tests drive
it from synthetic artifacts so the expected numbers are hand-derived.
"""
import datetime
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from bench_report import analyze_workspace, render_markdown  # noqa: E402

BASE = datetime.datetime(2026, 9, 16, 10, 0, 0, tzinfo=datetime.timezone.utc)


def ms(seconds):
    """Epoch milliseconds for BASE + `seconds`, so log timestamps and ledger
    ISO timestamps share one clock in the tests."""
    return int((BASE.timestamp() + seconds) * 1000)


def step_finish(ts, inp, out, reasoning, cache_read, cache_write, cost):
    return json.dumps({
        "type": "step_finish",
        "timestamp": ts,
        "sessionID": "ses_test",
        "tokens": {
            "total": inp + out + reasoning + cache_read + cache_write,
            "input": inp,
            "output": out,
            "reasoning": reasoning,
            "cache": {"write": cache_write, "read": cache_read},
        },
        "cost": cost,
    })


def ledger_line(ts, type_, task, summary, **extra):
    entry = {"ts": ts, "type": type_, "task": task, "summary": summary}
    entry.update(extra)
    return json.dumps(entry)


def step_finish_real(ts, inp, out, reasoning, cache_read, cache_write, cost):
    """The shape opencode actually emits: tokens/cost live under `part`."""
    return json.dumps({
        "type": "step_finish",
        "timestamp": ts,
        "sessionID": "ses_test",
        "part": {
            "id": "prt_x",
            "reason": "tool-calls",
            "sessionID": "ses_test",
            "type": "step-finish",
            "tokens": {
                "total": inp + out + reasoning + cache_read + cache_write,
                "input": inp,
                "output": out,
                "reasoning": reasoning,
                "cache": {"write": cache_write, "read": cache_read},
            },
            "cost": cost,
        },
    })


class BenchReportTest(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="bench-report-"))
        self.ws = self._tmp / "ws"
        self.ws.mkdir()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def write(self, name, lines):
        (self.ws / name).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def build_fixture_workspace(self):
        # Task 1: coder (2 API steps, cache warm on the 2nd) + reviewer (1 step).
        self.write("task-1-coder.log", [
            "opencode banner line that is not json",
            '{"type":"step_start","timestamp":%d,"sessionID":"ses_c1"}' % ms(0),
            step_finish(ms(2), 100, 10, 0, 0, 0, 0.001),
            '{"type":"text","timestamp":%d,"sessionID":"ses_c1",'
            '"part":{"type":"text","text":"implementing"}}' % ms(3),
            step_finish(ms(5), 20, 5, 2, 200, 30, 0.002),
        ])
        self.write("task-1-reviewer.log", [
            '{"type":"step_start","timestamp":%d,"sessionID":"ses_r1"}' % ms(10),
            step_finish(ms(14), 50, 8, 0, 0, 0, 0.0005),
        ])
        # Task 2: coder only (1 step); review sent it back.
        self.write("task-2-coder.log", [
            step_finish(ms(200), 10, 1, 0, 90, 0, 0.0001),
        ])
        self.write("ledger.jsonl", [
            ledger_line("2026-09-16T10:00:00Z", "gate", "-", "gate"),
            ledger_line("2026-09-16T10:00:10Z", "brief_ready", "1", "b1"),
            ledger_line("2026-09-16T10:00:20Z", "red_check", "1", "red"),
            ledger_line("2026-09-16T10:00:25Z", "coder_round", "1", "r1",
                        STATUS="DONE", ROUND="1"),
            ledger_line("2026-09-16T10:02:00Z", "commit", "1", "green",
                        commits="abc1234"),
            ledger_line("2026-09-16T10:02:05Z", "review_outcome", "1", "APPROVED",
                        verdict="APPROVED", findings="0"),
            ledger_line("2026-09-16T10:02:06Z", "task_complete", "1", "done"),
            ledger_line("2026-09-16T10:03:00Z", "brief_ready", "2", "b2"),
            ledger_line("2026-09-16T10:03:10Z", "red_check", "2", "red"),
            ledger_line("2026-09-16T10:03:15Z", "coder_round", "2", "r1",
                        STATUS="DONE", ROUND="1"),
            ledger_line("2026-09-16T10:04:00Z", "commit", "2", "green",
                        commits="def5678"),
            ledger_line("2026-09-16T10:04:05Z", "coder_round", "2", "r2",
                        STATUS="DONE", ROUND="2"),
            ledger_line("2026-09-16T10:05:00Z", "review_outcome", "2", "SEND_BACK",
                        verdict="SEND_BACK", findings="1"),
            ledger_line("2026-09-16T10:06:00Z", "task_complete", "2", "done"),
        ])

    def test_role_token_totals_requests_and_span(self):
        self.build_fixture_workspace()
        result = analyze_workspace(str(self.ws))

        coder = result["roles"]["coder"]
        self.assertEqual(coder["input"], 130)
        self.assertEqual(coder["output"], 16)
        self.assertEqual(coder["reasoning"], 2)
        self.assertEqual(coder["cache_read"], 290)
        self.assertEqual(coder["cache_write"], 30)
        self.assertEqual(coder["requests"], 3)
        self.assertAlmostEqual(coder["cost"], 0.0031, places=6)

        reviewer = result["roles"]["reviewer"]
        self.assertEqual(reviewer["input"], 50)
        self.assertEqual(reviewer["output"], 8)
        self.assertEqual(reviewer["requests"], 1)

    def test_max_parallel_is_ignored_by_analyzer(self):
        self.build_fixture_workspace()
        result = analyze_workspace(str(self.ws))
        self.assertEqual(result["totals"]["cache_read"], 290)
        self.assertEqual(result["totals"]["input"], 180)
        self.assertEqual(result["totals"]["requests"], 4)
        self.assertAlmostEqual(result["totals"]["cost"], 0.0036, places=6)

    def test_cache_hit_pct_and_uncached_tokens(self):
        self.build_fixture_workspace()
        result = analyze_workspace(str(self.ws))
        # 290 / (290 + 180) * 100
        self.assertAlmostEqual(result["cache_hit_pct"], 61.7, places=1)
        # input + output + reasoning
        self.assertEqual(result["uncached_tokens"], 180 + 24 + 2)

    def test_per_task_metrics_and_correction_rounds(self):
        self.build_fixture_workspace()
        result = analyze_workspace(str(self.ws))
        tasks = {t["id"]: t for t in result["tasks"]}

        one = tasks[1]
        self.assertEqual(one["status"], "APPROVED")
        self.assertEqual(one["correction_rounds"], 0)
        self.assertEqual(one["roles"]["coder"]["requests"], 2)
        self.assertEqual(one["roles"]["reviewer"]["requests"], 1)

        two = tasks[2]
        self.assertEqual(two["status"], "SEND_BACK")
        self.assertEqual(two["correction_rounds"], 1)
        self.assertEqual(two["roles"]["coder"]["requests"], 1)

    def test_stage_durations_from_ledger(self):
        self.build_fixture_workspace()
        result = analyze_workspace(str(self.ws))
        one = result["tasks"][0]
        # brief: brief_ready 10:00:10 -> red_check 10:00:20
        self.assertAlmostEqual(one["brief_s"], 10.0, places=3)
        # gate: coder dispatch ended at ms(5) -> commit at 10:02:00
        self.assertAlmostEqual(one["gate_s"], 115.0, places=3)
        # operador span: first event ms(0) -> last ms(5)
        self.assertAlmostEqual(one["roles"]["coder"]["span_s"], 5.0, places=3)

    def test_role_spans_are_summed_across_tasks(self):
        self.build_fixture_workspace()
        result = analyze_workspace(str(self.ws))
        # coder: task1 span 5.0 + task2 span 0.0
        self.assertAlmostEqual(result["roles"]["coder"]["span_s"], 5.0, places=3)
        # reviewer: task1 span 4.0
        self.assertAlmostEqual(result["roles"]["reviewer"]["span_s"], 4.0, places=3)

    def test_total_wall_clock_falls_back_to_ledger_span(self):
        self.build_fixture_workspace()
        result = analyze_workspace(str(self.ws))
        # 10:00:00 -> 10:06:00
        self.assertAlmostEqual(result["total_wall_clock_s"], 360.0, places=3)

    def test_explicit_total_overrides_ledger_span(self):
        self.build_fixture_workspace()
        result = analyze_workspace(str(self.ws), total_seconds=12.5)
        self.assertAlmostEqual(result["total_wall_clock_s"], 12.5, places=3)

    def test_missing_log_is_zeroed_not_fatal(self):
        self.build_fixture_workspace()
        result = analyze_workspace(str(self.ws))
        two = result["tasks"][1]
        self.assertEqual(two["roles"]["reviewer"]["requests"], 0)
        self.assertEqual(two["roles"]["reviewer"]["input"], 0)

    def test_markdown_reports_headline_metrics(self):
        self.build_fixture_workspace()
        result = analyze_workspace(str(self.ws), total_seconds=42.0)
        md = render_markdown(result)
        self.assertIn("cache", md.lower())
        self.assertIn("requests", md.lower())
        self.assertIn("42.0", md)

    def test_missing_ledger_is_an_error(self):
        with self.assertRaises(OSError):
            analyze_workspace(str(self.ws))

    def test_tokens_are_read_from_the_nested_part_object(self):
        # opencode emits tokens/cost inside `part`, not at the event top level.
        self.write("task-7-coder.log", [
            step_finish_real(1000, 185, 90, 0, 17280, 0, 0.00013359),
            step_finish_real(4000, 552, 170, 7, 17536, 0, 0.000241608),
        ])
        self.write("ledger.jsonl", [
            ledger_line("2026-09-16T10:00:00Z", "task_complete", "7", "done"),
        ])
        result = analyze_workspace(str(self.ws))
        coder = result["tasks"][0]["roles"]["coder"]
        self.assertEqual(coder["input"], 185 + 552)
        self.assertEqual(coder["output"], 90 + 170)
        self.assertEqual(coder["reasoning"], 7)
        self.assertEqual(coder["cache_read"], 17280 + 17536)
        self.assertEqual(coder["requests"], 2)
        self.assertAlmostEqual(coder["cost"], 0.00013359 + 0.000241608, places=8)

    def test_extra_log_dirs_are_read_when_the_workspace_log_is_gone(self):
        # Parallel tasks run in worktrees; their logs are harvested elsewhere
        # before the worktree is released, so the analyzer must read the
        # harvest dir when the integration workspace has no task log.
        harvest = self._tmp / "harvest"
        harvest.mkdir()
        (harvest / "task-9-coder.log").write_text(
            step_finish(ms(0), 111, 22, 3, 333, 0, 0.01) + "\n",
            encoding="utf-8",
        )
        (harvest / "task-9-reviewer.log").write_text(
            step_finish(ms(5), 44, 4, 0, 55, 0, 0.002) + "\n",
            encoding="utf-8",
        )
        self.write("ledger.jsonl", [
            ledger_line("2026-09-16T10:00:00Z", "task_complete", "9", "done"),
        ])
        result = analyze_workspace(str(self.ws), extra_log_dirs=[str(harvest)])
        task = result["tasks"][0]
        self.assertEqual(task["roles"]["coder"]["input"], 111)
        self.assertEqual(task["roles"]["coder"]["requests"], 1)
        self.assertEqual(task["roles"]["reviewer"]["input"], 44)

    def test_workspace_log_wins_over_extra_log_dirs(self):
        harvest = self._tmp / "harvest"
        harvest.mkdir()
        (harvest / "task-1-coder.log").write_text(
            step_finish(ms(0), 999, 0, 0, 0, 0, 0.0) + "\n", encoding="utf-8")
        self.build_fixture_workspace()
        result = analyze_workspace(str(self.ws), extra_log_dirs=[str(harvest)])
        coder = {t["id"]: t for t in result["tasks"]}[1]["roles"]["coder"]
        # the workspace's own task-1-coder.log is the authoritative one
        self.assertEqual(coder["input"], 120)


if __name__ == "__main__":
    unittest.main()
