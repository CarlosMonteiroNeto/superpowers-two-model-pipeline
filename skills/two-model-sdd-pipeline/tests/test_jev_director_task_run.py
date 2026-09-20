import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest


SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
if os.name == "nt":
    _git_bash = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
    BASH = str(_git_bash) if _git_bash.exists() else "bash"
else:
    BASH = "bash"


def executable(directory, name, body):
    path = pathlib.Path(directory) / name
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    if os.name == "nt":
        subprocess.run([BASH, "-c", "chmod +x '{}'".format(path)], check=True)
    else:
        path.chmod(0o755)
    return str(path)


class TaskRunDirectorIntegrationTests(unittest.TestCase):
    """Exercise the real task-run CORRECTIVE/ARBITRATE boundaries."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="jev task-run "))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.repo, check=True)
        (self.repo / "README").write_text("base\n", encoding="utf-8")
        (self.repo / "docs" / "superpowers" / "plans").mkdir(parents=True)
        self.plan = self.repo / "docs" / "superpowers" / "plans" / "jev-task-run-plan.json"
        self.plan.write_text(json.dumps({
            "feature": "task-run director boundary",
            "tasks": [{
                "id": 1,
                "title": "Original task",
                "summary": "Keep the original task viable.",
                "spec_refs": ["docs/spec.md#site-3"],
                "touches": ["README"],
                "depends_on": [],
                "acceptance": ["the director remains authoritative"],
            }],
        }), encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=self.repo, check=True)
        self.stub_dir = self.tmp / "stubs"
        self.stub_dir.mkdir()
        self.dispatch_log = self.tmp / "dispatch.log"
        self.append = str(SCRIPTS / "ledger-append")

        subprocess.run(
            [BASH, str(SCRIPTS / "pipeline-workspace"), str(self.plan)],
            cwd=self.repo, check=True, capture_output=True,
        )
        self.workspace = self.repo / ".superpowers" / "two-model" / "jev-task-run-plan"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ledger(self, kind, task, summary, *extras):
        subprocess.run(
            [BASH, self.append, str(self.workspace / "ledger.jsonl"), kind, str(task), summary, *extras],
            cwd=self.repo, check=True, capture_output=True,
        )

    def _review(self, verdict):
        review = {
            "verdict": verdict,
            "findings": ([{
                "severity": "Important",
                "file": "README",
                "line": 1,
                "issue": "the original task needs a corrective task",
                "fix": "append a scoped corrective task",
            }] if verdict != "APPROVED" else []),
            "minors": [],
            "summary": "structured review evidence",
        }
        (self.workspace / "task-1-review.json").write_text(json.dumps(review), encoding="utf-8")

    def _write_stubs(self):
        dispatch = executable(self.stub_dir, "dispatch", r'''
log="${STUB_DISPATCH_LOG:?}"
agent=""; task=""; prompt=""; previous=""
for value in "$@"; do
  case "$previous" in
    --agent) agent=$value ;;
    --task) task=$value ;;
    --prompt-file) prompt=$value ;;
  esac
  previous=$value
done
printf '%s\t%s\t%s\n' "$agent" "$task" "$prompt" >> "$log"
if [ "$agent" = "two-model-task-generator" ] && grep -q 'Mode: CORRECTIVE' "$prompt"; then
  python3 - "$PLAN_PATH" <<'PY'
import json, sys
path = sys.argv[1]
plan = json.load(open(path, encoding='utf-8'))
if not any(str(task.get('id')) == '2' for task in plan.get('tasks', [])):
    plan['tasks'].append({
        'id': 2,
        'title': 'Correct the original task',
        'summary': 'Apply the review correction.',
        'spec_refs': ['docs/spec.md#site-3'],
        'touches': ['README'],
        'depends_on': [],
        'acceptance': ['the correction is scoped'],
        'corrects': 1,
    })
json.dump(plan, open(path, 'w', encoding='utf-8'), indent=2)
PY
fi
exit 0
''')
        hook = executable(self.stub_dir, "failing-director-hook", "echo hook failed >&2\nexit 19\n")
        coder_gate = executable(self.stub_dir, "coder-gate", r'''
ws=$1; task=$2; append="${LEDGER_APPEND_BIN:?}"
"$append" "$ws/ledger.jsonl" commit "$task" "corrective green" "commits=stub"
printf '%s\n' '{"type":"text","part":{"type":"text","text":"{\"verdict\":\"APPROVED\",\"findings\":[],\"minors\":[],\"summary\":\"approved\"}"}}' > "$ws/task-$task-reviewer.log"
exit 0
''')
        return dispatch, hook, coder_gate

    def _run(self, initial_verdict):
        dispatch, hook, coder_gate = self._write_stubs()
        self._ledger("gate", "-", "go", "lang=go", "test_cmd=true", "analyze_cmd=true")
        self._ledger("brief_ready", 1, "brief")
        self._ledger("red_check", 1, "red")
        if initial_verdict == "SEND_BACK":
            self._ledger("commit", 1, "green", "commits=stub")
        self._ledger("review_outcome", 1, initial_verdict, "findings=1")
        self._review(initial_verdict)
        if initial_verdict == "ESCALATE":
            # Route-next may re-use this parsed log after arbitration resolves.
            (self.workspace / "task-1-reviewer.log").write_text(
                '{"verdict":"APPROVED","findings":[],"minors":[],"summary":"approved"}\n',
                encoding="utf-8",
            )
        env = dict(os.environ)
        env.update({
            "PLAN": str(self.plan),
            "DISPATCH_BIN": dispatch,
            "DIRECTOR_PROMPT_BIN": hook,
            "CODER_GATE_BIN": coder_gate,
            "LEDGER_APPEND_BIN": self.append,
            "STUB_DISPATCH_LOG": str(self.dispatch_log),
            "PLAN_PATH": str(self.plan),
        })
        result = subprocess.run(
            [BASH, str(SCRIPTS / "task-run"), str(self.workspace), "1", "2" if initial_verdict == "SEND_BACK" else "1"],
            cwd=self.repo, env=env, capture_output=True, text=True,
        )
        return result

    def test_corrective_failure_still_dispatches_one_director_and_reconciles_ledger(self):
        result = self._run("SEND_BACK")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = [line.split("\t") for line in self.dispatch_log.read_text(encoding="utf-8").splitlines()]
        directors = [call for call in calls if call[0] == "two-model-task-generator"]
        self.assertEqual(len(directors), 1, calls)
        self.assertEqual(directors[0][1], "0")
        self.assertTrue(any(call[0] == "two-model-coder-go" for call in calls), calls)
        self.assertIn("director prompt preparation failed", result.stdout)
        entries = [json.loads(line) for line in (self.workspace / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        sequence = [(entry["type"], str(entry.get("task")), entry["summary"]) for entry in entries]
        self.assertLess(sequence.index(("corrective", "2", "corrective task for 1")), sequence.index(("commit", "2", "corrective green")))
        self.assertIn(("task_complete", "2", "APPROVED"), sequence)
        self.assertIn(("task_complete", "1", "APPROVED"), sequence)

    def test_arbitrate_failure_still_dispatches_one_director_and_keeps_arbitration_sequence(self):
        result = self._run("ESCALATE")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = [line.split("\t") for line in self.dispatch_log.read_text(encoding="utf-8").splitlines()]
        directors = [call for call in calls if call[0] == "two-model-task-generator"]
        self.assertEqual(len(directors), 1, calls)
        self.assertEqual(directors[0][1], "0")
        entries = [json.loads(line) for line in (self.workspace / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        types = [entry["type"] for entry in entries]
        self.assertIn("arbitrate_resolved", types)
        self.assertLess(types.index("arbitrate_resolved"), types.index("commit"))
        self.assertIn("task_complete", types)


if __name__ == "__main__":
    unittest.main()
