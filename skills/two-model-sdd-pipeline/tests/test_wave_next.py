import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
PY = sys.executable


class WaveNextTest(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="wave-next-"))
        self.ws = self._tmp / "ws"
        self.ws.mkdir()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def write(self, tasks, ledger):
        (self.ws / "plan.json").write_text(
            json.dumps({"feature": "f", "tasks": tasks}), encoding="utf-8")
        (self.ws / "ledger.jsonl").write_text(
            "\n".join(json.dumps(e) for e in ledger) + ("\n" if ledger else ""),
            encoding="utf-8")

    def run_it(self, *args):
        return subprocess.run(
            [PY, str(SCRIPTS / "wave-next"), str(self.ws), *map(str, args)],
            capture_output=True, text=True)

    @staticmethod
    def done(n):
        return [{"ts": "t", "type": "task_complete", "task": str(n), "summary": "APPROVED"}]

    def tasks(self, *specs):
        return [{"id": i, "touches": t, "depends_on": d} for i, t, d in specs]

    def test_all_complete_emits_final_review(self):
        self.write(self.tasks((1, ["a"], [])), self.done(1))
        r = self.run_it()
        self.assertEqual(r.returncode, 0)
        self.assertIn("FINAL_REVIEW", r.stdout)

    def test_blocked_when_depends_on_unsatisfied(self):
        self.write(self.tasks((1, ["a"], [2]), (2, ["b"], [1])), [])
        r = self.run_it()
        self.assertEqual(r.returncode, 1)
        self.assertIn("WAVE_EMPTY", r.stderr)

    def test_independent_tasks_run_together(self):
        self.write(self.tasks((1, ["a"], []), (2, ["b"], []), (3, ["c"], [])), [])
        r = self.run_it(2)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), ["RUN", "1", "RUN", "2"])

    def test_overlapping_touches_defer_next_wave(self):
        self.write(self.tasks((1, ["shared"], []), (2, ["shared"], [])), [])
        r = self.run_it(2)
        self.assertEqual(r.stdout.split(), ["RUN", "1"])

    def test_overlap_deferral_reason_is_printed(self):
        """A collapsed wave must be observable: the scheduler says which task
        it dropped and which file caused it."""
        self.write(self.tasks((1, ["shared"], []), (2, ["shared"], [])), [])
        r = self.run_it(2)
        self.assertEqual(r.stdout.split(), ["RUN", "1"])
        self.assertIn("WAVE-DEFER: task 2 deferred", r.stderr)
        self.assertIn("shared", r.stderr)

    def test_fewest_touches_first_yields_a_larger_wave(self):
        """Selection is fewest-touches-first: a wide low-id task must not wall
        out a schedulable pair. Lowest-id-first would emit only task 1 here;
        tasks 2 and 3 are disjoint and should run together."""
        self.write([
            {"id": 1, "touches": ["a", "b"], "depends_on": []},
            {"id": 2, "touches": ["a"], "depends_on": []},
            {"id": 3, "touches": ["b"], "depends_on": []},
        ], [])
        r = self.run_it(3)
        self.assertEqual(r.stdout.split(), ["RUN", "2", "RUN", "3"])

    def test_deferred_task_picked_once_dependency_done(self):
        self.write(self.tasks((1, ["a"], []), (2, ["b"], [1])), self.done(1))
        r = self.run_it(2)
        self.assertEqual(r.stdout.split(), ["RUN", "2"])

    def test_corrective_runs_alone(self):
        tasks = [
            {"id": 1, "touches": ["a"], "depends_on": []},
            {"id": 2, "touches": ["b"], "depends_on": []},
            {"id": 3, "touches": ["c"], "depends_on": [], "corrects": 1},
        ]
        self.write(tasks, [])
        r = self.run_it(2)
        self.assertEqual(r.stdout.split(), ["RUN", "3"])

    def test_integration_failed_reopens_task(self):
        ledger = self.done(1) + [
            {"ts": "t", "type": "integration_failed", "task": "1", "summary": "gates"}]
        self.write(self.tasks((1, ["a"], [])), ledger)
        r = self.run_it()
        self.assertEqual(r.stdout.split(), ["RUN", "1"])

    def test_usage(self):
        r = subprocess.run([PY, str(SCRIPTS / "wave-next")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
