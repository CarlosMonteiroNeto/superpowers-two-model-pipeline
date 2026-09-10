import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import time
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"

if os.name == "nt":
    git_bash = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
    BASH = str(git_bash) if git_bash.exists() else "bash"
else:
    BASH = "bash"


def entry(etype, task, summary, ts="2026-08-29T12:00:00Z", **extra):
    e = {"ts": ts, "type": etype, "task": str(task), "summary": summary}
    e.update(extra)
    return e


def write_global_ledger(ws, entries):
    p = pathlib.Path(ws) / "ledger.jsonl"
    p.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return p


def run(args):
    return subprocess.run(args, capture_output=True, text=True)


def run_append(ws, etype, task, summary, extra_args=(), use_task_flag=False, task_flag=None):
    ledger = str(pathlib.Path(ws) / "ledger.jsonl")
    cmd = [BASH, str(SCRIPTS / "ledger-append")]
    if use_task_flag:
        cmd += ["--task", str(task_flag)]
    cmd += [ledger, etype, str(task), summary, *extra_args]
    return run(cmd)


def run_route(ws, task, total=None):
    args = [BASH, str(SCRIPTS / "route-next"), str(ws), str(task)]
    if total is not None:
        args.append(str(total))
    return run(args)


class LedgerAppendPartitionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="ledger-partition-")
        self.ws = pathlib.Path(self._tmp) / "ws"
        self.ws.mkdir()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_numeric_task_writes_both_files(self):
        r = run_append(self.ws, "red_check", 3, "RED verified")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        gfile = self.ws / "ledger.jsonl"
        part = self.ws / "ledger-task-3.jsonl"
        self.assertTrue(gfile.exists())
        self.assertTrue(part.exists(), "numeric task must mirror to per-task file")
        g_lines = gfile.read_text(encoding="utf-8").strip().splitlines()
        p_lines = part.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(g_lines), 1)
        self.assertEqual(len(p_lines), 1)
        self.assertEqual(json.loads(g_lines[0]), json.loads(p_lines[0]))
        self.assertEqual(json.loads(p_lines[0])["task"], "3")

    def test_dash_task_writes_global_only(self):
        r = run_append(self.ws, "gate", "-", "auto-detected")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.ws / "ledger.jsonl").exists())
        self.assertFalse((self.ws / "ledger-task--.jsonl").exists())
        self.assertEqual(list(self.ws.glob("ledger-task-*.jsonl")), [])

    def test_explicit_task_flag_mirrors(self):
        r = run_append(self.ws, "review_outcome", 3, "APPROVED", use_task_flag=True, task_flag=3)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.ws / "ledger-task-3.jsonl").exists())


class LedgerMigrateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="ledger-migrate-")
        self.ws = pathlib.Path(self._tmp) / "ws"
        self.ws.mkdir()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_split_keys_by_task_field(self):
        write_global_ledger(self.ws, [
            entry("gate", "-", "gate"),
            entry("brief_ready", 1, "task"),
            entry("red_check", 1, "RED"),
            entry("brief_ready", 2, "task"),
        ])
        r = run([BASH, str(SCRIPTS / "ledger-migrate"), str(self.ws)])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        p1 = self.ws / "ledger-task-1.jsonl"
        p2 = self.ws / "ledger-task-2.jsonl"
        self.assertTrue(p1.exists())
        self.assertTrue(p2.exists())
        self.assertEqual(len(p1.read_text(encoding="utf-8").strip().splitlines()), 2)
        self.assertEqual(len(p2.read_text(encoding="utf-8").strip().splitlines()), 1)
        # "-" entries stay global-only: no partition file for them.
        self.assertFalse((self.ws / "ledger-task--.jsonl").exists())
        # Idempotent: second run rebuilds the same content.
        r2 = run([BASH, str(SCRIPTS / "ledger-migrate"), str(self.ws)])
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertEqual(len(p1.read_text(encoding="utf-8").strip().splitlines()), 2)


class RouteNextPartitionRegressionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="route-partition-regression-")
        self.ws = pathlib.Path(self._tmp) / "ws"
        self.ws.mkdir()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def scenario(self, task=3):
        return [
            entry("brief_ready", task, "task"),
            entry("red_check", task, "RED"),
            entry("coder_round", task, "Coder"),
            entry("commit", task, "Task", commits="a1b2c3"),
        ]

    def test_output_unchanged_before_after_split(self):
        # Global-only workspace (pre-upgrade layout) with noise from other tasks.
        entries = [
            entry("gate", "-", "gate"),
            entry("brief_ready", 1, "t1"),
            entry("review_outcome", 1, "APPROVED"),
            entry("task_complete", 1, "t1"),
            *self.scenario(3),
            entry("brief_ready", 7, "other"),
        ]
        write_global_ledger(self.ws, entries)
        # First call triggers the one-time migration internally.
        r1 = run_route(self.ws, 3)
        self.assertEqual(r1.returncode, 0, r1.stdout + r1.stderr)
        self.assertEqual(r1.stdout.strip(), "REVIEW 3")
        # Partition file must now exist (auto-migrated).
        self.assertTrue((self.ws / "ledger-task-3.jsonl").exists())
        # Second call reads the hot path; output must be identical.
        r2 = run_route(self.ws, 3)
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertEqual(r2.stdout.strip(), r1.stdout.strip())

    def test_send_back_regression_across_split(self):
        entries = [
            *self.scenario(3),
            entry("review_outcome", 3, "SEND_BACK", findings="1"),
        ]
        write_global_ledger(self.ws, entries)
        r1 = run_route(self.ws, 3)
        self.assertEqual(r1.stdout.strip(), "CORRECTIVE 3")
        r2 = run_route(self.ws, 3)
        self.assertEqual(r2.stdout.strip(), "CORRECTIVE 3")


class RouteNextLargeLedgerPerfTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="route-perf-")
        self.base = pathlib.Path(self._tmp)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def make_ws(self, name, prior_tasks, task_entries):
        ws = self.base / name
        ws.mkdir()
        entries = [entry("gate", "-", "gate")]
        for t in range(1, prior_tasks + 1):
            entries += [
                entry("brief_ready", t, "task"),
                entry("red_check", t, "RED"),
                entry("coder_round", t, "Coder", round="1/4"),
                entry("commit", t, "Task", commits="abc"),
                entry("review_outcome", t, "APPROVED"),
                entry("task_complete", t, "Task"),
            ]
        entries += task_entries
        write_global_ledger(ws, entries)
        return ws

    def test_task_201_routing_bounded_and_fast(self):
        target = 201
        current = [
            entry("brief_ready", target, "task"),
            entry("red_check", target, "RED"),
            entry("coder_round", target, "Coder", round="1/4"),
        ]
        ws_small = self.make_ws("ws_small", 0, current)
        ws_large = self.make_ws("ws_large", 200, current)

        r_small = run_route(ws_small, target)
        self.assertEqual(r_small.returncode, 0, r_small.stdout + r_small.stderr)
        sized_start = time.perf_counter()
        r_small2 = run_route(ws_small, target)
        small_dt = time.perf_counter() - sized_start
        self.assertEqual(r_small2.stdout.strip(), "CODER 201")

        # First large call performs the one-time migration (amortized); the
        # perf invariant is the STEADY-STATE hot path after the split.
        r_warm = run_route(ws_large, target)
        self.assertEqual(r_warm.returncode, 0, r_warm.stdout + r_warm.stderr)
        self.assertEqual(r_warm.stdout.strip(), "CODER 201")

        large_start = time.perf_counter()
        r_large = run_route(ws_large, target)
        large_dt = time.perf_counter() - large_start
        self.assertEqual(r_large.returncode, 0, r_large.stdout + r_large.stderr)
        self.assertEqual(r_large.stdout.strip(), "CODER 201")

        # Hot-path input is bounded: per-task file holds only this task's
        # entries even though the global file holds 200 prior tasks.
        part = ws_large / f"ledger-task-{target}.jsonl"
        self.assertTrue(part.exists(), "route-next must migrate/split before routing")
        part_lines = [ln for ln in part.read_text(encoding="utf-8").splitlines() if ln.strip()]
        global_lines = [ln for ln in (ws_large / "ledger.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
        self.assertGreater(len(global_lines), 1000)
        self.assertLessEqual(len(part_lines), 10)

        # Timing must not scale with the 200 prior tasks: generous 10x bound
        # plus an absolute ceiling so the test is stable on slow CI.
        self.assertLess(large_dt, 5.0, f"route-next too slow on large ledger: {large_dt:.2f}s")
        bound = max(small_dt * 10, 0.5)
        self.assertLess(large_dt, bound,
                        f"route-next scales with history: small={small_dt:.3f}s large={large_dt:.3f}s")


if __name__ == "__main__":
    unittest.main()
