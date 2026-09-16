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


# Complete task per design §3: acceptance-driven, no expected_red.
FULL_TASK = {
    "id": 1, "title": "Add the target widget", "summary": "Add the widget.",
    "spec_refs": ["§9.7"], "touches": ["lib/a.go"], "depends_on": [],
    "acceptance": ["thing exists"],
}


class RunPipelineTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="run-pipeline-"))
        self.repo = self._tmp / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(self.repo), check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"],
                       cwd=str(self.repo), check=True)
        subprocess.run(["git", "config", "user.name", "Test"],
                       cwd=str(self.repo), check=True)
        (self.repo / "lib").mkdir()
        (self.repo / "lib" / "a.go").write_text("package a\n", encoding="utf-8")
        (self.repo / "docs" / "superpowers" / "plans").mkdir(parents=True)
        subprocess.run(["git", "add", "-A"], cwd=str(self.repo), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=str(self.repo), check=True)
        self.plan = self.repo / "docs" / "superpowers" / "plans" / "plan.json"
        self.stub_dir = self._tmp / "stubs"
        self.stub_dir.mkdir()
        self.dispatch_log = self._tmp / "dispatch.log"

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def ws(self):
        # L3: pipeline-workspace strips the plan's extension, so a
        # `plan.json` plan yields the `plan` workspace directory.
        return self.repo / ".superpowers" / "two-model" / "plan"

    def write_plan(self, tasks):
        self.plan.write_text(json.dumps({"feature": "t", "tasks": tasks}),
                             encoding="utf-8")

    def write_gate(self, *extra):
        ws = self.ws()
        ws.mkdir(parents=True, exist_ok=True)
        entries = [{"ts": "x", "type": "gate", "task": "-",
                    "summary": "go", "lang": "go",
                    "test_cmd": "true", "analyze_cmd": "true"}]
        entries.extend(extra)
        (ws / "ledger.jsonl").write_text(
            "".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")

    def fake_dispatch(self):
        return write_stub(
            self.stub_dir, "dispatch",
            """
echo "$*" >> "${STUB_DISPATCH_LOG:?}"
exit 0
""",
        )

    def fake_capture_fail(self):
        # Records the dispatch argv and the prompt file contents, then fails
        # so run-pipeline stops right after the task-generator dispatch
        # (bounded observations for prompt/context assertions).
        return write_stub(
            self.stub_dir, "dispatch-capture",
            """
log="${STUB_DISPATCH_LOG:?}"
{
  echo "CALL $*"
  prompt=""
  prev=""
  for a in "$@"; do
    if [ "$prev" = "--prompt-file" ]; then prompt=$a; fi
    prev=$a
  done
  if [ -n "$prompt" ] && [ -f "$prompt" ]; then
    echo "PROMPT-BEGIN"
    cat "$prompt"
    echo "PROMPT-END"
  fi
} >> "$log"
exit 1
""",
        )

    def fake_red_gate(self):
        # Simulates one full green task: ledgers the entries Script CEO
        # would produce (through the real ledger-append, so per-task
        # partitions mirror like production) and leaves a parseable
        # reviewer log.
        return write_stub(
            self.stub_dir, "red-gate",
            """
ws=$1; task=$2
ledger="$ws/ledger.jsonl"
append="${LEDGER_APPEND_BIN:?}"
sha=$(git rev-parse --short HEAD)
"$append" "$ledger" red_check "$task" "RED"
"$append" "$ledger" commit "$task" "green" "commits=$sha"
printf '{"type":"text","part":{"type":"text","text":"working"}}\\n' > "$ws/task-$task-reviewer.log"
printf '{"verdict":"APPROVED","findings":[],"minors":[],"summary":"ok"}\\n' >> "$ws/task-$task-reviewer.log"
"$append" "$ledger" review_outcome "$task" "APPROVED" "findings=0"
"$append" "$ledger" task_complete "$task" "APPROVED"
exit 0
""",
        )

    def fake_red_gate_committing(self):
        # Wave-path gate stub: unlike fake_red_gate it makes a REAL commit
        # (its cwd is the task worktree), so integrate has something to merge
        # and the integration HEAD can be asserted to carry each task.
        return write_stub(
            self.stub_dir, "red-gate-committing",
            """
ws=$1; task=$2
append="${LEDGER_APPEND_BIN:?}"
[ -n "${STUB_PLAN_LOG:-}" ] && printf '%s\\n' "${PLAN:-}" >> "$STUB_PLAN_LOG"
mkdir -p wave
printf 'task %s\\n' "$task" > "wave/task-$task.txt"
git add "wave/task-$task.txt"
git commit -q -m "task $task"
sha=$(git rev-parse --short HEAD)
"$append" "$ws/ledger.jsonl" red_check "$task" "RED"
"$append" "$ws/ledger.jsonl" commit "$task" "green" "commits=$sha"
printf '{"type":"text","part":{"type":"text","text":"working"}}\\n' > "$ws/task-$task-reviewer.log"
printf '{"verdict":"APPROVED","findings":[],"minors":[],"summary":"ok"}\\n' >> "$ws/task-$task-reviewer.log"
"$append" "$ws/ledger.jsonl" review_outcome "$task" "APPROVED" "findings=0"
"$append" "$ws/ledger.jsonl" task_complete "$task" "APPROVED"
exit 0
""",
        )

    def fake_integrate_fail(self):
        # Stub integrator: ledgers integration_failed for every task it was
        # handed (exactly what the real integrate does on conflict/gate-red/
        # commit failure) and exits 1. The driver must then attempt bounded
        # recovery, not re-emit the task forever.
        return write_stub(
            self.stub_dir, "integrate-fail",
            """
ws=$1; shift
append="${LEDGER_APPEND_BIN:?}"
for n in "$@"; do
  "$append" "$ws/ledger.jsonl" integration_failed "$n" "stub failure"
done
exit 1
""",
        )

    def fake_red_gate_send_back(self):
        # Simulates task 1 going green then being SEND_BACK by the revisor:
        # commit + a SEND_BACK review_outcome (route-next reads the verdict
        # and emits CORRECTIVE without a REVIEW round).
        return write_stub(
            self.stub_dir, "red-gate-send-back",
            """
ws=$1; task=$2
append="${LEDGER_APPEND_BIN:?}"
sha=$(git rev-parse --short HEAD)
"$append" "$ws/ledger.jsonl" red_check "$task" "RED"
"$append" "$ws/ledger.jsonl" commit "$task" "green" "commits=$sha"
"$append" "$ws/ledger.jsonl" review_outcome "$task" "SEND_BACK" "findings=1"
exit 0
""",
        )

    def fake_coder_gate_committed(self):
        # The corrective task goes green: commit only. The run-pipeline
        # REVIEW handler records the verdict from the (pre-written)
        # task-2-reviewer.log reviewer event stream.
        return write_stub(
            self.stub_dir, "coder-gate-committed",
            """
ws=$1; task=$2
append="${LEDGER_APPEND_BIN:?}"
sha=$(git rev-parse --short HEAD)
"$append" "$ws/ledger.jsonl" commit "$task" "green" "commits=$sha"
exit 0
""",
        )

    def write_reviewer_log(self, task, verdict):
        event = {
            "type": "text",
            "part": {
                "type": "text",
                "text": json.dumps({
                    "verdict": verdict, "findings": [], "minors": [],
                    "summary": "ok",
                }),
            },
        }
        (self.ws() / ("task-%s-reviewer.log" % task)).write_text(
            json.dumps(event) + "\n", encoding="utf-8")

    def run_pipeline(self, *args, **extra_env):
        # `_timeout` is a test-only knob (not an env var): it guards against a
        # regression that turns a failure path into an unbounded loop, which
        # must fail as a TimeoutExpired error, never hang the suite.
        timeout = extra_env.pop("_timeout", 30)
        env = dict(os.environ)
        env.update(extra_env)
        out = self._tmp / "run-pipeline.out"
        err = self._tmp / "run-pipeline.err"
        with open(out, "w", encoding="utf-8") as fo, \
                open(err, "w", encoding="utf-8") as fe:
            proc = subprocess.Popen(
                [BASH, str(SCRIPTS / "run-pipeline"), str(self.plan), *args],
                stdout=fo, stderr=fe, cwd=str(self.repo), env=env,
            )
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                raise
        result = subprocess.CompletedProcess(
            args=args, returncode=proc.returncode,
            stdout=out.read_text(encoding="utf-8", errors="replace"),
            stderr=err.read_text(encoding="utf-8", errors="replace"),
        )
        return result


class TestRunPipelineFlow(RunPipelineTestBase):
    def test_full_branch_to_closing_no_push(self):
        """Acceptance: a complete plan without expected_red runs with no
        expand dispatch, and closing builds the curated package and
        dispatches the task-generator once."""
        self.write_plan([dict(FULL_TASK)])
        self.write_gate()
        r = self.run_pipeline(
            "--no-push",
            "--max-parallel", "1",
            RED_GATE_BIN=self.fake_red_gate(),
            DISPATCH_BIN=self.fake_dispatch(),
            STUB_DISPATCH_LOG=str(self.dispatch_log),
            LEDGER_APPEND_BIN=str(SCRIPTS / "ledger-append"),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ws = self.ws()
        ledger_text = (ws / "ledger.jsonl").read_text(encoding="utf-8")
        for want in ("brief_ready", "task_complete", "final_review"):
            self.assertIn(want, ledger_text)
        self.assertTrue((ws / "closing-review.diff").exists())
        dcalls = self.dispatch_log.read_text(encoding="utf-8")
        self.assertNotIn("EXPAND", dcalls)
        # Complete plan: exactly one task-generator dispatch, the closing one.
        self.assertEqual(dcalls.count("two-model-task-generator"), 1,
                         dcalls)
        self.assertIn("FINAL_REVIEW", r.stdout)

    def test_send_back_episode_reaches_final_review(self):
        """Regression: a SEND_BACK on task 1 must route its pre-seeded
        corrective task 2 to review, reconcile task 1, and reach FINAL_REVIEW
        - never loop on CORRECTIVE 1 forever. The corrective episode must
        complete: both tasks end with task_complete and an APPROVED last
        review."""
        corrective = {
            "id": 2, "title": "Fix task 1", "summary": "Corrective for 1.",
            "spec_refs": ["§9.7"], "touches": ["lib/b.go"], "depends_on": [1],
            "acceptance": ["thing fixed"], "corrects": 1,
        }
        self.write_plan([dict(FULL_TASK), corrective])
        self.write_gate()
        (self.ws() / "task-1-review.json").write_text(
            json.dumps({"verdict": "SEND_BACK", "findings": ["weak tests"],
                        "minors": [], "summary": "x"}),
            encoding="utf-8")
        self.write_reviewer_log(2, "APPROVED")
        r = self.run_pipeline(
            "--no-push",
            "--max-parallel", "1",
            RED_GATE_BIN=self.fake_red_gate_send_back(),
            CODER_GATE_BIN=self.fake_coder_gate_committed(),
            DISPATCH_BIN=self.fake_dispatch(),
            STUB_DISPATCH_LOG=str(self.dispatch_log),
            LEDGER_APPEND_BIN=str(SCRIPTS / "ledger-append"),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("FINAL_REVIEW", r.stdout)
        entries = [
            json.loads(line)
            for line in (self.ws() / "ledger.jsonl").read_text(
                encoding="utf-8").splitlines()
            if line.strip()
        ]

        def task_entries(tid):
            return [e for e in entries if str(e.get("task")) == tid]

        for tid in ("1", "2"):
            types = [e["type"] for e in task_entries(tid)]
            self.assertIn("task_complete", types,
                          "task %s not complete: %s" % (tid, types))
            reviews = [e["summary"] for e in task_entries(tid)
                       if e["type"] == "review_outcome"]
            self.assertEqual(reviews[-1], "APPROVED",
                             "task %s last review not APPROVED: %s"
                             % (tid, reviews))

    def test_incomplete_plan_blocks_without_expand_dispatch(self):
        """The expand dispatch is removed: a plan whose tasks lack
        acceptance must block, never call the task-generator to fill tasks[]."""
        self.write_plan([{"id": 1, "title": "Thin", "summary": "x"}])
        self.write_gate()
        r = self.run_pipeline(
            "--no-push",
            "--max-parallel", "1",
            DISPATCH_BIN=self.fake_dispatch(),
            STUB_DISPATCH_LOG=str(self.dispatch_log),
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        dispatched = (self.dispatch_log.read_text(encoding="utf-8")
                      if self.dispatch_log.exists() else "")
        self.assertEqual(dispatched.strip(), "", dispatched)

    def _assert_punctual_dispatch(self, verdict):
        self.write_plan([dict(FULL_TASK)])
        self.write_gate({
            "ts": "x", "type": "review_outcome", "task": "1",
            "summary": verdict, "findings": "1",
        })
        (self.ws() / "task-1-review.json").write_text(
            json.dumps({"verdict": verdict, "findings": ["weak"]}),
            encoding="utf-8")
        # A stale cross-task session must never be resumed.
        (self.ws() / "task-0-session.txt").write_text(
            "STALE-SESSION\n", encoding="utf-8")
        self.run_pipeline(
            "--no-push",
            "--max-parallel", "1",
            DISPATCH_BIN=self.fake_capture_fail(),
            STUB_DISPATCH_LOG=str(self.dispatch_log),
        )
        calls = self.dispatch_log.read_text(encoding="utf-8")
        self.assertIn(str(self.plan), calls)
        self.assertIn("Add the target widget", calls)
        self.assertIn("§9.7", calls)
        self.assertNotIn("--continue", calls)
        self.assertNotIn("STALE-SESSION", calls)

    def test_corrective_dispatch_passes_plan_and_target_task(self):
        """Acceptance: a corrective dispatch passes the plan path and the
        target task (with its spec_refs), fresh - no session reuse."""
        self._assert_punctual_dispatch("SEND_BACK")

    def test_arbitrate_dispatch_passes_plan_and_target_task(self):
        """Acceptance: an arbitrate dispatch passes the plan path and the
        target task (with its spec_refs), fresh - no session reuse."""
        self._assert_punctual_dispatch("ESCALATE")

    def test_arbitrate_resolves_once_then_blocks(self):
        """C1: the ARBITRATE branch must ledger an observable resolution and
        terminate - never re-dispatch the task-generator on every iteration."""
        self.write_plan([dict(FULL_TASK)])
        self.write_gate(
            {"ts": "x", "type": "commit", "task": "1", "summary": "green",
             "commits": "deadbeef"},
            {"ts": "x", "type": "review_outcome", "task": "1",
             "summary": "ESCALATE", "findings": "1"},
        )
        self.write_reviewer_log(1, "ESCALATE")
        r = self.run_pipeline(
            "--no-push",
            "--max-parallel", "1",
            DISPATCH_BIN=self.fake_dispatch(),
            STUB_DISPATCH_LOG=str(self.dispatch_log),
            LEDGER_APPEND_BIN=str(SCRIPTS / "ledger-append"),
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("did not resolve task 1", r.stderr)
        entries = [
            json.loads(line)
            for line in (self.ws() / "ledger.jsonl").read_text(
                encoding="utf-8").splitlines()
            if line.strip()
        ]
        resolved = [e for e in entries if e["type"] == "arbitrate_resolved"]
        self.assertEqual(len(resolved), 1, entries)
        self.assertIn("plan_sha", resolved[0])
        dcalls = self.dispatch_log.read_text(encoding="utf-8")
        self.assertEqual(dcalls.count("two-model-task-generator"), 1, dcalls)

    def test_corrective_resumes_operador_session_not_generic(self):
        """L5: the corrective round must resume the operador's own session;
        the generic record points at the reviewer after review."""
        corrective = {
            "id": 2, "title": "Fix task 1", "summary": "Corrective for 1.",
            "spec_refs": ["§9.7"], "touches": ["lib/b.go"], "depends_on": [1],
            "acceptance": ["thing fixed"], "corrects": 1,
        }
        self.write_plan([dict(FULL_TASK), corrective])
        self.write_gate(
            {"ts": "x", "type": "commit", "task": "1", "summary": "green",
             "commits": "deadbeef"},
            {"ts": "x", "type": "review_outcome", "task": "1",
             "summary": "SEND_BACK", "findings": "1"},
        )
        (self.ws() / "task-1-review.json").write_text(
            json.dumps({"verdict": "SEND_BACK", "findings": ["weak"]}),
            encoding="utf-8")
        (self.ws() / "task-1-session.txt").write_text(
            "GENERIC-REVIEWER-SESSION\n", encoding="utf-8")
        (self.ws() / "task-1-two-model-coder-go-session.txt").write_text(
            "OPERADOR-SESSION\n", encoding="utf-8")
        self.write_reviewer_log(2, "APPROVED")
        r = self.run_pipeline(
            "--no-push",
            "--max-parallel", "1",
            DISPATCH_BIN=self.fake_dispatch(),
            CODER_GATE_BIN=self.fake_coder_gate_committed(),
            STUB_DISPATCH_LOG=str(self.dispatch_log),
            LEDGER_APPEND_BIN=str(SCRIPTS / "ledger-append"),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        dcalls = self.dispatch_log.read_text(encoding="utf-8")
        self.assertIn("--continue OPERADOR-SESSION", dcalls)
        self.assertNotIn("GENERIC-REVIEWER-SESSION", dcalls)

    def test_interrupted_red_gate_blocks_loudly(self):
        """5134b05: an interrupted dispatch (provider timeout rc=124) must
        surface as BLOCKED, never a silent EXIT - even now that run-pipeline
        delegates RED to the orchestrator."""
        self.write_plan([dict(FULL_TASK)])
        self.write_gate()
        interrupted = write_stub(self.stub_dir, "red-gate-interrupted",
                                 "exit 124\n")
        r = self.run_pipeline(
            "--no-push",
            "--max-parallel", "1",
            RED_GATE_BIN=interrupted,
            DISPATCH_BIN=self.fake_dispatch(),
            STUB_DISPATCH_LOG=str(self.dispatch_log),
            LEDGER_APPEND_BIN=str(SCRIPTS / "ledger-append"),
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("BLOCKED", r.stderr)

    def test_missing_plan_is_usage(self):
        r = subprocess.run(
            [BASH, str(SCRIPTS / "run-pipeline"), str(self._tmp / "nope.json")],
            capture_output=True, text=True, cwd=str(self.repo),
            env=dict(os.environ),
        )
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_task_run_completes_one_task(self):
        """Task 9: task-run drives exactly one task to APPROVED (exit 0) and
        ledgers task_complete for it - the extracted per-task contract."""
        self.write_plan([dict(FULL_TASK)])
        subprocess.run(
            [BASH, str(SCRIPTS / "pipeline-workspace"), str(self.plan)],
            cwd=str(self.repo), check=True, capture_output=True,
        )
        self.write_gate()
        env = dict(os.environ)
        env.update(
            RED_GATE_BIN=self.fake_red_gate(),
            DISPATCH_BIN=self.fake_dispatch(),
            STUB_DISPATCH_LOG=str(self.dispatch_log),
            LEDGER_APPEND_BIN=str(SCRIPTS / "ledger-append"),
        )
        out = self._tmp / "task-run.out"
        err = self._tmp / "task-run.err"
        with open(out, "w", encoding="utf-8") as fo, \
                open(err, "w", encoding="utf-8") as fe:
            proc = subprocess.run(
                [BASH, str(SCRIPTS / "task-run"), str(self.ws()), "1", "1"],
                stdout=fo, stderr=fe, cwd=str(self.repo), env=env,
            )
        stdout = out.read_text(encoding="utf-8", errors="replace")
        stderr = err.read_text(encoding="utf-8", errors="replace")
        self.assertEqual(proc.returncode, 0, stdout + stderr)
        entries = [
            json.loads(line)
            for line in (self.ws() / "ledger.jsonl").read_text(
                encoding="utf-8").splitlines()
            if line.strip()
        ]
        completes = [e for e in entries
                     if e.get("type") == "task_complete"
                     and str(e.get("task")) == "1"]
        self.assertEqual(len(completes), 1, entries)

    def test_max_parallel_zero_is_usage(self):
        """--max-parallel N must be an integer >= 1: 0 is a usage error."""
        self.write_plan([dict(FULL_TASK)])
        r = self.run_pipeline("--no-push", "--max-parallel", "0")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_max_parallel_non_numeric_is_usage(self):
        """A non-numeric --max-parallel is a usage error (exit 2)."""
        self.write_plan([dict(FULL_TASK)])
        r = self.run_pipeline("--no-push", "--max-parallel", "two")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_max_parallel_1_regression_is_the_serial_path(self):
        """--max-parallel 1 reproduces the pre-wave serial flow: task-run in
        the repo root + route-next advance, no worktrees and no integrate.
        The ledger (type, task) sequence is the pre-change serial order."""
        self.write_plan([dict(FULL_TASK)])
        self.write_gate()
        r = self.run_pipeline(
            "--no-push", "--max-parallel", "1",
            RED_GATE_BIN=self.fake_red_gate(),
            DISPATCH_BIN=self.fake_dispatch(),
            STUB_DISPATCH_LOG=str(self.dispatch_log),
            LEDGER_APPEND_BIN=str(SCRIPTS / "ledger-append"),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("FINAL_REVIEW", r.stdout)
        entries = [
            json.loads(line)
            for line in (self.ws() / "ledger.jsonl").read_text(
                encoding="utf-8").splitlines()
            if line.strip()
        ]
        seq = [(e["type"], str(e.get("task"))) for e in entries]
        self.assertEqual(seq, [
            ("gate", "-"),
            ("brief_ready", "1"),
            ("red_check", "1"),
            ("commit", "1"),
            ("review_outcome", "1"),
            ("task_complete", "1"),
            ("final_review", "-"),
        ])
        for wave_type in ("worktree_alloc", "worktree_release", "integrated",
                          "integration_failed"):
            self.assertNotIn(wave_type, [t for t, _ in seq])
        branches = subprocess.run(
            ["git", "branch", "--list", "task/*"], cwd=str(self.repo),
            capture_output=True, text=True).stdout.strip()
        self.assertEqual(branches, "")

    def test_wave_runs_two_disjoint_tasks_in_parallel(self):
        """--max-parallel 2: two touches-disjoint tasks each run in their own
        worktree, both integrate, and the integration HEAD carries both
        changes; every worktree and task branch is released afterwards."""
        tasks = [
            {"id": 1, "title": "A", "summary": "Add a.", "spec_refs": ["s1"],
             "touches": ["lib/a.go"], "depends_on": [],
             "acceptance": ["a works"]},
            {"id": 2, "title": "B", "summary": "Add b.", "spec_refs": ["s1"],
             "touches": ["lib/b.go"], "depends_on": [],
             "acceptance": ["b works"]},
        ]
        self.write_plan(tasks)
        self.write_gate()
        r = self.run_pipeline(
            "--no-push", "--max-parallel", "2",
            RED_GATE_BIN=self.fake_red_gate_committing(),
            DISPATCH_BIN=self.fake_dispatch(),
            STUB_DISPATCH_LOG=str(self.dispatch_log),
            LEDGER_APPEND_BIN=str(SCRIPTS / "ledger-append"),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        entries = [
            json.loads(line)
            for line in (self.ws() / "ledger.jsonl").read_text(
                encoding="utf-8").splitlines()
            if line.strip()
        ]
        allocs = sorted(str(e["task"]) for e in entries
                        if e["type"] == "worktree_alloc")
        releases = sorted(str(e["task"]) for e in entries
                          if e["type"] == "worktree_release")
        self.assertEqual(allocs, ["1", "2"])
        self.assertEqual(releases, ["1", "2"])
        integrated = sorted(str(e["task"]) for e in entries
                            if e["type"] == "integrated")
        self.assertEqual(integrated, ["1", "2"])
        for n in ("1", "2"):
            content = subprocess.run(
                ["git", "show", "HEAD:wave/task-%s.txt" % n],
                cwd=str(self.repo), capture_output=True, text=True).stdout
            self.assertIn("task %s" % n, content)
        branches = subprocess.run(
            ["git", "branch", "--list", "task/*"], cwd=str(self.repo),
            capture_output=True, text=True).stdout.strip()
        self.assertEqual(branches, "")
        wt_root = self.repo / ".superpowers" / "two-model" / "worktrees"
        leftovers = sorted(p.name for p in wt_root.iterdir()) \
            if wt_root.exists() else []
        self.assertEqual(leftovers, [])

    def test_wave_resume_reuses_an_existing_worktree(self):
        """A re-run after a crash/block must REUSE an already-allocated task
        worktree (worktree-alloc exit 1 still prints WORKTREE=/WS=) instead of
        blocking on it - the same tolerance the bounded-recovery path has."""
        tasks = [
            {"id": 1, "title": "A", "summary": "Add a.", "spec_refs": ["s1"],
             "touches": ["lib/a.go"], "depends_on": [],
             "acceptance": ["a works"]},
            {"id": 2, "title": "B", "summary": "Add b.", "spec_refs": ["s1"],
             "touches": ["lib/b.go"], "depends_on": [],
             "acceptance": ["b works"]},
        ]
        self.write_plan(tasks)
        self.write_gate()
        blocking = write_stub(self.stub_dir, "red-gate-block", "exit 1\n")
        r1 = self.run_pipeline(
            "--no-push", "--max-parallel", "2",
            RED_GATE_BIN=blocking, DISPATCH_BIN=self.fake_dispatch(),
            LEDGER_APPEND_BIN=str(SCRIPTS / "ledger-append"),
        )
        self.assertNotEqual(r1.returncode, 0, r1.stdout + r1.stderr)
        wt = self.repo / ".superpowers" / "two-model" / "worktrees" / "task-1"
        self.assertTrue(wt.exists(), "fixture must leave task 1 allocated")
        r2 = self.run_pipeline(
            "--no-push", "--max-parallel", "2",
            RED_GATE_BIN=blocking, DISPATCH_BIN=self.fake_dispatch(),
            LEDGER_APPEND_BIN=str(SCRIPTS / "ledger-append"),
        )
        self.assertNotIn("BLOCKED - worktree-alloc", r2.stdout + r2.stderr)

    def test_wave_task_run_receives_worktree_tracked_plan(self):
        """Item 2: the wave task-run must be handed the WORKTREE's tracked
        plan path, not the worktree's gitignored workspace plan.json. Only
        then does a diretor corrective/arbitration edit land in a tracked file
        the task's gate chain can commit (the workspace copy is disposable)."""
        tasks = [
            {"id": 1, "title": "A", "summary": "Add a.", "spec_refs": ["s1"],
             "touches": ["lib/a.go"], "depends_on": [],
             "acceptance": ["a works"]},
            {"id": 2, "title": "B", "summary": "Add b.", "spec_refs": ["s1"],
             "touches": ["lib/b.go"], "depends_on": [],
             "acceptance": ["b works"]},
        ]
        self.write_plan(tasks)
        self.write_gate()
        plan_log = self._tmp / "task-run-plan.log"
        r = self.run_pipeline(
            "--no-push", "--max-parallel", "2",
            RED_GATE_BIN=self.fake_red_gate_committing(),
            DISPATCH_BIN=self.fake_dispatch(),
            STUB_DISPATCH_LOG=str(self.dispatch_log),
            STUB_PLAN_LOG=str(plan_log),
            LEDGER_APPEND_BIN=str(SCRIPTS / "ledger-append"),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        plans = [p.strip() for p in plan_log.read_text(
                     encoding="utf-8").splitlines() if p.strip()]
        self.assertEqual(len(plans), 2, plans)
        ws_plan = str(self.ws() / "plan.json").replace("\\", "/")
        for p in plans:
            norm = p.replace("\\", "/")
            self.assertIn("/worktrees/task-", norm, p)
            self.assertTrue(norm.endswith("docs/superpowers/plans/plan.json"),
                            p)
            self.assertNotEqual(norm, ws_plan, p)

    def test_integration_failure_recovery_is_bounded_and_blocks(self):
        """Critical: a failed integrate must not loop forever. The driver
        makes exactly ONE corrective attempt in the failed task's existing
        worktree (reusing it - worktree-alloc exit 1 still reports the paths),
        then blocks for a human. `_timeout` converts any regression to an
        unbounded loop into a fast TimeoutExpired instead of a hung suite.
        The recovery must NOT inject a SEND_BACK episode: it is inert in
        route-next (has_complete wins) and, once a re-integrate succeeds,
        ledger-merge folds it into the integration ledger where it poisons
        final-gate with 'last review unresolved: SEND_BACK'."""
        tasks = [
            {"id": 1, "title": "A", "summary": "Add a.", "spec_refs": ["s1"],
             "touches": ["lib/a.go"], "depends_on": [],
             "acceptance": ["a works"]},
            {"id": 2, "title": "B", "summary": "Add b.", "spec_refs": ["s1"],
             "touches": ["lib/b.go"], "depends_on": [],
             "acceptance": ["b works"]},
        ]
        self.write_plan(tasks)
        self.write_gate()
        r = self.run_pipeline(
            "--no-push", "--max-parallel", "2",
            _timeout=60,
            RED_GATE_BIN=self.fake_red_gate_committing(),
            INTEGRATE_BIN=self.fake_integrate_fail(),
            DISPATCH_BIN=self.fake_dispatch(),
            STUB_DISPATCH_LOG=str(self.dispatch_log),
            LEDGER_APPEND_BIN=str(SCRIPTS / "ledger-append"),
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("still fails integration after one corrective", r.stderr)
        self.assertIn("task 1", r.stderr)
        # Regression guard for the SEND_BACK poisoning: the recovery must not
        # inject an episode anywhere. Checking the worktree shard is what
        # fails against the pre-fix script; checking the integration ledger is
        # what protects final-gate once a re-integrate succeeds and folds the
        # shard.
        wt_ws = (self.repo / ".superpowers" / "two-model" / "worktrees"
                 / "task-1" / ".superpowers" / "two-model" / "plan")
        for path in (self.ws() / "ledger.jsonl", wt_ws / "ledger.jsonl"):
            entries = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            sends = [e for e in entries
                     if e.get("type") == "review_outcome"
                     and e.get("summary") == "SEND_BACK"]
            self.assertEqual(sends, [], (str(path), entries))


if __name__ == "__main__":
    unittest.main()
