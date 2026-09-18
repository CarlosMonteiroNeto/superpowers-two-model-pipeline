"""Regression module for F2: the workspace plan snapshot must be refreshed
from the tracked plan after an integration that may have changed HEAD.

The reviewed baseline let a task branch merge a tracked plan carrying a new
task while `$WS/plan.json` kept the old copy, so `wave-next` emitted
FINAL_REVIEW and the new task never ran. These tests exercise the real refresh
(`pipeline-workspace --refresh`), the real scheduler, and the run-pipeline wave
loop with disposable Git repositories and gate/dispatch stubs.
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


VALID_TASKS = [
    {"id": 1, "title": "A", "summary": "Add a.", "spec_refs": ["s1"],
     "touches": ["lib/a.txt"], "depends_on": [], "acceptance": ["a works"]},
]


class PlanSnapshotRefreshTest(unittest.TestCase):
    """`pipeline-workspace --refresh`: validate then atomically replace the
    existing snapshot, preserving every other workspace artifact."""

    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="plan-refresh-"))
        self.repo = self._tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        self.ws = self.repo / ".superpowers" / "two-model" / "plan"
        self.ws.mkdir(parents=True)
        self.valid = {"feature": "f", "tasks": [dict(VALID_TASKS[0])]}
        (self.ws / "plan.json").write_text(json.dumps(self.valid),
                                           encoding="utf-8")
        self.artifacts = {
            "ledger.jsonl": '{"type":"gate"}\n',
            "ledger-task-1.jsonl": '{"type":"brief_ready","task":"1"}\n',
            "task-1-brief.md": "# brief\n",
            "task-1-coder.log": "log\n",
            "task-1-two-model-coder-go-session.txt": "sess\n",
        }
        for name, body in self.artifacts.items():
            (self.ws / name).write_text(body, encoding="utf-8")
        self.cand_dir = self._tmp / "candidate"
        self.cand_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def candidate(self, plan, name="plan.json"):
        p = self.cand_dir / name
        p.write_text(plan if isinstance(plan, str) else json.dumps(plan),
                     encoding="utf-8")
        return p

    def refresh(self, path):
        return subprocess.run(
            [BASH, str(SCRIPTS / "pipeline-workspace"), "--refresh", str(path)],
            capture_output=True, text=True, cwd=str(self.repo))

    def snapshot(self):
        return (self.ws / "plan.json").read_text(encoding="utf-8")

    def test_valid_candidate_replaces_snapshot_and_preserves_artifacts(self):
        new = {"feature": "f", "tasks": [
            dict(VALID_TASKS[0]),
            {"id": 2, "title": "B", "summary": "Add b.", "spec_refs": ["s1"],
             "touches": ["lib/b.txt"], "depends_on": [1],
             "acceptance": ["b works"]},
        ]}
        r = self.refresh(self.candidate(new))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(self.snapshot()), new)
        for name, body in self.artifacts.items():
            self.assertEqual((self.ws / name).read_text(encoding="utf-8"), body,
                             name)
        leftovers = list(self.ws.glob("plan.json.tmp*"))
        self.assertEqual(leftovers, [])

    def test_invalid_json_blocks_and_keeps_last_valid_snapshot(self):
        before = self.snapshot()
        r = self.refresh(self.candidate("{ not json"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_missing_tasks_blocks(self):
        before = self.snapshot()
        r = self.refresh(self.candidate({"feature": "f"}))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_empty_tasks_blocks(self):
        before = self.snapshot()
        r = self.refresh(self.candidate({"feature": "f", "tasks": []}))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_missing_required_field_blocks(self):
        before = self.snapshot()
        bad = {"feature": "f", "tasks": [
            {"id": 1, "title": "A", "summary": "s"}]}  # no acceptance
        r = self.refresh(self.candidate(bad))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_duplicate_ids_block(self):
        before = self.snapshot()
        bad = {"feature": "f", "tasks": [
            dict(VALID_TASKS[0]), dict(VALID_TASKS[0])]}
        r = self.refresh(self.candidate(bad))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_nonpositive_id_blocks(self):
        before = self.snapshot()
        bad = {"feature": "f", "tasks": [
            {"id": 0, "title": "A", "summary": "s", "acceptance": ["x"]}]}
        r = self.refresh(self.candidate(bad))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_empty_acceptance_blocks(self):
        before = self.snapshot()
        bad = {"feature": "f", "tasks": [
            {"id": 1, "title": "A", "summary": "s", "acceptance": []}]}
        r = self.refresh(self.candidate(bad))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_source_equals_destination_is_safe(self):
        before = self.snapshot()
        r = self.refresh(self.ws / "plan.json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_candidate_path_with_spaces(self):
        spaced = self._tmp / "dir with spaces"
        spaced.mkdir()
        p = spaced / "plan.json"
        p.write_text(json.dumps(self.valid), encoding="utf-8")
        r = self.refresh(p)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(self.snapshot()), self.valid)

    def test_refresh_requires_an_existing_candidate(self):
        r = self.refresh(self.cand_dir / "missing.json")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)


class RunPipelinePlanRefreshTest(unittest.TestCase):
    """The wave driver must refresh `$WS/plan.json` from the tracked plan after
    integrate, so a merged plan edit changes the next wave."""

    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="run-refresh-"))
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
        self.write_plan({"feature": "f", "tasks": [dict(VALID_TASKS[0])]})
        self.stub_dir = self._tmp / "stubs"
        self.stub_dir.mkdir()
        self.dispatch_log = self._tmp / "dispatch.log"

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def ws(self):
        return self.repo / ".superpowers" / "two-model" / "plan"

    def write_plan(self, plan):
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        git(self.repo, "add", "-A")
        subprocess.run(["git", "-C", str(self.repo), "commit", "-q", "-m",
                        "plan"], capture_output=True)

    def write_gate(self):
        self.ws().mkdir(parents=True, exist_ok=True)
        gate = {"ts": "x", "type": "gate", "task": "-", "summary": "go",
                "lang": "go", "test_cmd": "true", "analyze_cmd": "true"}
        (self.ws() / "ledger.jsonl").write_text(json.dumps(gate) + "\n",
                                                encoding="utf-8")

    def fake_gate_ok(self):
        return write_stub(self.stub_dir, "gate-ok", "exit 0\n")

    def fake_dispatch(self):
        return write_stub(
            self.stub_dir, "dispatch",
            'echo "$*" >> "${STUB_DISPATCH_LOG:?}"\nexit 0\n')

    def red_gate_editing_plan(self, mutate_plan, marker):
        """A red-gate stub that commits a change in its worktree and, for task
        1, applies mutate_plan to the worktree's tracked plan before committing.
        The mutation script lives at @MARKER@ so the body stays %-free."""
        marker = marker.replace("\\", "/")
        with open(marker, "w", encoding="utf-8") as fh:
            fh.write(mutate_plan)
        body = (
            "ws=$1; task=$2\n"
            "append=\"${LEDGER_APPEND_BIN:?}\"\n"
            "if [ \"$task\" = \"1\" ]; then\n"
            "  python3 - \"$PLAN\" \"@MARKER@\" <<'PY'\n"
            "import json, sys\n"
            "plan_path, mut_path = sys.argv[1], sys.argv[2]\n"
            "data = json.load(open(plan_path, encoding='utf-8'))\n"
            "exec(open(mut_path, encoding='utf-8').read())\n"
            "json.dump(data, open(plan_path, 'w', encoding='utf-8'))\n"
            "PY\n"
            "fi\n"
            "mkdir -p lib\n"
            "printf 'task %s\\n' \"$task\" > \"lib/task-$task.txt\"\n"
            "git add -A\n"
            "git commit -q -m \"task $task\"\n"
            "sha=$(git rev-parse --short HEAD)\n"
            "\"$append\" \"$ws/ledger.jsonl\" red_check \"$task\" \"RED\"\n"
            "\"$append\" \"$ws/ledger.jsonl\" commit \"$task\" \"green\" "
            "\"commits=$sha\"\n"
            "printf '{\"type\":\"text\",\"part\":{\"type\":\"text\","
            "\"text\":\"working\"}}\\n' > \"$ws/task-$task-reviewer.log\"\n"
            "printf '{\"verdict\":\"APPROVED\",\"findings\":[],\"minors\":[],"
            "\"summary\":\"ok\"}\\n' >> \"$ws/task-$task-reviewer.log\"\n"
            "\"$append\" \"$ws/ledger.jsonl\" review_outcome \"$task\" "
            "\"APPROVED\" \"findings=0\"\n"
            "\"$append\" \"$ws/ledger.jsonl\" task_complete \"$task\" "
            "\"APPROVED\"\n"
            "exit 0\n"
        ).replace("@MARKER@", marker)
        return write_stub(self.stub_dir, "red-gate-edit", body)

    def run_pipeline(self, *args, _timeout=90, **env_extra):
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

    def ledger_types(self):
        return [json.loads(line)["type"]
                for line in (self.ws() / "ledger.jsonl").read_text(
                    encoding="utf-8").splitlines() if line.strip()]

    def env(self, mutate_plan):
        marker = str(self._tmp / "mutate.py")
        return {
            "RED_GATE_BIN": self.red_gate_editing_plan(mutate_plan, marker),
            "RUN_GATES_BIN": self.fake_gate_ok(),
            "DISPATCH_BIN": self.fake_dispatch(),
            "STUB_DISPATCH_LOG": str(self.dispatch_log),
            "LEDGER_APPEND_BIN": str(SCRIPTS / "ledger-append"),
        }

    def test_merged_plan_new_task_is_scheduled_not_final_review(self):
        add_task = (
            "data['tasks'].append({'id': 2, 'title': 'B', 'summary': 'Add b.',"
            " 'spec_refs': ['s1'], 'touches': ['lib/b.txt'],"
            " 'depends_on': [1], 'acceptance': ['b works']})\n"
            "data['tasks'][0]['acceptance'] = ['a works (updated)']\n"
        )
        self.write_gate()
        r = self.run_pipeline("--no-push", "--max-parallel", "2",
                              **self.env(add_task))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        entries = [json.loads(line)
                   for line in (self.ws() / "ledger.jsonl").read_text(
                       encoding="utf-8").splitlines() if line.strip()]
        integrated = sorted(str(e["task"]) for e in entries
                            if e["type"] == "integrated")
        self.assertEqual(integrated, ["1", "2"])
        # task 2 ran only because the driver refreshed the snapshot from the
        # tracked plan that task 1's branch merged.
        self.assertIn("RUN 2", r.stdout)
        plan = json.loads((self.ws() / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual([t["id"] for t in plan["tasks"]], [1, 2])
        self.assertEqual(plan["tasks"][0]["acceptance"], ["a works (updated)"])

    def test_explicit_total_mismatch_after_refresh_blocks(self):
        add_task = (
            "data['tasks'].append({'id': 2, 'title': 'B', 'summary': 'Add b.',"
            " 'spec_refs': ['s1'], 'touches': ['lib/b.txt'],"
            " 'depends_on': [1], 'acceptance': ['b works']})\n"
        )
        self.write_gate()
        r = self.run_pipeline("--no-push", "--max-parallel", "2", "1",
                              **self.env(add_task))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("TOTAL", r.stdout + r.stderr)

    def test_invalid_refreshed_plan_blocks_without_stale_advance(self):
        invalidate = (
            "data['tasks'][0]['id'] = 'not-an-int'\n"
        )
        self.write_gate()
        r = self.run_pipeline("--no-push", "--max-parallel", "2",
                              **self.env(invalidate))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("plan refresh failed", r.stdout + r.stderr)
        # the driver must not advance to the next wave on stale data
        self.assertNotIn("RUN 2", r.stdout)
        # the last valid snapshot is retained, not truncated
        plan = json.loads((self.ws() / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(len(plan["tasks"]), 1)


if __name__ == "__main__":
    unittest.main()
