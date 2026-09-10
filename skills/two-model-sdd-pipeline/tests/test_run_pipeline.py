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


FULL_TASK = {
    "id": 1, "title": "Add thing", "summary": "Add the thing.",
    "spec_refs": ["§1"], "touches": ["lib/a.go"], "depends_on": [],
    "acceptance": ["thing exists"], "expected_red": "no thing",
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

    def write_plan(self, tasks):
        self.plan.write_text(json.dumps({"feature": "t", "tasks": tasks}),
                             encoding="utf-8")

    def write_gate(self):
        ws = self.repo / ".superpowers" / "two-model" / "plan.json"
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "ledger.jsonl").write_text(
            json.dumps({"ts": "x", "type": "gate", "task": "-",
                        "summary": "go", "lang": "go",
                        "test_cmd": "true", "analyze_cmd": "true"}) + "\n",
            encoding="utf-8")

    def fake_dispatch(self):
        return write_stub(
            self.stub_dir, "dispatch",
            """
echo "$*" >> "${STUB_DISPATCH_LOG:?}"
exit 0
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

    def run_pipeline(self, *args, **extra_env):
        env = dict(os.environ)
        env.update(extra_env)
        return subprocess.run(
            [BASH, str(SCRIPTS / "run-pipeline"), str(self.plan), *args],
            capture_output=True, text=True, cwd=str(self.repo), env=env,
        )


class TestRunPipelineFlow(RunPipelineTestBase):
    def test_full_branch_to_closing_no_push(self):
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
        ws = self.repo / ".superpowers" / "two-model" / "plan.json"
        ledger_text = (ws / "ledger.jsonl").read_text(encoding="utf-8")
        for want in ("brief_ready", "task_complete", "final_review"):
            self.assertIn(want, ledger_text)
        self.assertTrue((ws / "closing-review.diff").exists())
        dcalls = self.dispatch_log.read_text(encoding="utf-8")
        self.assertIn("two-model-task-generator", dcalls)
        self.assertIn("FINAL_REVIEW", r.stdout)

    def test_empty_plan_dispatches_diretor_then_blocks(self):
        """No usable tasks: Script CEO must call Agente diretor once; if
        tasks still cannot be used, block loudly instead of looping."""
        self.write_plan([])
        self.write_gate()
        r = self.run_pipeline(
            "--no-push",
            DISPATCH_BIN=self.fake_dispatch(),
            STUB_DISPATCH_LOG=str(self.dispatch_log),
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        dcalls = self.dispatch_log.read_text(encoding="utf-8")
        self.assertIn("two-model-task-generator", dcalls)
        self.assertIn("did not expand", r.stdout + r.stderr)

    def test_missing_plan_is_usage(self):
        r = subprocess.run(
            [BASH, str(SCRIPTS / "run-pipeline"), str(self._tmp / "nope.json")],
            capture_output=True, text=True, cwd=str(self.repo),
            env=dict(os.environ),
        )
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
