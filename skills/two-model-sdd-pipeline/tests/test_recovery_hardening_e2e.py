"""Composed recovery-hardening verification (F1-F4).

Exercises the real routing, plan refresh, ledger propagation, and disposable
Git integration with provider/gate stubs:

* a task arbitrates, the director adds a later task to the tracked plan, the
  fresh attempt approves, the wave integrates and refreshes the snapshot, and
  the added task runs before closing;
* a dirty integration checkout halts the run before closing;
* an empty generic commit halts the run before closing.
"""

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"

if os.name == "nt":
    _gb = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
    BASH = str(_gb) if _gb.exists() else "bash"
else:
    BASH = "bash"

GO_TEST_FAILURE = "\n".join([
    '{"Time":"2026-01-01T00:00:00Z","Action":"run",'
    '"Package":"example.com/foo","Test":"TestAdd"}',
    '{"Time":"2026-01-01T00:00:00Z","Action":"output",'
    '"Package":"example.com/foo","Test":"TestAdd",'
    '"Output":"    add_test.go:10: got 5, want 4\\n"}',
    '{"Time":"2026-01-01T00:00:00Z","Action":"fail",'
    '"Package":"example.com/foo","Test":"TestAdd","Elapsed":0.0}',
]) + "\n"

TASK_1 = {"id": 1, "title": "A", "summary": "Add a.", "spec_refs": ["s1"],
          "touches": ["lib/a.txt"], "depends_on": [], "acceptance": ["a works"]}


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True)


def write_stub(directory, name, body):
    p = pathlib.Path(directory) / name
    p.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    if os.name == "nt":
        subprocess.run([BASH, "-c", "chmod +x '{}'".format(p)],
                       capture_output=True)
    else:
        p.chmod(0o755)
    return str(p)


class RecoveryHardeningE2E(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="recovery-e2e-"))
        self.repo = self._tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "t")
        (self.repo / "lib").mkdir()
        (self.repo / "docs" / "superpowers" / "plans").mkdir(parents=True)
        (self.repo / "lib" / "a.txt").write_text("base\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "base")
        self.plan = self.repo / "docs" / "superpowers" / "plans" / "plan.json"
        self.write_plan([dict(TASK_1)])
        self.stub_dir = self._tmp / "stubs"
        self.stub_dir.mkdir()
        self.count_dir = self._tmp / "counts"
        self.count_dir.mkdir()
        self.dispatch_log = self._tmp / "dispatch.log"

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def ws(self):
        return self.repo / ".superpowers" / "two-model" / "plan"

    def write_plan(self, tasks):
        self.plan.write_text(json.dumps({"feature": "f", "tasks": tasks}),
                             encoding="utf-8")
        git(self.repo, "add", "-A")
        subprocess.run(["git", "-C", str(self.repo), "commit", "-q", "-m",
                        "plan"], capture_output=True)

    def write_gate(self):
        self.ws().mkdir(parents=True, exist_ok=True)
        (self.ws() / "ledger.jsonl").write_text(json.dumps({
            "ts": "x", "type": "gate", "task": "-", "summary": "go",
            "lang": "go", "test_cmd": "true", "analyze_cmd": "true"}) + "\n",
            encoding="utf-8")

    def director_stub(self):
        """Dispatch stub: a task-generator dispatch edits the plan path named in
        its prompt to add task 2 (idempotent); everything else is a no-op."""
        return write_stub(
            self.stub_dir, "dispatch",
            """
echo "$*" >> "${STUB_DISPATCH_LOG:?}"
agent=""; prompt=""; prev=""
for a in "$@"; do
  case "$prev" in
    --agent) agent=$a ;;
    --prompt-file) prompt=$a ;;
  esac
  prev=$a
done
if [ "$agent" = "two-model-task-generator" ] && [ -n "$prompt" ] \
   && grep -q '^Plan: ' "$prompt"; then
  plan=$(sed -n 's/^Plan: //p' "$prompt" | head -1)
  python3 - "$plan" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
if not any(str(t.get("id")) == "2" for t in data.get("tasks", [])):
    data["tasks"].append({
        "id": 2, "title": "B", "summary": "Add b.", "spec_refs": ["s1"],
        "touches": ["wave/task-2.txt"], "depends_on": [1],
        "acceptance": ["b works"]})
json.dump(data, open(path, "w", encoding="utf-8"))
PY
fi
exit 0
""")

    def green_stub(self):
        """RED-gate stub: task 1's first attempt is a post-commit ESCALATE (so
        the router arbitrates); every other attempt commits a change and
        approves. State is per task so a resumed run stays deterministic."""
        return write_stub(
            self.stub_dir, "red-gate",
            """
ws=$1; task=$2
append="${LEDGER_APPEND_BIN:?}"
cf="${STUB_COUNT_DIR:?}/task-$task.count"
n=$(cat "$cf" 2>/dev/null || echo 0)
n=$((n + 1)); printf '%s' "$n" > "$cf"
if [ "$task" = "1" ] && [ "$n" -eq 1 ]; then
  sha=$(git rev-parse --short HEAD 2>/dev/null || echo base)
  "$append" "$ws/ledger.jsonl" red_check "$task" "RED"
  "$append" "$ws/ledger.jsonl" commit "$task" "green" "commits=$sha"
  "$append" "$ws/ledger.jsonl" review_outcome "$task" "ESCALATE" "findings=1"
  exit 0
fi
mkdir -p wave
printf 'task %s\\n' "$task" > "wave/task-$task.txt"
git add -A
git commit -q -m "task $task" || true
sha=$(git rev-parse --short HEAD)
"$append" "$ws/ledger.jsonl" red_check "$task" "RED"
"$append" "$ws/ledger.jsonl" commit "$task" "green" "commits=$sha"
printf '{"type":"text","part":{"type":"text","text":"working"}}\\n' > "$ws/task-$task-reviewer.log"
printf '{"verdict":"APPROVED","findings":[],"minors":[],"summary":"ok"}\\n' >> "$ws/task-$task-reviewer.log"
"$append" "$ws/ledger.jsonl" review_outcome "$task" "APPROVED" "findings=0"
"$append" "$ws/ledger.jsonl" task_complete "$task" "APPROVED"
exit 0
""")

    def gate_ok(self):
        return write_stub(self.stub_dir, "gate-ok", "exit 0\n")

    def run_pipeline(self, *args, _timeout=120, **env_extra):
        env = dict(os.environ)
        env.update(env_extra)
        out = self._tmp / "rp.out"
        err = self._tmp / "rp.err"
        with open(out, "w", encoding="utf-8") as fo, \
                open(err, "w", encoding="utf-8") as fe:
            proc = subprocess.Popen(
                [BASH, str(SCRIPTS / "run-pipeline"), str(self.plan), *args],
                stdout=fo, stderr=fe, cwd=str(self.repo), env=env)
            try:
                proc.wait(timeout=_timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                raise
        return subprocess.CompletedProcess(
            args, proc.returncode,
            out.read_text(encoding="utf-8", errors="replace"),
            err.read_text(encoding="utf-8", errors="replace"))

    def base_env(self):
        return {
            "RED_GATE_BIN": self.green_stub(),
            "RUN_GATES_BIN": self.gate_ok(),
            "DISPATCH_BIN": self.director_stub(),
            "STUB_DISPATCH_LOG": str(self.dispatch_log),
            "STUB_COUNT_DIR": str(self.count_dir),
            "LEDGER_APPEND_BIN": str(SCRIPTS / "ledger-append"),
        }

    def test_composed_arbitration_director_task_and_closing(self):
        self.write_gate()
        r = self.run_pipeline("--no-push", "--max-parallel", "2",
                              **self.base_env())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("FINAL_REVIEW", r.stdout)
        # the director ran and the arbitration was recorded
        self.assertIn("two-model-task-generator",
                      self.dispatch_log.read_text(encoding="utf-8"))
        entries = [json.loads(line)
                   for line in (self.ws() / "ledger.jsonl").read_text(
                       encoding="utf-8").splitlines() if line.strip()]
        self.assertIn("arbitrate_resolved", [e["type"] for e in entries])
        # both tasks integrated; task 2 (director-added) ran from the refreshed
        # snapshot and its file landed on the integration HEAD
        integrated = sorted(str(e["task"]) for e in entries
                            if e["type"] == "integrated")
        self.assertEqual(integrated, ["1", "2"])
        self.assertIn("RUN 2", r.stdout)
        content = subprocess.run(
            ["git", "-C", str(self.repo), "show", "HEAD:wave/task-2.txt"],
            capture_output=True, text=True).stdout
        self.assertIn("task 2", content)

    def test_dirty_integration_stops_before_closing(self):
        self.write_gate()
        (self.repo / "stray.txt").write_text("user work\n", encoding="utf-8")
        r = self.run_pipeline("--no-push", "--max-parallel", "2",
                              **self.base_env())
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("BLOCKED", r.stderr)
        self.assertIn("dirty", (r.stdout + r.stderr).lower())
        self.assertTrue((self.repo / "stray.txt").is_file())
        # closing never ran (no final_review ledger entry, no closing message)
        entries = [json.loads(line)
                   for line in (self.ws() / "ledger.jsonl").read_text(
                       encoding="utf-8").splitlines() if line.strip()]
        self.assertNotIn("final_review", [e["type"] for e in entries])
        self.assertNotIn("closing complete", r.stdout)

    def test_empty_commit_stops_before_closing(self):
        """Serial path + the real coder-gate: a green suite with nothing to
        commit must block the task instead of reaching closing."""
        self.write_gate()
        (self.ws() / "task-1-red.txt").write_text(GO_TEST_FAILURE,
                                                  encoding="utf-8")
        real_coder_gate = SCRIPTS / "coder-gate"
        red_gate = write_stub(
            self.stub_dir, "red-gate-real-gate",
            '"%s" "$1" "$2"\nexit $?\n' % real_coder_gate)
        r = self.run_pipeline(
            "--no-push", "--max-parallel", "1",
            RED_GATE_BIN=red_gate,
            RUN_GATES_BIN=self.gate_ok(),
            DISPATCH_BIN=self.director_stub(),
            STUB_DISPATCH_LOG=str(self.dispatch_log),
            LEDGER_APPEND_BIN=str(SCRIPTS / "ledger-append"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("nothing to commit", (r.stdout + r.stderr).lower())
        self.assertNotIn("FINAL_REVIEW", r.stdout)


if __name__ == "__main__":
    unittest.main()
