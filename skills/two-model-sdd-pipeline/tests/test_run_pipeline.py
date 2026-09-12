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
        return self.repo / ".superpowers" / "two-model" / "plan.json"

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
                proc.wait(timeout=30)
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

    def test_missing_plan_is_usage(self):
        r = subprocess.run(
            [BASH, str(SCRIPTS / "run-pipeline"), str(self._tmp / "nope.json")],
            capture_output=True, text=True, cwd=str(self.repo),
            env=dict(os.environ),
        )
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
