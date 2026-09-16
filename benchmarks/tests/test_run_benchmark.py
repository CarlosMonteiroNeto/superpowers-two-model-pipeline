"""Tests for the benchmark orchestrator (run-benchmark) with a stub engine.

Proves the orchestrator wires run-side + report + compare together with the
correct script locations, runs sides sequentially, and produces the reports
in the results dir (a missing script path is the class of bug this guards).
"""
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

BENCH = pathlib.Path(__file__).resolve().parent.parent
RUN_BENCHMARK = BENCH / "run-benchmark"

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
exit 0
"""


class RunBenchmarkTest(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="bench-orch-"))
        self.engine = self._tmp / "engine-repo"
        self.engine.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(self.engine), check=True)
        subprocess.run(["git", "config", "user.email", "t@e.com"],
                       cwd=str(self.engine), check=True)
        subprocess.run(["git", "config", "user.name", "T"],
                       cwd=str(self.engine), check=True)
        script_dir = self.engine / "skills" / "two-model-sdd-pipeline" / "scripts"
        script_dir.mkdir(parents=True)
        (script_dir / "run-pipeline").write_text(STUB_ENGINE, encoding="utf-8", newline="\n")
        subprocess.run(["git", "add", "-A"], cwd=str(self.engine), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "stub"], cwd=str(self.engine), check=True)
        self.results = self._tmp / "results"

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)
        # The default-engine-repo regression test intentionally uses the real
        # repo's ignored scratch area; clean the bit it creates.
        shutil.rmtree(BENCH.parent / ".superpowers" / "bench" / self.results.name,
                      ignore_errors=True)

    def run_benchmark(self, *args):
        return subprocess.run(
            [BASH, str(RUN_BENCHMARK),
             "--engine-repo", str(self.engine),
             "--results-dir", str(self.results),
             *args],
            capture_output=True, text=True,
        )

    def test_serial_only_produces_report(self):
        proc = self.run_benchmark("--only", "serial", "--serial-ref", "HEAD")
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertTrue((self.results / "serial-result.json").is_file())
        self.assertTrue((self.results / "serial-report.json").is_file())
        md = (self.results / "serial-report.md").read_text(encoding="utf-8")
        self.assertIn("Benchmark report", md)

    def test_parallel_only_passes_max_parallel(self):
        proc = self.run_benchmark("--only", "parallel", "--parallel-ref", "HEAD",
                                  "--max-parallel", "5")
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        result = json.loads((self.results / "parallel-result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["max_parallel"], 5)
        self.assertIn("--max-parallel", result["command"])

    def test_both_sides_then_compare(self):
        first = self.run_benchmark("--only", "serial", "--serial-ref", "HEAD")
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.run_benchmark("--only", "parallel", "--parallel-ref", "HEAD")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertTrue((self.results / "compare.json").is_file())
        md = (self.results / "compare.md").read_text(encoding="utf-8")
        self.assertIn("speedup", md.lower())

    def test_default_engine_repo_resolves_to_a_git_repo(self):
        # Regression: BENCH_DIR sits at benchmarks/, so ENGINE_REPO must be its
        # parent. A bogus ref must fail at the worktree step, never with
        # "not a git repo" (which would mean ENGINE_REPO resolved too high).
        proc = subprocess.run(
            [BASH, str(RUN_BENCHMARK), "--results-dir", str(self.results),
             "--only", "serial",
             "--serial-ref", "0000000000000000000000000000000000000000"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotIn("not a git repo", proc.stderr)


if __name__ == "__main__":
    unittest.main()
