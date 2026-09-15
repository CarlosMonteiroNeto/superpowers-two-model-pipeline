# Parallel Task Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let mutually independent tasks in a `plan.json` run concurrently through worktree isolation, a plan-derived wave scheduler, and a script-owned integration gate — without changing the serial flow at `--max-parallel 1`.

**Architecture:** A new `wave-next` decider emits ready, `touches`-disjoint tasks; `worktree-alloc` gives each a `task/<N>` branch and its own workspace/ledger shard; each task's existing gate chain runs unchanged inside that worktree under a new `task-run` loop; `integrate` merges task branches into the integration branch in ascending id order, running the full suite after **each** merge and aborting only the failing merge. `route-next`, the gates, the agents, and `cmd`/`dispatch` are untouched.

**Tech Stack:** POSIX bash (git-bash on Windows) + Python 3 stdlib; `unittest` suites driven by `skills/two-model-sdd-pipeline/tests/run-tests.sh`.

**Spec:** `docs/superpowers/specs/2026-09-15-parallel-task-execution-design.md`

## Global Constraints

- **`write-script` is binding** for every new/changed script (spec §3.6): exit-code families are fixed; `ledger-append` is the sole ledger writer; LLM spawns go through `dispatch`; command output that reaches an LLM goes through `cmd`; scripts are idempotent and re-derive from plan + ledger; failures capture `rc=0; … || rc=$?` (never `cmd; rc=$?`); defaults are non-destructive; reports go to files, verdicts to stdout.
- **Exit-code families:** *deciders* (`touches-overlap`, `wave-next`, `final-gate`) = `0` clean/routed, `1` domain failure, `2` usage. *Loop scripts* (`task-run`, `integrate`) = `0` success, `1` failure/blocked, `2` usage. Never invent a fourth meaning; document the table in the file header.
- **Windows/git-bash:** `export PYTHONUTF8=1; export PYTHONIOENCODING=utf-8` in anything that pipes to Python; `cygpath -w` for paths handed to native Python; tolerate CRLF (`line=${line%$'\r'}`); inside a pipe use `python3 -c '…'`, never a heredoc; avoid `awk -v` with Windows paths.
- **Resource-profile header** required on every new script (dispatch / context tokens / ledger I/O / subprocess / wall-clock / git).
- **One `tests/test_<script>.py` per new script**; assert exit codes, not prose. Run the full suite with `bash skills/two-model-sdd-pipeline/tests/run-tests.sh` before each commit.
- **`doc-check`** (`skills/two-model-sdd-pipeline/scripts/doc-check <repo>`) must pass at the end: a change under `skills/` requires `README.txt`/`README-LLM.md` updated in the same commit range (satisfied by Task 14).
- **Never commit unless the task says so**; when committing, stage only the task's files.
- **English-only** artifacts.

---

### Task 1: `touches-overlap` decider

**Files:**
- Create: `skills/two-model-sdd-pipeline/scripts/touches-overlap`
- Test: `skills/two-model-sdd-pipeline/tests/test_touches_overlap.py`

**Interfaces:**
- Consumes: `<ws>/plan.json` (fields `tasks[].id`, `tasks[].touches`).
- Produces: `touches-overlap WORKSPACE ID [ID...]` → exit `0` disjoint (stdout `TOUCHES-OVERLAP: disjoint`), `1` overlap (stderr `TOUCHES-OVERLAP: <a> and <b> share <files>`), `2` usage/missing plan/unknown id. Consumed by `wave-next` (Task 8).

- [ ] **Step 1: Write the failing test**

Create `tests/test_touches_overlap.py`:

```python
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
PY = sys.executable


class TouchesOverlapTest(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="touches-overlap-"))
        self.ws = self._tmp / "ws"
        self.ws.mkdir()
        self.plan = {"feature": "f", "tasks": [
            {"id": 1, "touches": ["src/a.go", "src/shared.go"]},
            {"id": 2, "touches": ["src/b.go"]},
            {"id": 3, "touches": ["src/shared.go", "src/c.go"]},
        ]}
        (self.ws / "plan.json").write_text(json.dumps(self.plan), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def run_it(self, *ids):
        return subprocess.run(
            [PY, str(SCRIPTS / "touches-overlap"), str(self.ws), *map(str, ids)],
            capture_output=True, text=True)

    def test_disjoint_is_zero(self):
        r = self.run_it(1, 2)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("disjoint", r.stdout)

    def test_overlap_is_one_and_names_files(self):
        r = self.run_it(1, 3)
        self.assertEqual(r.returncode, 1)
        self.assertIn("src/shared.go", r.stderr)

    def test_single_id_is_disjoint(self):
        self.assertEqual(self.run_it(1).returncode, 0)

    def test_unknown_id_is_usage(self):
        self.assertEqual(self.run_it(1, 99).returncode, 2)

    def test_missing_plan_is_usage(self):
        (self.ws / "plan.json").unlink()
        self.assertEqual(self.run_it(1, 2).returncode, 2)

    def test_no_args_is_usage(self):
        r = subprocess.run([PY, str(SCRIPTS / "touches-overlap")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python3 -m unittest test_touches_overlap -v` from `skills/two-model-sdd-pipeline/tests/`
Expected: FAIL (script does not exist → non-zero import/exec).

- [ ] **Step 3: Write the script**

Create `scripts/touches-overlap`:

```python
#!/usr/bin/env python3
"""Declared-`touches` pairwise disjointness decider (no LLM).

Decides whether a candidate wave's tasks can run concurrently: two tasks may
share a wave only if their declared `touches` sets are disjoint.

Usage: touches-overlap WORKSPACE ID [ID...]    (reads <ws>/plan.json)
Exit codes: 0 = disjoint, 1 = overlap (conflicting pairs on stderr),
            2 = usage / missing plan / unknown id.

Resource profile: dispatch none; stdout not LLM-facing; ledger read none
(plan.json only); one Python pass; wall-clock trivial; git none.
"""

import json
import os
import sys


def main():
    if len(sys.argv) < 3:
        print("usage: touches-overlap WORKSPACE ID [ID...]", file=sys.stderr)
        return 2
    ws, ids = sys.argv[1], sys.argv[2:]
    plan_path = os.path.join(ws, "plan.json")
    if not os.path.isfile(plan_path):
        print("TOUCHES-OVERLAP: no plan.json at {}".format(plan_path), file=sys.stderr)
        return 2
    with open(plan_path, encoding="utf-8", errors="replace") as fh:
        plan = json.load(fh)
    touches = {str(t.get("id")): set(t.get("touches", []))
               for t in plan.get("tasks", [])}
    unknown = [i for i in ids if i not in touches]
    if unknown:
        print("TOUCHES-OVERLAP: unknown task id(s) {}".format(",".join(unknown)),
              file=sys.stderr)
        return 2
    conflicts = []
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            shared = sorted(touches[ids[a]] & touches[ids[b]])
            if shared:
                conflicts.append((ids[a], ids[b], shared))
    if conflicts:
        for x, y, shared in conflicts:
            print("TOUCHES-OVERLAP: {} and {} share {}".format(x, y, ",".join(shared)),
                  file=sys.stderr)
        return 1
    print("TOUCHES-OVERLAP: disjoint")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run it and watch it pass**

Run: `python3 -m unittest test_touches_overlap -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add skills/two-model-sdd-pipeline/scripts/touches-overlap skills/two-model-sdd-pipeline/tests/test_touches_overlap.py
git commit -m "feat(pipeline): touches-overlap decider for wave scheduling"
```

---

### Task 2: Fix `interface-check`'s `depends_on`-as-path bug

**Files:**
- Modify: `skills/two-model-sdd-pipeline/scripts/interface-check:4-5,46`
- Test: `skills/two-model-sdd-pipeline/tests/test_interface_check.py`

**Interfaces:**
- Produces: `interface-check` now compares the committed `BASE..HEAD` diff only against the other tasks' declared file `touches`; `depends_on` (task ids) no longer enters the file set. Exit codes unchanged (`0/1/2`).

- [ ] **Step 1: Write the failing tests**

In `test_interface_check.py`, change the `setUp` plan so the consumed file is declared via `touches`, and add a regression test:

```python
        self.plan = {
            "feature": "f",
            "tasks": [
                {"id": 1, "touches": ["src/a.dart"], "depends_on": []},
                {"id": 2, "touches": ["src/a.dart", "src/b.dart"], "depends_on": [1]},
            ],
        }
```

and add:

```python
    def test_depends_on_path_like_entries_are_not_consumed(self):
        # depends_on holds task ids; a path-like entry there must not be
        # treated as a consumed interface.
        plan = {"feature": "f", "tasks": [
            {"id": 1, "touches": ["src/other.dart"], "depends_on": ["src/b.dart"]},
            {"id": 3, "touches": ["src/b.dart"], "depends_on": []},
        ]}
        (self.ws / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        (self.repo / "src" / "b.dart").write_text("void b() { z(); }\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "t3")
        r = self.run_it(3)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
```

- [ ] **Step 2: Run and watch the new test fail**

Run: `python3 -m unittest test_interface_check -v`
Expected: `test_depends_on_path_like_entries_are_not_consumed` FAILS (exit 1 — the old code reads `depends_on` as a path). `test_touching_consumed_interface_emits_change` still passes (task 2 now declares `src/a.dart` in `touches`).

- [ ] **Step 3: Fix the script**

In `scripts/interface-check`, change line 46 from

```python
        for f in t.get("touches", []) + t.get("depends_on", []):
```

to

```python
        for f in t.get("touches", []):
```

and the docstring line 4-5 from `declares in its `touches` or `depends_on` (plan.json)` to `declares in its `touches` (plan.json); `depends_on` holds task ids, not paths`.

- [ ] **Step 4: Run the full suite**

Run: `bash skills/two-model-sdd-pipeline/tests/run-tests.sh`
Expected: all pass. If a `coder-gate`/fixture test relied on the old semantics, update its plan fixture to declare the consumed file in `touches`.

- [ ] **Step 5: Commit**

```bash
git add skills/two-model-sdd-pipeline/scripts/interface-check skills/two-model-sdd-pipeline/tests/test_interface_check.py
git commit -m "fix(pipeline): interface-check treats depends_on as task ids, not paths"
```

---

### Task 3: Plan-authoring rules (`depends_on` + `touches` are scheduling-authoritative)

**Files:**
- Modify: `skills/two-model-sdd-pipeline/SKILL.md` (schema section; batching rule)
- Modify: `skills/writing-plans/SKILL.md` (plan completeness list)
- Modify: `skills/brainstorming/SKILL.md` (plan completeness list)
- Test: `skills/two-model-sdd-pipeline/tests/test_skill_content.py` / `test_skill_docs.py` (existing content assertions — update if they break)

**Interfaces:**
- Produces: the documented contract `wave-next` relies on — `depends_on` = task ids, binding; `touches` = disjointness contract; contract-producing tasks are their own wave.

- [ ] **Step 1: Edit `two-model-sdd-pipeline/SKILL.md`**

In the "The JSON Plan" section, after the schema block, add:

```markdown
**`depends_on` and `touches` are scheduling-authoritative.** `depends_on` holds
task **ids** (never paths); a task is dispatched only once every id in it is
`task_complete`. `touches` is the concurrency contract: two tasks may share a
wave only when their `touches` sets are **disjoint**. A task that produces a
type/interface/model consumed by ≥2 tasks is a wave of its own and must land
before the consuming wave. Corrective tasks (`corrects: N`) never get their own
wave slot.
```

- [ ] **Step 2: Edit `writing-plans/SKILL.md` and `brainstorming/SKILL.md`**

In each plan-completeness list, add one line:

```markdown
- `depends_on`: the task ids that must be `task_complete` before this task may
  run (empty array = no predecessor). `touches`: the exclusive file set; tasks
  with overlapping `touches` never share a wave.
```

- [ ] **Step 3: Run the pipeline suite**

Run: `bash skills/two-model-sdd-pipeline/tests/run-tests.sh`
Expected: pass. If `test_skill_content`/`test_skill_docs` assert the old schema text, update those assertions to the new lines in the same commit.

- [ ] **Step 4: Commit**

```bash
git add skills/two-model-sdd-pipeline/SKILL.md skills/writing-plans/SKILL.md skills/brainstorming/SKILL.md skills/two-model-sdd-pipeline/tests
git commit -m "docs(pipeline): depends_on + touches are scheduling-authoritative"
```

---

### Task 4: `ledger-merge` (worktree shard → integration ledger)

**Files:**
- Create: `skills/two-model-sdd-pipeline/scripts/ledger-merge`
- Test: `skills/two-model-sdd-pipeline/tests/test_ledger_merge.py`

**Interfaces:**
- Consumes: the sibling `ledger-append` (sole writer) and `ledger-migrate`.
- Produces: `ledger-merge INTEGRATION_WS SOURCE_LEDGER [SOURCE_LEDGER...]` → appends every non-`gate`, not-already-present entry through `ledger-append`, then rebuilds partitions. Exit `0`; `2` usage. Idempotent.

- [ ] **Step 1: Write the failing test**

Create `tests/test_ledger_merge.py`:

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and watch it fail**

Run: `python3 -m unittest test_ledger_merge -v`
Expected: FAIL (script missing).

- [ ] **Step 3: Write the script**

Create `scripts/ledger-merge`:

```python
#!/usr/bin/env python3
"""Merge per-worktree ledger shards into the integration ledger.

Parallel tasks write their own workspace ledger (a worktree has its own
`.superpowers/two-model/<slug>/`). On wave close the integrator folds those
shards into the integration ledger. To keep `ledger-append` the sole writer
(and thus keep escaping + the partition mirror in one place) every entry is
re-emitted through `ledger-append`, never appended by hand.

Usage: ledger-merge INTEGRATION_WS SOURCE_LEDGER [SOURCE_LEDGER...]
Exit codes: 0 = merged (idempotent), 2 = usage.

Resource profile: dispatch none; stdout not LLM-facing; ledger I/O global +
per-task rebuild; one Python pass + one ledger-append per new entry; git none.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KEEP = ("ts", "type", "task", "summary")


def key_of(entry):
    """Identity of an entry, ignoring the append timestamp.

    `ledger-append` restamps `ts` on every write, so a raw-line comparison
    would never match a re-emitted entry and re-runs would duplicate the
    whole shard. Identity is the entry's content minus `ts`.
    """
    return json.dumps({k: v for k, v in entry.items() if k != "ts"}, sort_keys=True)


def load_seen(path):
    seen = set()
    if os.path.isfile(path):
        with open(path, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    seen.add(key_of(json.loads(raw)))
                except ValueError:
                    pass
    return seen


def main():
    if len(sys.argv) < 3:
        print("usage: ledger-merge INTEGRATION_WS SOURCE_LEDGER [SOURCE_LEDGER...]",
              file=sys.stderr)
        return 2
    ws, sources = sys.argv[1], sys.argv[2:]
    dest = os.path.join(ws, "ledger.jsonl")
    seen = load_seen(dest)
    appended = 0
    for src in sources:
        if not os.path.isfile(src):
            continue
        with open(src, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if entry.get("type") == "gate":
                    continue
                key = key_of(entry)
                if key in seen:
                    continue
                args = ["bash", os.path.join(HERE, "ledger-append"), dest,
                        str(entry.get("type", "")), str(entry.get("task", "-")),
                        str(entry.get("summary", ""))]
                for k, v in entry.items():
                    if k in KEEP:
                        continue
                    args.append("{}={}".format(k, v))
                rc = subprocess.run(args, capture_output=True, text=True).returncode
                if rc == 0:
                    seen.add(key)
                    appended += 1
    subprocess.run(["bash", os.path.join(HERE, "ledger-migrate"), ws],
                   capture_output=True)
    print("LEDGER-MERGE: merged {} entry(ies) into {}".format(appended, ws))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run and watch it pass**

Run: `python3 -m unittest test_ledger_merge -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add skills/two-model-sdd-pipeline/scripts/ledger-merge skills/two-model-sdd-pipeline/tests/test_ledger_merge.py
git commit -m "feat(pipeline): ledger-merge folds worktree shards into the integration ledger"
```

---

### Task 5: `ledger-migrate` in-flight guard

**Files:**
- Modify: `skills/two-model-sdd-pipeline/scripts/ledger-migrate:24-29`
- Test: `skills/two-model-sdd-pipeline/tests/test_ledger_partition.py`

**Interfaces:**
- Produces: `ledger-migrate` refuses to `rm -f` partitions while a wave is in flight (an unmatched `worktree_alloc` in the global ledger), exiting `0` with `LEDGER-MIGRATE: wave in flight - deferred`; behavior otherwise unchanged.

- [ ] **Step 1: Write the failing test**

Add to `test_ledger_partition.py`:

```python
    def test_defers_when_a_wave_is_in_flight(self):
        ws = pathlib.Path(self._tmp) / "ws"
        ws.mkdir()
        lines = [
            json.dumps({"ts": "t", "type": "gate", "task": "-", "summary": "go"}),
            json.dumps({"ts": "t", "type": "worktree_alloc", "task": "1",
                        "summary": "allocated"}),
            json.dumps({"ts": "t", "type": "brief_ready", "task": "1", "summary": "b"}),
        ]
        (ws / "ledger.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        r = subprocess.run([BASH, str(SCRIPTS / "ledger-migrate"), str(ws)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("in flight", r.stdout + r.stderr)
        self.assertFalse((ws / "ledger-task-1.jsonl").exists())
```

(Use the file's existing `SCRIPTS`/`BASH` conventions; add imports only if missing.)

- [ ] **Step 2: Run and watch it fail**

Run: `python3 -m unittest test_ledger_partition -v`
Expected: the new test FAILS (current script splits and creates `ledger-task-1.jsonl`).

- [ ] **Step 3: Add the guard**

In `scripts/ledger-migrate`, immediately after the `[ -f "ledger.jsonl" ]` check (line 24), insert:

```bash
# Concurrency guard (write-script §7): never rm -f live partitions while a
# wave's worktrees are running. An unmatched worktree_alloc means a wave is
# in flight; defer and let the caller fall back to the global ledger.
alloc=$(grep -c '"type": *"worktree_alloc"' ledger.jsonl || true)
released=$(grep -c '"type": *"worktree_release"' ledger.jsonl || true)
if [ "${alloc:-0}" -gt "${released:-0}" ]; then
  echo "LEDGER-MIGRATE: wave in flight ($alloc alloc / $released release) - deferred"
  exit 0
fi
```

- [ ] **Step 4: Run the full suite**

Run: `bash skills/two-model-sdd-pipeline/tests/run-tests.sh`
Expected: all pass (existing migrate/partition tests have no `worktree_alloc`, so the guard never trips).

- [ ] **Step 5: Commit**

```bash
git add skills/two-model-sdd-pipeline/scripts/ledger-migrate skills/two-model-sdd-pipeline/tests/test_ledger_partition.py
git commit -m "fix(pipeline): ledger-migrate defers while a wave is in flight"
```

---

### Task 6: `worktree-alloc`

**Files:**
- Create: `skills/two-model-sdd-pipeline/scripts/worktree-alloc`
- Test: `skills/two-model-sdd-pipeline/tests/test_worktree.py`

**Interfaces:**
- Produces: `worktree-alloc WORKSPACE TASK` → creates `git worktree` at `<repo>/.superpowers/two-model/worktrees/task-<N>` on branch `task/<N>` from integration `HEAD`; seeds the worktree workspace with `plan.json`, a self-ignoring `.gitignore`, and a `ledger.jsonl` holding only the branch `gate` entry; ledgers `worktree_alloc` into the **integration** ledger; prints `WORKTREE=<path>` and `WS=<path>`. Exit `0`; `1` already allocated; `2` usage. Consumed by `run-pipeline` (Task 12) and `worktree-release` (Task 7).

- [ ] **Step 1: Write the failing test**

Create `tests/test_worktree.py` (uses the `test_run_pipeline.py` bash/temp-repo helpers pattern):

```python
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
    subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)


class WorktreeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="worktree-"))
        self.repo = self._tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "t")
        (self.repo / "lib").mkdir()
        (self.repo / "lib" / "a.go").write_text("package a\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "base")
        self.ws = self.repo / ".superpowers" / "two-model" / "plan"
        self.ws.mkdir(parents=True)
        (self.ws / "plan.json").write_text(json.dumps({"feature": "f", "tasks": []}),
                                           encoding="utf-8")
        gate = {"ts": "t", "type": "gate", "task": "-", "summary": "go", "lang": "go",
                "test_cmd": "true", "analyze_cmd": "true"}
        (self.ws / "ledger.jsonl").write_text(json.dumps(gate) + "\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def run_it(self, script, *args):
        return subprocess.run([BASH, str(SCRIPTS / script), str(self.ws), *map(str, args)],
                              capture_output=True, text=True, cwd=self.repo)

    def test_alloc_creates_worktree_branch_and_workspace(self):
        r = self.run_it("worktree-alloc", 3)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        wt = self.repo / ".superpowers" / "two-model" / "worktrees" / "task-3"
        self.assertTrue((wt / "lib" / "a.go").is_file())
        self.assertIn("task/3", subprocess.run(
            ["git", "-C", str(self.repo), "branch"], capture_output=True,
            text=True).stdout)
        wt_ws = wt / ".superpowers" / "two-model" / "plan"
        self.assertTrue((wt_ws / "plan.json").is_file())
        self.assertIn('"type": "gate"', (wt_ws / "ledger.jsonl").read_text(encoding="utf-8"))
        self.assertIn("worktree_alloc",
                      (self.ws / "ledger.jsonl").read_text(encoding="utf-8"))

    def test_alloc_leaves_integration_tree_clean(self):
        self.run_it("worktree-alloc", 3)
        out = subprocess.run(["git", "-C", str(self.repo), "status", "--porcelain"],
                             capture_output=True, text=True).stdout
        self.assertEqual(out.strip(), "")

    def test_second_alloc_is_one(self):
        self.run_it("worktree-alloc", 3)
        self.assertEqual(self.run_it("worktree-alloc", 3).returncode, 1)

    def test_usage(self):
        r = subprocess.run([BASH, str(SCRIPTS / "worktree-alloc")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and watch it fail**

Run: `python3 -m unittest test_worktree -v`
Expected: FAIL (script missing).

- [ ] **Step 3: Write the script**

Create `scripts/worktree-alloc`:

```bash
#!/usr/bin/env bash
# Allocate one git worktree (branch task/<N>) for a parallel task and seed its
# workspace. Prints WORKTREE=<path> and WS=<path>.
#
# Usage: worktree-alloc WORKSPACE TASK
# Exit codes: 0 = allocated, 1 = already allocated, 2 = usage.
#
# Resource profile: dispatch none; stdout not LLM-facing; ledger I/O writes
# the integration global ledger; subprocess: git worktree add + one ledger-append;
# wall-clock trivial; git writes (worktree + branch task/<N> from HEAD).
set -euo pipefail

if [ $# -ne 2 ]; then
  echo "usage: worktree-alloc WORKSPACE TASK" >&2
  exit 2
fi
ws=$1
task=$2
script_dir=$(cd "$(dirname "$0")" && pwd)
root=$(git rev-parse --show-toplevel)
wt="$root/.superpowers/two-model/worktrees/task-$task"

if git worktree list --porcelain | grep -qx "worktree $wt"; then
  echo "WORKTREE-ALLOC: task $task already allocated at $wt" >&2
  exit 1
fi

mkdir -p "$(dirname "$wt")"
git worktree add -q "$wt" -b "task/$task" HEAD

# Seed the worktree workspace. The worktree is a fresh checkout: the
# integration tree's self-ignoring .superpowers/.gitignore is untracked and
# does NOT travel, so recreate it or the gate's `git add -A` would commit
# the workspace into the task branch.
wt_ws="$wt/.superpowers/two-model/$(basename "$ws")"
mkdir -p "$wt_ws"
printf '*\n' > "$wt/.superpowers/two-model/.gitignore"
cp -f "$ws/plan.json" "$wt_ws/plan.json"
grep -m1 '"type": *"gate"' "$ws/ledger.jsonl" > "$wt_ws/ledger.jsonl" || : > "$wt_ws/ledger.jsonl"

"$script_dir/ledger-append" "$ws/ledger.jsonl" worktree_alloc "$task" \
  "allocated task/$task" worktree="$wt"

echo "WORKTREE=$wt"
echo "WS=$wt_ws"
```

- [ ] **Step 4: Run and watch it pass**

Run: `python3 -m unittest test_worktree -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add skills/two-model-sdd-pipeline/scripts/worktree-alloc skills/two-model-sdd-pipeline/tests/test_worktree.py
git commit -m "feat(pipeline): worktree-alloc isolates a parallel task"
```

---

### Task 7: `worktree-release`

**Files:**
- Create: `skills/two-model-sdd-pipeline/scripts/worktree-release`
- Test: `skills/two-model-sdd-pipeline/tests/test_worktree.py` (extend)

**Interfaces:**
- Produces: `worktree-release WORKSPACE TASK` → refuses unless `task/<N>` is merged into `HEAD`; then removes the worktree, prunes, deletes the branch, and ledgers `worktree_release`. Exit `0` released; `1` not merged / not found; `2` usage. Never auto-removes on failure.

- [ ] **Step 1: Write the failing tests**

Append to `test_worktree.py`:

```python
    def test_release_after_merge_removes_branch_and_tree(self):
        self.run_it("worktree-alloc", 3)
        wt = self.repo / ".superpowers" / "two-model" / "worktrees" / "task-3"
        (wt / "lib" / "a.go").write_text("package a // x\n", encoding="utf-8")
        git(wt, "add", "-A")
        git(wt, "commit", "-qm", "task3")
        git(self.repo, "merge", "--no-ff", "-m", "merge 3", "task/3")
        r = self.run_it("worktree-release", 3)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(wt.exists())
        branches = subprocess.run(["git", "-C", str(self.repo), "branch"],
                                  capture_output=True, text=True).stdout
        self.assertNotIn("task/3", branches)
        self.assertIn("worktree_release",
                      (self.ws / "ledger.jsonl").read_text(encoding="utf-8"))

    def test_release_unmerged_is_one_and_keeps_tree(self):
        self.run_it("worktree-alloc", 3)
        r = self.run_it("worktree-release", 3)
        self.assertEqual(r.returncode, 1)
        self.assertTrue((self.repo / ".superpowers" / "two-model" / "worktrees"
                         / "task-3").exists())
```

- [ ] **Step 2: Run and watch them fail**

Run: `python3 -m unittest test_worktree -v`
Expected: FAIL (script missing).

- [ ] **Step 3: Write the script**

Create `scripts/worktree-release`:

```bash
#!/usr/bin/env bash
# Release a task worktree after its branch is merged into the integration HEAD.
# Never removes on failure (debugging parity with session-clean, write-script §7).
#
# Usage: worktree-release WORKSPACE TASK
# Exit codes: 0 = released, 1 = not merged / not found, 2 = usage.
#
# Resource profile: dispatch none; stdout not LLM-facing; ledger I/O writes the
# integration global ledger; subprocess: git worktree remove/prune + branch -d +
# one ledger-append; wall-clock trivial; git removes a worktree and a branch.
set -euo pipefail

if [ $# -ne 2 ]; then
  echo "usage: worktree-release WORKSPACE TASK" >&2
  exit 2
fi
ws=$1
task=$2
script_dir=$(cd "$(dirname "$0")" && pwd)
root=$(git rev-parse --show-toplevel)
wt="$root/.superpowers/two-model/worktrees/task-$task"

if ! git branch --merged HEAD | sed 's/^[* ]*//' | grep -qx "task/$task"; then
  echo "WORKTREE-RELEASE: task/$task is not merged into HEAD - keeping worktree" >&2
  exit 1
fi

if git worktree list --porcelain | grep -qx "worktree $wt"; then
  git worktree remove --force "$wt"
fi
git worktree prune
git branch -d "task/$task" >/dev/null 2>&1 || true

"$script_dir/ledger-append" "$ws/ledger.jsonl" worktree_release "$task" \
  "released task/$task"
```

- [ ] **Step 4: Run and watch them pass**

Run: `python3 -m unittest test_worktree -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add skills/two-model-sdd-pipeline/scripts/worktree-release skills/two-model-sdd-pipeline/tests/test_worktree.py
git commit -m "feat(pipeline): worktree-release after a merged task"
```

---

### Task 8: `wave-next` scheduler

**Files:**
- Create: `skills/two-model-sdd-pipeline/scripts/wave-next`
- Test: `skills/two-model-sdd-pipeline/tests/test_wave_next.py`

**Interfaces:**
- Consumes: `<ws>/plan.json`, `<ws>/ledger.jsonl`; the `touches-overlap` logic (import `pathclass`-style module or call the sibling script — call the sibling script to avoid a second copy).
- Produces: `wave-next WORKSPACE [MAX_PARALLEL]` → one `RUN <id>` line per selected task, or `FINAL_REVIEW`; exit `0` emitted, `1` `WAVE_EMPTY` (blocked), `2` usage. Consumed by `run-pipeline` (Task 12).

**Readiness rules (exact):**
- **done task**: has a `task_complete` or `integrated` entry, and the newest of `{task_complete, integrated, integration_failed}` is not `integration_failed`. `depends_on` entries are satisfied by done tasks.
- **pending episode**: newest `review_outcome` is `SEND_BACK` or `ESCALATE` with no later `APPROVED` / `arbitrate_resolved` / completion → the task must run alone. A **done** task is never in an episode (completion clears it), so this can never conflict with a later `task_complete`.
- **ready**: not done, all `depends_on` done, and not in a pending episode.
- If any ready task is a corrective (`corrects`) or in a pending episode → emit only the lowest-id such task.
- Otherwise greedily add ready tasks in ascending id order, each disjoint from the selected set (`touches-overlap`), up to `MAX_PARALLEL`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_wave_next.py`:

```python
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
```

- [ ] **Step 2: Run and watch it fail**

Run: `python3 -m unittest test_wave_next -v`
Expected: FAIL (script missing).

- [ ] **Step 3: Write the script**

Create `scripts/wave-next`:

```python
#!/usr/bin/env python3
"""Plan-derived wave scheduler (no LLM).

Reads plan.json + the merged ledger and emits the next wave: the ready tasks
(all depends_on done, not done, no open episode) whose declared `touches` are
pairwise disjoint, capped at MAX_PARALLEL. Corrective/pending-episode tasks are
emitted alone.

Usage: wave-next WORKSPACE [MAX_PARALLEL]
Exit codes: 0 = wave emitted (one `RUN <id>` per line) or FINAL_REVIEW,
            1 = nothing runnable while tasks remain (WAVE_EMPTY), 2 = usage.

Resource profile: dispatch none; stdout is Script-CEO-facing (RUN lines);
ledger I/O reads the global ledger once; one Python pass + one subprocess per
candidate pair (touches-overlap); git none.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load_ledger(path):
    entries = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except ValueError:
                    pass
    return entries


def task_of(entry):
    return entry.get("task")


def main():
    if len(sys.argv) not in (2, 3):
        print("usage: wave-next WORKSPACE [MAX_PARALLEL]", file=sys.stderr)
        return 2
    ws = sys.argv[1]
    try:
        cap = int(sys.argv[2]) if len(sys.argv) == 3 else 2
    except ValueError:
        return 2
    plan_path = os.path.join(ws, "plan.json")
    if not os.path.isfile(plan_path) or cap < 1:
        return 2
    with open(plan_path, encoding="utf-8", errors="replace") as fh:
        tasks = json.load(fh).get("tasks", [])
    ledger = load_ledger(os.path.join(ws, "ledger.jsonl"))

    done_events = ("task_complete", "integrated")
    state = {}      # id -> "done" | "failed" | None
    episode = {}    # id -> True if newest review_outcome is SEND_BACK/ESCALATE
    for t in tasks:
        tid = str(t.get("id"))
        last = None
        for e in ledger:
            if str(task_of(e)) != tid:
                continue
            if e.get("type") in done_events or e.get("type") == "integration_failed":
                last = e.get("type")
            if e.get("type") == "review_outcome":
                verdict = e.get("summary")
                episode[tid] = verdict in ("SEND_BACK", "ESCALATE")
                if verdict == "APPROVED":
                    episode[tid] = False
            if e.get("type") == "arbitrate_resolved":
                episode[tid] = False
        state[tid] = "done" if last in done_events else ("failed" if last else None)

    if all(state.get(str(t.get("id"))) == "done" for t in tasks) and tasks:
        print("FINAL_REVIEW")
        return 0

    ready = []
    for t in tasks:
        tid = str(t.get("id"))
        if state.get(tid) == "done":
            continue
        deps = [str(d) for d in (t.get("depends_on") or [])]
        if any(state.get(d) != "done" for d in deps):
            continue
        ready.append(t)

    if not ready:
        print("WAVE_EMPTY: nothing runnable (blocked)", file=sys.stderr)
        return 1

    # Corrective work and open episodes run alone, lowest id first.
    special = [t for t in ready if t.get("corrects") or episode.get(str(t.get("id")))]
    if special:
        print("RUN {}".format(min(int(t["id"]) for t in special)))
        return 0

    selected = []
    for t in sorted(ready, key=lambda x: int(x["id"])):
        if len(selected) >= cap:
            break
        candidate = selected + [t]
        ids = [str(x["id"]) for x in candidate]
        rc = subprocess.run([sys.executable, os.path.join(HERE, "touches-overlap"), ws, *ids],
                            capture_output=True, text=True).returncode
        if rc == 0:
            selected = candidate
    for t in selected:
        print("RUN {}".format(t["id"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run and watch it pass**

Run: `python3 -m unittest test_wave_next -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add skills/two-model-sdd-pipeline/scripts/wave-next skills/two-model-sdd-pipeline/tests/test_wave_next.py
git commit -m "feat(pipeline): wave-next plan-derived scheduler"
```

---

### Task 9: Extract `task-run` from `run-pipeline` (pure refactor)

**Files:**
- Create: `skills/two-model-sdd-pipeline/scripts/task-run`
- Modify: `skills/two-model-sdd-pipeline/scripts/run-pipeline:206-386` (the main loop becomes a call)
- Test: `skills/two-model-sdd-pipeline/tests/test_run_pipeline.py` (must pass unchanged — the regression contract)

**Interfaces:**
- Consumes: `orchestrator`, `parse-review`, `ledger-append`, `brief-scaffold`, `coder-gate`, `dispatch` — exactly as `run-pipeline` does today.
- Produces: `task-run WORKSPACE TASK TOTAL` → drives one task to completion (or blocked) in its cwd's working tree; exit `0` complete, `1` blocked/escalated, `2` usage. Consumed by `run-pipeline` (serial and wave) and by Task 12.

- [ ] **Step 1: Confirm the baseline is green**

Run: `bash skills/two-model-sdd-pipeline/tests/run-tests.sh`
Expected: all pass (baseline before refactor).

- [ ] **Step 2: Create `task-run` by moving the loop**

Move the body of `run-pipeline`'s `while true` loop (lines 211-386: `orchestrator` call, `OUTCOME` parse, stuck detector, and the `REVIEW`/`CORRECTIVE`/`ARBITRATE` branches) into a new `scripts/task-run`, with these exact changes:
- Signature `task-run WORKSPACE TASK TOTAL`; no `first_incomplete`, no `NEXT`/`FINAL_REVIEW` cases.
- On `APPROVED` (the `REVIEW` branch) → `return 0`.
- On a terminal `escalated`/unresolved-arbitration or blocked state → `return 1`.
- Keep `set -euo pipefail`, the `DISPATCH_BIN`/`CODER_GATE_BIN`/`RED_GATE_BIN` env overrides, the `ledger()` wrapper, and the `reconcile_parents`/`refresh_plan`/`dispatch_task_generator` helpers **verbatim** (copy them into `task-run`).
- Add the write-script resource header and the exit-code table.

- [ ] **Step 3: Make `run-pipeline` call `task-run`**

Replace the loop with:

```bash
task=$(first_incomplete)
while true; do
  total=$(total_now)
  rc=0
  task_run_bin="${TASK_RUN_BIN:-$SCRIPT_DIR/task-run}"
  "$task_run_bin" "$WS" "$task" "$total" || rc=$?
  case "$rc" in
    0) ;;
    1) block "task $task blocked (inspect task-$task logs)";;
    *) block "task-run exit $rc on task $task";;
  esac
  action=$("$SCRIPT_DIR/route-next" "$WS" "$task" "$total") || block "route-next inconsistent after task $task"
  case "$action" in
    NEXT\ *) task=${action#NEXT } ;;
    FINAL_REVIEW*) break ;;
    *) block "unexpected action after completed task $task: $action" ;;
  esac
done
```

Delete the now-unused `prev_action`/`prev_lines`/`stuck` detector from `run-pipeline` (it lives in `task-run`).

- [ ] **Step 4: Run the suite unchanged**

Run: `bash skills/two-model-sdd-pipeline/tests/run-tests.sh`
Expected: **all existing tests pass with no edits** — the refactor is behavior-preserving. If any test fails, the extraction changed behavior: fix the extraction, not the test.

- [ ] **Step 5: Add a direct `task-run` test**

Add to `test_run_pipeline.py` (reuse its stubs):

```python
    def test_task_run_completes_one_task(self):
        # Same stubs as the serial test; task-run must return 0 after APPROVED.
        # (Reuse this class's helper that stages a full APPROVED round.)
```

Fill it with the class's existing helper calls; assert `returncode == 0` and that `task_complete` is ledgered for the task. (If the existing helpers already stage a full round, point `TASK_RUN_BIN` at the real script and pass the task id.)

- [ ] **Step 6: Commit**

```bash
git add skills/two-model-sdd-pipeline/scripts/task-run skills/two-model-sdd-pipeline/scripts/run-pipeline skills/two-model-sdd-pipeline/tests/test_run_pipeline.py
git commit -m "refactor(pipeline): extract task-run from run-pipeline (behavior-preserving)"
```

---

### Task 10: `integrate` (script-owned merge gate)

**Files:**
- Create: `skills/two-model-sdd-pipeline/scripts/integrate`
- Test: `skills/two-model-sdd-pipeline/tests/test_integrate.py`

**Interfaces:**
- Consumes: `run-gates` (generic) / `green-gate --no-commit` (flutter), `ledger-append`, `ledger-merge`, `worktree-release`.
- Produces: `integrate WORKSPACE TASK [TASK...]` → for each task in ascending id: `git merge --no-commit --no-ff task/<N>`; conflict → abort + `integration_failed N conflict`; run the full gate; red → abort + `integration_failed N gates`; green → commit + `integrated N sha=…` + `worktree-release`; then `ledger-merge` the worktree shard. Exit `0` all integrated; `1` ≥1 `integration_failed`; `2` usage.

- [ ] **Step 1: Write the failing test**

Create `tests/test_integrate.py` following the `test_run_pipeline.py` stub pattern (temp repo, `worktree-alloc`, a task branch with a commit, stub `run-gates`). Cover:
- clean merge + green gate → `integrated` ledgered, `task/<N>` branch gone, worktree gone, shard merged.
- conflicting branch → `integration_failed N conflict` ledgered, integration `HEAD` unchanged, other tasks still integrated.
- gate-red (a stub `RUN_GATES_BIN` that exits 1) → `integration_failed N gates` ledgered, `HEAD` unchanged.
- **suite runs after each merge**: plan 2 tasks, a stub gate that passes merge 1 and fails merge 2; assert merge 1 committed `integrated`, merge 2 aborted `integration_failed`.

- [ ] **Step 2: Run and watch it fail**

Run: `python3 -m unittest test_integrate -v`
Expected: FAIL (script missing).

- [ ] **Step 3: Write the script**

Create `scripts/integrate` (bash). Core loop per task `n` (ascending), with `ws` and `script_dir` resolved; read `lang`/`test_cmd`/`analyze_cmd` from the integration ledger's `gate` entry exactly as `final-gate:40-43` does:

```bash
for n in $(printf '%s\n' "$@" | sort -n); do
  if ! git merge --no-commit --no-ff "task/$n" >/dev/null 2>&1; then
    git merge --abort 2>/dev/null || true
    "$script_dir/ledger-append" "$ledger" integration_failed "$n" "conflict"
    failed=1
    continue
  fi
  gate_rc=0
  "$RUN_GATES_BIN" "$ws" "$test_cmd" "$analyze_cmd" || gate_rc=$?
  if [ "$gate_rc" -ne 0 ]; then
    git merge --abort 2>/dev/null || true
    "$script_dir/ledger-append" "$ledger" integration_failed "$n" "gates (rc=$gate_rc)"
    failed=1
    continue
  fi
  git commit --no-edit >/dev/null 2>&1
  sha=$(git rev-parse --short HEAD)
  "$script_dir/ledger-append" "$ledger" integrated "$n" "merged $sha" commits="$sha"
  "$script_dir/ledger-merge" "$ws" "$root/.superpowers/two-model/worktrees/task-$n/.superpowers/two-model/$(basename "$ws")/ledger.jsonl" >/dev/null 2>&1 || true
  "$script_dir/worktree-release" "$ws" "$n" >/dev/null 2>&1 || true
done
```

Add the header (exit-code table + resource profile), argument validation (`< 2` → `2`), and `set -euo pipefail` with `|| rc=$?` captures. For `lang=flutter`, call `green-gate --no-commit -w "$ws" -t "$n"` instead of `run-gates`.

- [ ] **Step 4: Run and watch it pass**

Run: `python3 -m unittest test_integrate -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/two-model-sdd-pipeline/scripts/integrate skills/two-model-sdd-pipeline/tests/test_integrate.py
git commit -m "feat(pipeline): script-owned integration gate"
```

---

### Task 11: `final-gate` parallel-closing checks

**Files:**
- Modify: `skills/two-model-sdd-pipeline/scripts/final-gate` (add blockers before the gate-run section)
- Test: `skills/two-model-sdd-pipeline/tests/test_final_gate.py`

**Interfaces:**
- Produces: `final-gate` additionally blocks on (a) an unmatched `worktree_alloc`, (b) a leftover `task/<N>` branch, (c) a task whose newest `integration_failed` postdates its completion. Existing checks and exit codes (`0/1/2`) unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `test_final_gate.py`: a fixture whose ledger has `worktree_alloc 2` with no `worktree_release` → expect `1` and "worktree" in output; and one where `run-pipeline`'s clean serial ledger is unchanged → expect the new checks do not fire.

- [ ] **Step 2: Run and watch them fail**

Run: `python3 -m unittest test_final_gate -v`
Expected: the new blocker test FAILS (exit `0`, no blocker).

- [ ] **Step 3: Add the checks**

In `scripts/final-gate`, after the parked-severity loop, add:

```bash
alloc=$(grep -c '"type": *"worktree_alloc"' "$ledger" || true)
released=$(grep -c '"type": *"worktree_release"' "$ledger" || true)
[ "${alloc:-0}" -gt "${released:-0}" ] && emit "a worktree is still allocated ($alloc alloc / $released release)"
if git branch --list 'task/*' | grep -q .; then
  emit "unmerged task branch(es) remain: $(git branch --list 'task/*' | tr -d ' *' | tr '\n' ' ')"
fi
```

(The per-task "newest event is `integration_failed`" check folds into the existing per-task loop: after the `task_complete` presence check, compare the line index of the last `integration_failed` for the task against the last `task_complete`/`integrated` and `emit "task $t failed integration after completion"` when the failure is newer.)

- [ ] **Step 4: Run and watch them pass**

Run: `python3 -m unittest test_final_gate -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/two-model-sdd-pipeline/scripts/final-gate skills/two-model-sdd-pipeline/tests/test_final_gate.py
git commit -m "feat(pipeline): final-gate blocks on pending worktrees and failed integrations"
```

---

### Task 12: `run-pipeline` wave loop + `--max-parallel`

**Files:**
- Modify: `skills/two-model-sdd-pipeline/scripts/run-pipeline` (arg parse + loop)
- Test: `skills/two-model-sdd-pipeline/tests/test_run_pipeline.py` (extend)

**Interfaces:**
- Produces: `run-pipeline PLAN_FILE [TOTAL] [--no-push] [--max-parallel N]` — `N` default `2`; `N==1` is the existing serial path through `task-run` (Task 9); `N>1` runs `wave-next` → `worktree-alloc` per id → parallel `task-run` (cwd = worktree) → `integrate` → serial handling of failures, until `FINAL_REVIEW`.

- [ ] **Step 1: Write the failing tests**

Add to `test_run_pipeline.py`:
- **`--max-parallel 1` regression:** run the existing serial fixture with `--max-parallel 1`; assert the ledger/commit sequence is identical to the pre-change run (same entries, same order).
- **wave run:** plan with 2 disjoint tasks (`touches: ["lib/a.go"]`, `["lib/b.go"]`), stub `dispatch`/gates to approve both, `--max-parallel 2`; assert two `task/<N>` branches existed and two `integrated` entries are ledgered, integration `HEAD` contains both changes, and no worktree remains.
- **argument:** `--max-parallel 0` → exit `2`.

- [ ] **Step 2: Run and watch them fail**

Run: `python3 -m unittest test_run_pipeline -v`
Expected: the `--max-parallel` arg is rejected (exit `2`) → new tests FAIL.

- [ ] **Step 3: Implement the loop**

Add `--max-parallel N` parsing (validate integer ≥ 1, else exit `2`). Then:

```bash
if [ "$MAX_PARALLEL" -eq 1 ]; then
  # existing serial path (Task 9's task-run + route-next advance)
  ...
else
  while true; do
    wave=$("$SCRIPT_DIR/wave-next" "$WS" "$MAX_PARALLEL") || {
      rc=$?; [ "$rc" -eq 1 ] && block "wave-next: nothing runnable"; }
    case "$wave" in FINAL_REVIEW) break ;; esac
    ids=$(printf '%s\n' "$wave" | sed -n 's/^RUN //p')
    declare -A wt_of
    for n in $ids; do
      out=$("$SCRIPT_DIR/worktree-alloc" "$WS" "$n") || block "worktree-alloc task $n"
      wt_of[$n]=$(printf '%s\n' "$out" | sed -n 's/^WORKTREE=//p')
      wsws_of[$n]=$(printf '%s\n' "$out" | sed -n 's/^WS=//p')
    done
    for n in $ids; do
      ( cd "${wt_of[$n]}" && "$SCRIPT_DIR/task-run" "${wsws_of[$n]}" "$n" "$(total_now)" \
          >"$WS/task-$n-run.log" 2>&1 ) &
    done
    wait
    "$SCRIPT_DIR/integrate" "$WS" $ids || true
  done
fi
```

Fill the serial branch with Task 9's exact loop. Any task the integrator failed is already ledgered `integration_failed`; the next `wave-next` re-emits it alone (Task 8's rules), so the loop self-heals without special-casing.

- [ ] **Step 4: Run and watch them pass**

Run: `bash skills/two-model-sdd-pipeline/tests/run-tests.sh`
Expected: all pass, including the `--max-parallel 1` regression.

- [ ] **Step 5: Commit**

```bash
git add skills/two-model-sdd-pipeline/scripts/run-pipeline skills/two-model-sdd-pipeline/tests/test_run_pipeline.py
git commit -m "feat(pipeline): run-pipeline wave loop with --max-parallel"
```

---

### Task 13: ADRs 0010–0012

**Files:**
- Create: `docs/superpowers/adr/0010-wave-scheduling-plan-derived.md`
- Create: `docs/superpowers/adr/0011-worktree-per-task-ledger-shards.md`
- Create: `docs/superpowers/adr/0012-script-owned-integration-gate.md`

**Interfaces:** none (documentation). Consumed by `CONTEXT.md` references in Task 14.

- [ ] **Step 1: Write the three ADRs**

Follow the existing ADR format (Status / Context / Decision / Consequences / Alternatives rejected) as in `docs/superpowers/adr/0009-opencode-run-file-positional-constraint.md`. Each states the reversal-cost / reach / rejected-alternative gates from spec §6 verbatim (ADR-0011 records the `flock` alternative; ADR-0012 records "merge at wave end / agent-driven merge").

- [ ] **Step 2: Verify links**

Run: `grep -rn "ADR-001" docs/superpowers/adr | grep -E "001[012]"` and confirm each references the others where the spec does.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/adr/0010-wave-scheduling-plan-derived.md docs/superpowers/adr/0011-worktree-per-task-ledger-shards.md docs/superpowers/adr/0012-script-owned-integration-gate.md
git commit -m "docs(pipeline): ADRs for wave scheduling, worktree shards, integration gate"
```

---

### Task 14: READMEs + CONTEXT + `doc-check`

**Files:**
- Modify: `README.txt` (INSTALL-adjacent script list; per-task loop description)
- Modify: `README-LLM.md` (§6 deterministic-scripts table; §7 ordering invariants)
- Modify: `CONTEXT.md` (glossary: wave, shard, integration branch, task worktree; a 2026-09-15 decision block)
- Verify: `skills/two-model-sdd-pipeline/scripts/doc-check`

**Interfaces:** none.

- [ ] **Step 1: Update `README-LLM.md` §6**

Add rows for `touches-overlap`, `wave-next`, `ledger-merge`, `worktree-alloc`, `worktree-release`, `task-run`, `integrate`, each with its purpose and exit codes; add the parallel-execution note to §7 (plan-derived waves; `--max-parallel`; serial at `1`).

- [ ] **Step 2: Update `README.txt` and `CONTEXT.md`**

Mirror the same in the human-facing README, and add glossary entries:

```markdown
## Decision points locked during brainstorming (2026-09-15)

- Parallel tasks: `depends_on` + `touches` are scheduling-authoritative; waves are
  computed by `wave-next`, never inferred by an LLM (ADR-0010).
- Isolation: one git worktree + `task/<N>` branch per task, with a per-worktree
  ledger shard merged by the integrator (ADR-0011).
- Integration: `integrate` is a script-owned serial merge gate, full suite after
  each merge, aborting only the failing merge (ADR-0012).
- Defaults: `--max-parallel 2`; `--max-parallel 1` reproduces the exact serial flow.
```

- [ ] **Step 3: Run `doc-check` and the full suite**

Run: `bash skills/two-model-sdd-pipeline/scripts/doc-check .`
Expected: `DOC-CHECK: pipeline files and READMEs both updated - OK`.
Run: `bash skills/two-model-sdd-pipeline/tests/run-tests.sh` — all pass.
Run: `bash skills/flutter-app-pipeline/tests/run-tests.sh` — all pass (unchanged).

- [ ] **Step 4: Commit and push**

```bash
git add README.txt README-LLM.md CONTEXT.md
git commit -m "docs(pipeline): document parallel task execution (waves + worktrees)"
git push -u origin main
```

---

## Self-Review

**Spec coverage:** §3.1 model → Tasks 3, 8; §3.2 components → Tasks 1, 4, 5, 6, 7, 8, 9, 10, 11, 12; §3.5 tests → every task's test step; §3.6 conventions → Global Constraints + each header; §5 plan-authoring → Tasks 2, 3; §6 ADRs → Task 13; §7 order → the task sequence; §8 out-of-scope → no task touches it. Gaps: none.

**Placeholder scan:** no "TBD"/"handle edge cases"/"similar to Task N"; every code step carries real code; Task 9 Step 5 and Task 11 Step 1 reference an existing test helper by name rather than re-printing it (the helper is in-file and read in the task).

**Type consistency:** `wave-next` emits `RUN <id>` (Task 8) and `run-pipeline` parses `^RUN ` (Task 12); `worktree-alloc` prints `WORKTREE=`/`WS=` (Task 6) parsed the same way (Task 12); ledger types `worktree_alloc`/`worktree_release`/`integrated`/`integration_failed` are spelled identically in Tasks 4, 5, 10, 11 and in `wave-next` (Task 8); `task-run WORKSPACE TASK TOTAL` matches its call sites in Tasks 9 and 12.
