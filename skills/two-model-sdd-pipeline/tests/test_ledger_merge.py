import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
PY = sys.executable


def entry(**kw):
    base = {"ts": "t", "type": "x", "task": "-", "summary": "s"}
    base.update(kw)
    return base


class LedgerMergeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="ledger-merge-"))
        self.ws = self._tmp / "ws"
        self.ws.mkdir()
        (self.ws / "ledger.jsonl").write_text(
            "\n".join(json.dumps(e) for e in [
                entry(type="gate", task="-", summary="go", lang="go",
                      test_cmd="true", analyze_cmd="true"),
                entry(type="brief_ready", task="3", summary="brief scaffolded from plan"),
            ]) + "\n", encoding="utf-8")
        self.shard = self._tmp / "shard.jsonl"
        (self.shard).write_text(
            "\n".join(json.dumps(e) for e in [
                entry(type="gate", task="-", summary="go", lang="go",
                      test_cmd="true", analyze_cmd="true"),
                entry(type="red_check", task="3", summary="dispatching operador"),
                entry(type="commit", task="3", summary="green abc1234", commits="abc1234"),
                entry(type="review_outcome", task="3", summary="APPROVED", findings="0"),
                entry(type="task_complete", task="3", summary="APPROVED"),
            ]) + "\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def run_it(self, *sources):
        return subprocess.run(
            [PY, str(SCRIPTS / "ledger-merge"), str(self.ws), *map(str, sources)],
            capture_output=True, text=True)

    def lines(self):
        return [json.loads(l) for l in
                (self.ws / "ledger.jsonl").read_text(encoding="utf-8").splitlines() if l]

    def test_merges_missing_entries_and_skips_gate(self):
        r = self.run_it(self.shard)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        types = [(e["type"], e["task"]) for e in self.lines()]
        self.assertEqual(types.count(("gate", "-")), 1)          # not duplicated
        self.assertIn(("red_check", "3"), types)
        self.assertIn(("task_complete", "3"), types)

    def test_partition_rebuilt(self):
        self.run_it(self.shard)
        part = self.ws / "ledger-task-3.jsonl"
        self.assertTrue(part.is_file())
        self.assertIn("task_complete",
                      part.read_text(encoding="utf-8"))

    def test_idempotent(self):
        self.run_it(self.shard)
        before = len(self.lines())
        self.run_it(self.shard)
        self.assertEqual(len(self.lines()), before)

    def test_usage(self):
        r = subprocess.run([PY, str(SCRIPTS / "ledger-merge")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_non_dict_destination_line_is_skipped(self):
        (self.ws / "ledger.jsonl").write_text(
            "5\n" + json.dumps(
                entry(type="brief_ready", task="3", summary="scaffolded")) + "\n",
            encoding="utf-8")
        r = self.run_it(self.shard)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        types = [(e["type"], e["task"]) for e in self.lines() if isinstance(e, dict)]
        self.assertIn(("red_check", "3"), types)
        self.assertIn(("task_complete", "3"), types)

    def test_append_failure_reports_and_exits_one(self):
        not_dir = self._tmp / "ws-as-file"
        not_dir.write_text("not a directory\n", encoding="utf-8")
        r = subprocess.run(
            [PY, str(SCRIPTS / "ledger-merge"), str(not_dir), str(self.shard)],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("failed to append", r.stderr)
        self.assertIn("LEDGER-MERGE: merged", r.stdout)


if __name__ == "__main__":
    unittest.main()
