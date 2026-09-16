"""Tests for the benchmark side-runner (run-side).

The runner is exercised against a stub engine: a throwaway git repo whose
``skills/two-model-sdd-pipeline/scripts/run-pipeline`` writes a minimal
workspace and exits with a controllable code. This proves the runner's own
mechanics -- engine worktree from a ref, clean scratch fixture repo, exact
command construction (including ``--max-parallel``), timing capture, result
file, and exit-code propagation -- without invoking the real pipeline.
"""
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

BENCH = pathlib.Path(__file__).resolve().parent.parent
RUN_SIDE = BENCH / "scripts" / "run-side"
PLAN_NAME = "2026-09-16-parallelism-benchmark-plan.json"

if os.name == "nt":
    git_bash = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
    BASH = str(git_bash) if git_bash.exists() else "bash"
else:
    BASH = "bash"

STUB_ENGINE = """#!/usr/bin/env bash
set -euo pipefail
mkdir -p ".superpowers/two-model/stubws"
ledger=".superpowers/two-model/stubws/ledger.jsonl"
printf '%s\\n' '{"ts":"2026-09-16T00:00:00Z","type":"gate","task":"-"}' > "$ledger"
printf '%s\\n' '{"ts":"2026-09-16T00:00:05Z","type":"task_complete","task":"1","summary":"done"}' >> "$ledger"
exit "${BENCH_STUB_EXIT:-0}"
"""

# Simulates the real parallel flow: the coder log lives in the task worktree
# and the worktree is deleted on release, so only a harvester can see it.
STUB_ENGINE_WITH_WORKTREE = """#!/usr/bin/env bash
set -euo pipefail
mkdir -p ".superpowers/two-model/stubws"
ledger=".superpowers/two-model/stubws/ledger.jsonl"
printf '%s\\n' '{"ts":"2026-09-16T00:00:00Z","type":"gate","task":"-"}' > "$ledger"
wt=".superpowers/two-model/worktrees/task-1/.superpowers/two-model/stubws"
mkdir -p "$wt"
printf '%s\\n' '{"type":"step_finish","timestamp":1000,"tokens":{"input":7}}' > "$wt/task-1-coder.log"
sleep 5
rm -rf ".superpowers/two-model/worktrees"
printf '%s\\n' '{"ts":"2026-09-16T00:00:05Z","type":"task_complete","task":"1","summary":"done"}' >> "$ledger"
exit 0
"""


class RunSideTest(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="bench-run-side-"))
        self.engine = self._tmp / "engine-repo"
        self.engine.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(self.engine), check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"],
                       cwd=str(self.engine), check=True)
        subprocess.run(["git", "config", "user.name", "Test"],
                       cwd=str(self.engine), check=True)
        script_dir = self.engine / "skills" / "two-model-sdd-pipeline" / "scripts"
        script_dir.mkdir(parents=True)
        script = script_dir / "run-pipeline"
        script.write_text(STUB_ENGINE, encoding="utf-8", newline="\n")
        subprocess.run(["git", "add", "-A"], cwd=str(self.engine), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "stub engine"],
                       cwd=str(self.engine), check=True)
        self.work = self._tmp / "work"

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def run_side(self, *extra, env_extra=None):
        env = dict(os.environ)
        env.update(env_extra or {})
        return subprocess.run(
            [BASH, str(RUN_SIDE),
             "--engine-repo", str(self.engine),
             "--engine-ref", "HEAD",
             "--work-dir", str(self.work),
             "--side", extra[0] if extra else "serial",
             *extra[1:]],
            capture_output=True, text=True, env=env,
        )

    def result(self):
        return json.loads((self.work / "result.json").read_text(encoding="utf-8"))

    def test_serial_run_records_result_and_omits_max_parallel(self):
        proc = self.run_side("serial")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = self.result()
        self.assertEqual(result["side"], "serial")
        self.assertEqual(result["exit_code"], 0)
        self.assertIsNone(result["max_parallel"])
        self.assertNotIn("--max-parallel", result["command"])
        self.assertIn("--no-push", result["command"])
        self.assertGreaterEqual(result["total_seconds"], 0.0)

    def test_parallel_run_passes_max_parallel(self):
        proc = self.run_side("parallel", "--max-parallel", "5")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = self.result()
        self.assertEqual(result["max_parallel"], 5)
        self.assertIn("--max-parallel", result["command"])
        self.assertIn("5", result["command"])

    def test_engine_worktree_is_created_from_the_ref(self):
        self.run_side("serial")
        engine_script = (self.work / "engine" / "skills" /
                         "two-model-sdd-pipeline" / "scripts" / "run-pipeline")
        self.assertTrue(engine_script.is_file())

    def test_scratch_fixture_is_a_fresh_git_repo_with_the_plan(self):
        self.run_side("serial")
        fixture = self.work / "fixture"
        self.assertTrue((fixture / ".git").exists())
        self.assertTrue((fixture / "pubspec.yaml").is_file())
        plan = fixture / "docs" / "superpowers" / "plans" / PLAN_NAME
        self.assertTrue(plan.is_file(), "plan not copied into the fixture")
        head = subprocess.run(["git", "-C", str(fixture), "rev-parse", "HEAD"],
                              capture_output=True, text=True)
        self.assertEqual(head.returncode, 0)

    def test_workspace_is_located_and_recorded(self):
        self.run_side("serial")
        result = self.result()
        self.assertIsNotNone(result["workspace"])
        self.assertTrue((pathlib.Path(result["workspace"]) / "ledger.jsonl").is_file())

    def test_exit_code_is_propagated_and_recorded(self):
        proc = self.run_side("serial", env_extra={"BENCH_STUB_EXIT": "7"})
        self.assertEqual(proc.returncode, 7)
        self.assertEqual(self.result()["exit_code"], 7)

    def test_worktree_logs_are_harvested_before_release(self):
        script = (self.engine / "skills" / "two-model-sdd-pipeline" /
                  "scripts" / "run-pipeline")
        script.write_text(STUB_ENGINE_WITH_WORKTREE, encoding="utf-8", newline="\n")
        subprocess.run(["git", "commit", "-qam", "worktree stub"],
                       cwd=str(self.engine), check=True)
        proc = self.run_side("parallel", "--max-parallel", "2")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        harvested = self.work / "harvest" / "task-1-coder.log"
        self.assertTrue(harvested.is_file(),
                        "worktree log was not harvested before release")
        self.assertIn("step_finish", harvested.read_text(encoding="utf-8"))
        self.assertIn("harvest", self.result()["harvest"])


if __name__ == "__main__":
    unittest.main()
