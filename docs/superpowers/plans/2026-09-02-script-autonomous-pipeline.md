# Script-Autonomous Two-Model Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move subagent dispatch, gate decisions, and task routing out of the main agent and into deterministic Script A, so the interactive session (B) writes briefs and receives feedback only through script outputs.

**Architecture:** Script A (modular bash: `orchestrator` driver + specialized scripts) runs the per-task loop autonomously: red-gate dispatches C via `opencode run --agent` (headless), Script A decides task-tests/full-suite/analyze by exit code, green-gate commits + updates the graph + dispatches D, D returns a structured JSON verdict, route-next routes (CORRECTIVE/ARBITRATE/NEXT/FINAL_REVIEW). C is write-only (never runs tests); C and D retain sessions within a task; RTK compresses all LLM-facing output. This plan is for the pipeline repo (`~/.config/opencode/vendor/superpowers`).

**Tech Stack:** bash scripts, python3 unittest (existing suite), OpenCode CLI (`opencode run`), RTK (`rtk` 0.46.0), Graphify CLI, Git.

**Spec:** `docs/superpowers/specs/2026-09-02-script-autonomous-pipeline-design.md`

## Global Constraints

- Language: all internal artifacts in English. UI strings (app-facing) default to pt-br.
- Every LLM-invoked command runs through `scripts/cmd` (full output to file, RTK-compressed stdout, true exit code returned).
- Nothing a gate verdict depends on is ever compressed (red-gate `EXPECTED-RED`, red-integrity byte-compare, review packages).
- `RTK_ENABLED=0` disables compression (passthrough); `RTK_BIN` overrides the binary.
- All scripts honor `FLUTTER_BIN`, `DART_BIN`, `GIT_BIN`, `GRAPHIFY_BIN`, `RTK_BIN` env overrides.
- Workers never commit; only Script A (via `green-gate` or the orchestrator) commits.
- Route-next decides every transition; the LLM never decides "APPROVED → next" by reasoning.
- Ledger entries are appended via `scripts/ledger-append`, never free-handed.
- Final review runs in a fresh `/new` session fed only plan + consolidated diff + ledger.
- Test suites: `skills/two-model-sdd-pipeline/tests/run-tests.sh` and `skills/flutter-app-pipeline/tests/run-tests.sh` (python3 unittest). On Windows the suites use Git Bash (`C:\Program Files\Git\bin\bash.exe`) and stub binaries.

---

### Task 1: Spike — headless subagent dispatch via `opencode run` (linchpin)

**Files:**
- Modify: `~/.config/opencode/agent/two-model-coder.md` (mode: subagent → all)
- Create: `docs/superpowers/spike-dispatch-findings.md` (findings record)

**Interfaces:**
- Produces: confirmed dispatch command form `opencode run --agent <NAME> [--continue --session <ID>] --format json "<PROMPT>"` and the JSON event stream shape (`sessionID` field on every event; `text` events carry agent replies). Task 3 (`dispatch`) consumes these.

- [ ] **Step 1: Verify `mode: subagent` is NOT targetable headlessly**

Run: `opencode run --agent two-model-coder --format json "Reply with exactly: SPIKE_OK"`
Expected: warning `agent "two-model-coder" is a subagent, not a primary agent. Falling back to default agent` — proving subagent-mode agents cannot be dispatched headlessly.

- [ ] **Step 2: Change coder agent mode to `all`**

Edit `~/.config/opencode/agent/two-model-coder.md`: `mode: subagent` → `mode: all`. (`all` = primary + subagent; keeps task-tool usability, adds headless targeting.)

- [ ] **Step 3: Verify `mode: all` is targetable**

Run: `opencode run --agent two-model-coder --format json "Write a file spike_check.txt containing SPIKE_OK"`
Expected: exit 0, NO fallback warning, JSON events include a `tool_use` (write succeeded — the agent has edit access) and a final `text` event. Record the `sessionID`.

- [ ] **Step 4: Verify session resume preserves context**

Run: `opencode run --agent two-model-coder --continue --session <SESSION_ID> --format json "Same session as before. Reply with: RESUME_OK"`
Expected: exit 0, same `sessionID` in events, `RESUME_OK` in a `text` event. This is the C fix-round resume mechanism (ADR-0003).

- [ ] **Step 5: Record findings**

Write `docs/superpowers/spike-dispatch-findings.md`: the confirmed command form, the JSON event shape, the mode requirement, the resume mechanism, and the cache-read observation (prefix cache hit on resume).

- [ ] **Step 6: Commit**

```bash
git add ~/.config/opencode/agent/two-model-coder.md docs/superpowers/spike-dispatch-findings.md
git commit -m "spike: headless subagent dispatch via opencode run (mode: all)"
```

---

### Task 2: `cmd` — RTK wrapper wiring for Flutter commands

**Files:**
- Modify: `skills/two-model-sdd-pipeline/scripts/cmd`
- Test: `skills/two-model-sdd-pipeline/tests/test_cmd_runner.py`

**Interfaces:**
- Consumes: `cmd --full-file FILE -- CMD...` contract (full output to FILE, RTK-compressed stdout, true exit code).
- Produces: `flutter test` → `rtk test -- <cmd>` wrapper; `flutter analyze` → `rtk err -- <cmd>` wrapper; git diff → `rtk pipe -f git-diff` (existing). RTK wrapper failures must never change the command's verdict (exit code comes from the wrapper's true child exit where possible; where RTK masks it, the FULL file + passthrough is authoritative — see note).

**Spike finding this task depends on:** RTK has NO flutter pipe filter (verified: `flutter-test` → "Unknown filter"). `rtk test` / `rtk err` are command wrappers that run the child. On Windows/bash the wrapper's exit code was observed as 0 even for a failing child — so `cmd` must NOT use the wrapper's exit code as the verdict. Design decision: `cmd` runs the raw command for the verdict (`PIPESTATUS[0]`), and feeds the same stream to the RTK wrapper for compression only when the filter/wrapper applies. If RTK is unavailable or misbehaves, passthrough (full output) — nothing lost.

- [ ] **Step 1: Write the failing tests**

In `test_cmd_runner.py`, add:

```python
class TestCmdFlutterRtk(CmdTestBase):
    def test_flutter_test_keeps_true_exit_code_and_full_file(self):
        # rtk stub: mirrors a wrapper; must not mask the command verdict.
        rtk = write_stub(self.stub_dir, "rtk", "cat; exit 0\n")
        out = pathlib.Path(self._tmp) / "out.txt"
        r = run_script(
            "cmd",
            ["--full-file", str(out), "--", "sh", "-c",
             "echo flutter-run; exit 7"],
            cwd=self._tmp,
            env_extra={"RTK_BIN": rtk, "RTK_ENABLED": "1"},
        )
        # the raw command's exit code is the verdict (never rtk's).
        self.assertEqual(r.returncode, 7, r.stdout + r.stderr)
        # full output is in the file; stdout shows the (stub-compressed) view.
        self.assertIn("flutter-run", out.read_text(encoding="utf-8"))
        self.assertIn("flutter-run", r.stdout)

    def test_flutter_analyze_runs_through_rtk_err_when_available(self):
        # stub rtk records argv and echoes stdin; assert the err wrapper is used
        # for the analyze command and the file still holds full output.
        rtk = write_stub(self.stub_dir, "rtk", "echo \"WRAP:${1:-}\"; cat\n")
        out = pathlib.Path(self._tmp) / "out.txt"
        r = run_script(
            "cmd",
            ["--full-file", str(out), "--", "flutter", "analyze"],
            cwd=self._tmp,
            env_extra={"RTK_BIN": rtk, "RTK_ENABLED": "1", "FLUTTER_BIN": "flutter"},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("WRAP:err", r.stdout)
        self.assertTrue(out.exists())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bash skills/two-model-sdd-pipeline/tests/run-tests.sh`
Expected: the new test fails (cmd does not yet map flutter).

- [ ] **Step 3: Implement the wiring**

In `scripts/cmd`, extend the filter inference:

```bash
case "${1:-}" in
  flutter)
    case "${2:-}" in
      test)    wrapper="test" ;;
      analyze) wrapper="err" ;;
    esac
    ;;
esac
```

and in the run block: when `wrapper` is set and RTK is available, run `"$@" 2>&1 | tee "$full_file" | "$RTK_BIN" "$wrapper"` ; when not, current passthrough. Keep `rc=${PIPESTATUS[0]}` so the raw command's exit code is the verdict. Add `--skip-env` to wrapper invocations (avoids env-validation overhead).

- [ ] **Step 4: Run tests to verify they pass**

Run: `bash skills/two-model-sdd-pipeline/tests/run-tests.sh`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add skills/two-model-sdd-pipeline/scripts/cmd skills/two-model-sdd-pipeline/tests/test_cmd_runner.py
git commit -m "feat(cmd): RTK wrapper wiring for flutter test/analyze"
```

---

### Task 3: `route-next` — CORRECTIVE / ARBITRATE actions, drop STRATEGIC

**Files:**
- Modify: `skills/two-model-sdd-pipeline/scripts/route-next`
- Test: `skills/two-model-sdd-pipeline/tests/test_route_next.py`

**Interfaces:**
- Consumes: ledger entry types (`brief_ready`, `red_check`, `coder_round`, `commit`, `review_outcome`, `task_complete`, `escalated`).
- Produces: actions `BRIEF N`, `RED N`, `CODER N ROUND`, `REVIEW N`, `FIX N` (kept), `CORRECTIVE N` (new — review SEND_BACK → B writes corrective brief), `ARBITRATE N` (new — coder overflow or review ESCALATE → B validates), `NEXT N`, `FINAL_REVIEW`. `STRATEGIC N` removed.

- [ ] **Step 1: Write the failing tests**

In `test_route_next.py`, update `TestRouteNextFixAndEscalation`:

```python
def test_review_send_back_emits_corrective(self):
    # ... ledger with review_outcome SEND_BACK ...
    self.assert_action(r, "CORRECTIVE 3")

def test_review_escalate_emits_arbitrate(self):
    # ... ledger with review_outcome ESCALATE ...
    self.assert_action(r, "ARBITRATE 3")

def test_escalated_without_commit_emits_arbitrate(self):
    # ... ledger with escalated (2+ rounds, no commit) ...
    self.assert_action(r, "ARBITRATE 3")

def test_four_coder_rounds_emits_arbitrate(self):
    # ... 4 coder_round entries ...
    self.assert_action(r, "ARBITRATE 3")

def test_three_coder_rounds_emits_coder_round_four(self):
    # ... 3 coder_round entries ...
    self.assert_action(r, "CODER 3 4")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bash skills/two-model-sdd-pipeline/tests/run-tests.sh`
Expected: new expectations fail (route-next still emits FIX / STRATEGIC).

- [ ] **Step 3: Implement**

In `scripts/route-next`:
- Decision table: `SEND_BACK` → `CORRECTIVE $task`; `ESCALATE` → `ARBITRATE $task`.
- `has_escalated && no commit` → `ARBITRATE $task`.
- Rounds: `$rounds -ge 4` → `ARBITRATE`; else `CODER $task $(($rounds + 1))` (budget = round 1 + 3 fixes).
- Remove the `STRATEGIC` emission paths.

- [ ] **Step 4: Run tests to verify they pass**

Run: `bash skills/two-model-sdd-pipeline/tests/run-tests.sh`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add skills/two-model-sdd-pipeline/scripts/route-next skills/two-model-sdd-pipeline/tests/test_route_next.py
git commit -m "feat(route-next): CORRECTIVE/ARBITRATE actions, drop STRATEGIC, 4-round budget"
```

---

### Task 4: `token-kill` — RTK minification helpers

**Files:**
- Create: `skills/two-model-sdd-pipeline/scripts/token-kill`
- Test: `skills/two-model-sdd-pipeline/tests/test_token_kill.py`

**Interfaces:**
- Produces: `token-kill err <file>` (minify an error log to stdout — wrapper `rtk err -- cat <file>`), `token-kill src <file>` (strip comments/blank lines for payloads to C/D), `token-kill json <file>` (trim a JSON report via `rtk json`-style compact output). Exit 0 on success, 2 on usage.

- [ ] **Step 1: Write the failing tests**

```python
class TestTokenKill(unittest.TestCase):
    def test_err_minifies_log(self):
        r = run_script("token-kill", ["err", str(logfile)], cwd=self._tmp, env_extra={...})
        self.assertEqual(r.returncode, 0)
        self.assertIn("ERROR", r.stdout)  # errors preserved

    def test_src_strips_comments(self):
        # input: "// comment\nint x = 1;\n" -> output has no comment line
        self.assertNotIn("comment", r.stdout)

    def test_usage_error(self):
        r = run_script("token-kill", [], cwd=self._tmp, env_extra={...})
        self.assertEqual(r.returncode, 2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bash skills/two-model-sdd-pipeline/tests/run-tests.sh`
Expected: failures (script missing).

- [ ] **Step 3: Implement**

```bash
#!/usr/bin/env bash
set -euo pipefail
usage() { echo "usage: token-kill err|src|json FILE" >&2; exit 2; }
[ $# -eq 2 ] || usage
mode=$1; file=$2
[ -f "$file" ] || { echo "token-kill: no such file: $file" >&2; exit 2; }
case "$mode" in
  err)  rtk err -- cat "$file" 2>/dev/null || cat "$file" ;;
  src)  grep -vE '^\s*(//|#|/\*|\*|\*/)' "$file" | grep -vE '^\s*$' ;;
  json) python3 -c "import json,sys; d=json.load(open('$file')); print(json.dumps(d))" 2>/dev/null || cat "$file" ;;
  *)    usage ;;
esac
```

Honor `RTK_BIN` (default `rtk`) and fall back to raw `cat` when RTK is unavailable (nothing lost).

- [ ] **Step 4: Run tests to verify they pass**

Run: `bash skills/two-model-sdd-pipeline/tests/run-tests.sh`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add skills/two-model-sdd-pipeline/scripts/token-kill skills/two-model-sdd-pipeline/tests/test_token_kill.py
git commit -m "feat(token-kill): RTK minification helpers for err/src/json"
```

---

### Task 5: `graphify-update` and `graphify-subgraph`

**Files:**
- Create: `skills/flutter-app-pipeline/scripts/graphify-update`
- Create: `skills/flutter-app-pipeline/scripts/graphify-subgraph`
- Test: `skills/flutter-app-pipeline/tests/test_subgraph.py`

**Interfaces:**
- Consumes: `GRAPHIFY_BIN` (default `graphify`), `GRAPHIFY_ENABLED` (default 1), workspace with `plan.json` (tasks with `touches`), a graph at the project root.
- Produces: `graphify-update [ROOT]` → runs `graphify update <ROOT>` (exit = graphify's). `graphify-subgraph <WS> TASK` → runs `graphify explain "Node"` for each `touches` entry in plan.json task TASK, writes `<WS>/task-N-interfaces.md` (capped ~100 lines), exit 0.

- [ ] **Step 1: Write the failing tests**

In `test_subgraph.py`, mirror `test_gates.py`'s stubs (graphify stub logs calls):

```python
class TestGraphifyUpdate(GateTestBase):
    def test_invokes_graphify_update_on_root(self):
        # stub log records "update <cwd>"
        self.assertIn("update", calls)

class TestGraphifySubgraph(GateTestBase):
    def test_writes_interfaces_file_from_touches(self):
        # plan.json with task 3 touches ["lib/foo.dart"]; stub graphify
        # prints "explain lib/foo.dart"; run graphify-subgraph ws 3
        self.assertTrue((ws / "task-3-interfaces.md").exists())
        self.assertIn("foo", (ws / "task-3-interfaces.md").read_text())

    def test_missing_task_is_usage(self):
        self.assertEqual(r.returncode, 2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bash skills/flutter-app-pipeline/tests/run-tests.sh`
Expected: failures (scripts missing).

- [ ] **Step 3: Implement**

`graphify-update`:

```bash
#!/usr/bin/env bash
set -euo pipefail
GRAPHIFY_BIN="${GRAPHIFY_BIN:-graphify}"
root="${1:-$(pwd)}"
if [ "${GRAPHIFY_ENABLED:-1}" != "0" ]; then
  exec "$GRAPHIFY_BIN" update "$root"
fi
exit 0
```

`graphify-subgraph`:

```bash
#!/usr/bin/env bash
set -euo pipefail
# usage: graphify-subgraph WS TASK  -> writes WS/task-N-interfaces.md
[ $# -eq 2 ] || { echo "usage: graphify-subgraph WS TASK" >&2; exit 2; }
ws=$1; task=$2
[ -f "$ws/plan.json" ] || { echo "graphify-subgraph: no plan.json" >&2; exit 2; }
out="$ws/task-$task-interfaces.md"
: > "$out"
touches=$(python3 - "$ws" "$task" <<'PY'
import json, sys
ws, task = sys.argv[1], sys.argv[2]
plan = json.load(open(f"{ws}/plan.json"))
for t in plan.get("tasks", []):
    if str(t.get("id")) == task:
        print("\n".join(t.get("touches", [])))
        break
PY
)
[ -n "$touches" ] || { echo "graphify-subgraph: task $task has no touches" >&2; exit 2; }
while IFS= read -r node; do
  [ -n "$node" ] || continue
  echo "## $node" >> "$out"
  GRAPHIFY_ENABLED="${GRAPHIFY_ENABLED:-1}" \
    "$GRAPHIFY_BIN" explain "$node" >> "$out" 2>/dev/null || true
done <<< "$touches"
head -c 12000 "$out" > "$out.tmp" && mv "$out.tmp" "$out"
echo "graphify-subgraph: wrote $out"
exit 0
```

(Note: python3 heredoc used for plan.json parsing — deterministic, no LLM.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `bash skills/flutter-app-pipeline/tests/run-tests.sh`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add skills/flutter-app-pipeline/scripts/graphify-update skills/flutter-app-pipeline/scripts/graphify-subgraph skills/flutter-app-pipeline/tests/test_subgraph.py
git commit -m "feat(graphify): post-commit update + subgraph extraction for interfaces"
```

---

### Task 6: `dispatch` — headless subagent launcher

**Files:**
- Create: `skills/two-model-sdd-pipeline/scripts/dispatch`
- Test: `skills/two-model-sdd-pipeline/tests/test_dispatch.py`

**Interfaces:**
- Consumes: spike findings (Task 1), agent names `two-model-coder` / `two-model-reviewer`, `OPENCODE_BIN` env override (default `opencode`), workspace + task for log paths.
- Produces: `dispatch --agent <NAME> --task N [--continue SESSION] --prompt-file <FILE> --log <WS>/task-N-coder.log` → runs `opencode run --agent <NAME> [--continue --session <ID>] --format json --file <prompt-file> "<prompt>"`, tees stdout to `<LOG>`, writes the `sessionID` to `<WS>/task-N-session.txt` (or prints it), exit = opencode's exit code.

- [ ] **Step 1: Write the failing tests**

```python
class TestDispatch(unittest.TestCase):
    def test_dispatches_with_agent_and_logs(self):
        # stub opencode: echo '{"type":"text","sessionID":"ses_x","part":{"text":"ok"}}'
        # run dispatch --agent two-model-coder --task 3 --prompt-file brief --log log
        self.assertEqual(r.returncode, 0)
        self.assertTrue(log.exists())
        self.assertIn("two-model-coder", log.read_text())

    def test_continue_resumes_session(self):
        # stub opencode logs args; assert "--continue --session ses_x" passed
        self.assertIn("--continue", ...)
        self.assertIn("ses_x", ...)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bash skills/two-model-sdd-pipeline/tests/run-tests.sh`
Expected: failures (script missing).

- [ ] **Step 3: Implement**

```bash
#!/usr/bin/env bash
set -euo pipefail
OPENCODE_BIN="${OPENCODE_BIN:-opencode}"
usage() { echo "usage: dispatch --agent NAME --task N [--continue SESSION] --prompt-file FILE --log LOG" >&2; exit 2; }
agent=""; task=""; cont=""; prompt_file=""; log=""
while [ $# -gt 0 ]; do
  case "$1" in
    --agent) agent=${2:-}; shift 2 ;;
    --task) task=${2:-}; shift 2 ;;
    --continue) cont=${2:-}; shift 2 ;;
    --prompt-file) prompt_file=${2:-}; shift 2 ;;
    --log) log=${2:-}; shift 2 ;;
    *) usage ;;
  esac
done
[ -n "$agent" ] && [ -n "$task" ] && [ -n "$prompt_file" ] && [ -n "$log" ] || usage
[ -f "$prompt_file" ] || { echo "dispatch: no prompt file: $prompt_file" >&2; exit 2; }
mkdir -p "$(dirname "$log")"
args=(run --agent "$agent" --format json)
[ -n "$cont" ] && args+=(--continue --session "$cont")
args+=(--file "$prompt_file")
prompt="You are dispatched by Script A. Read the attached brief. Execute per its instructions. Report concisely."
"$OPENCODE_BIN" "${args[@]}" "$prompt" > "$log" 2>&1
rc=$?
# record session id from the JSON event stream for resume
sed -n 's/.*"sessionID":"\([^"]*\)".*/\1/p' "$log" | head -1 > "$(dirname "$log")/task-$task-session.txt"
exit $rc
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `bash skills/two-model-sdd-pipeline/tests/run-tests.sh`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add skills/two-model-sdd-pipeline/scripts/dispatch skills/two-model-sdd-pipeline/tests/test_dispatch.py
git commit -m "feat(dispatch): headless opencode run launcher with session resume"
```

---

### Task 7: `red-gate` — dispatch C on success

**Files:**
- Modify: `skills/flutter-app-pipeline/scripts/red-gate`
- Test: `skills/flutter-app-pipeline/tests/test_gates.py`

**Interfaces:**
- Consumes: brief at `<WS>/task-N-brief.md` (RED-TESTS + EXPECTED-RED), `FLUTTER_BIN`, `DISPATCH_BIN` env override (default: sibling `two-model-sdd-pipeline/scripts/dispatch`).
- Produces: on RED verified, runs the dispatch for C (agent `two-model-coder`, task N, prompt-file = the brief, log `<WS>/task-N-coder.log`), exit 0. Defective brief → exit 1 (no dispatch). Usage → exit 2.

- [ ] **Step 1: Write the failing tests**

In `test_gates.py`, add to `TestRedGate`:

```python
def test_red_verified_dispatches_coder(self):
    # brief verified RED (STUB_TEST_EXIT=1, output contains EXPECTED-RED)
    # stub DISPATCH_BIN logs its args; assert coder dispatched
    r = run_script("red-gate", [str(self.ws), "3"], cwd=self.ws,
                   env_extra={**self.env, "STUB_TEST_EXIT": "1",
                              "STUB_TEST_OUTPUT": "Error: api_client.dart does not exist",
                              "DISPATCH_BIN": self.dispatch_stub})
    self.assertEqual(r.returncode, 0)
    self.assertIn("two-model-coder", dispatch_log)

def test_defective_brief_does_not_dispatch(self):
    # STUB_TEST_EXIT=0 -> exit 1, no dispatch call
    self.assertEqual(r.returncode, 1)
    self.assertEqual(dispatch_log, "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bash skills/flutter-app-pipeline/tests/run-tests.sh`
Expected: failures (red-gate doesn't dispatch yet).

- [ ] **Step 3: Implement**

In `scripts/red-gate`, after the "RED verified" echo and before `exit 0`:

```bash
DISPATCH_BIN="${DISPATCH_BIN:-$SCRIPT_DIR/../../two-model-sdd-pipeline/scripts/dispatch}"
"$DISPATCH_BIN" --agent two-model-coder --task "$task" \
  --prompt-file "$brief" --log "$ws/task-$task-coder.log"
```

(Add `SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)` at the top.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `bash skills/flutter-app-pipeline/tests/run-tests.sh`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add skills/flutter-app-pipeline/scripts/red-gate skills/flutter-app-pipeline/tests/test_gates.py
git commit -m "feat(red-gate): dispatch coder on RED verified"
```

---

### Task 8: `green-gate` — analyze decision, commit, graphify-update, dispatch D

**Files:**
- Modify: `skills/flutter-app-pipeline/scripts/green-gate`
- Test: `skills/flutter-app-pipeline/tests/test_gates.py`

**Interfaces:**
- Consumes: existing gate chain (test → analyze → format → commit), `GRAPHIFY_BIN`, `DISPATCH_BIN`, ledger path via `-l`.
- Produces: on all green + commit: runs `graphify-update` (post-commit), then dispatches D (agent `two-model-reviewer`, task N, prompt-file = review package path `<WS>/task-N-review-package.md`, log `<WS>/task-N-reviewer.log`). `--no-commit` → validate only (no graphify, no D dispatch).

- [ ] **Step 1: Write the failing tests**

```python
def test_green_commits_updates_graph_and_dispatches_reviewer(self):
    # repo with change; green-gate -m "Task 3: x" -l ledger with DISPATCH_BIN stub
    self.assertEqual(r.returncode, 0)
    self.assertIn("Task 3: x", self._log(repo))
    self.assertIn("update", graphify_log)          # post-commit graph update
    self.assertIn("two-model-reviewer", dispatch_log)

def test_no_commit_does_not_dispatch(self):
    r = run_script("green-gate", ["--no-commit"], ...)
    self.assertEqual(r.returncode, 0)
    self.assertEqual(graphify_log, "")
    self.assertEqual(dispatch_log, "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bash skills/flutter-app-pipeline/tests/run-tests.sh`
Expected: failures.

- [ ] **Step 3: Implement**

In `scripts/green-gate`, after the commit block (only when `no_commit=0`):

```bash
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# post-commit graph update (ADR-0004)
"$SCRIPT_DIR/graphify-update" "$(pwd)" || true
# dispatch the reviewer (Item 3)
DISPATCH_BIN="${DISPATCH_BIN:-$SCRIPT_DIR/../../two-model-sdd-pipeline/scripts/dispatch}"
pkg="$ws/task-$task-review-package.md"   # ws/task from -w/--workspace flag
"$DISPATCH_BIN" --agent two-model-reviewer --task "$task" \
  --prompt-file "$pkg" --log "$ws/task-$task-reviewer.log"
```

(Add `-w|--workspace` and `-t|--task` flags to green-gate; required for D dispatch paths. `--no-commit` short-circuits before both.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `bash skills/flutter-app-pipeline/tests/run-tests.sh`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add skills/flutter-app-pipeline/scripts/green-gate skills/flutter-app-pipeline/tests/test_gates.py
git commit -m "feat(green-gate): post-commit graph update + reviewer dispatch"
```

---

### Task 9: `orchestrator` — thin driver executing route-next actions

**Files:**
- Create: `skills/two-model-sdd-pipeline/scripts/orchestrator`
- Test: `skills/two-model-sdd-pipeline/tests/test_orchestrator.py`

**Interfaces:**
- Consumes: route-next (Task 3), red-gate/green-gate/dispatch/graphify scripts, ledger.
- Produces: `orchestrator WS TASK [TOTAL]` → runs the per-task sequence autonomously: route → (RED via red-gate) → gates → review dispatch → route-next → prints `OUTCOME: <action>` for B. Exit 0 when it hands control to B (BRIEF/CORRECTIVE/ARBITRATE/FINAL_REVIEW), nonzero on internal error.

- [ ] **Step 1: Write the failing tests**

```python
class TestOrchestrator(unittest.TestCase):
    def _stub(self, name, body):
        p = pathlib.Path(self._tmp) / "stubs" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
        return str(p)

    def test_brief_handoff_when_no_ledger(self):
        ws = pathlib.Path(self._tmp) / "ws"
        ws.mkdir()
        (ws / "ledger.jsonl").write_text("", encoding="utf-8")
        r = run_script("orchestrator", [str(ws), "3"], cwd=self._tmp,
                       env_extra={"RTK_ENABLED": "0"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OUTCOME: BRIEF 3", r.stdout)

    def test_red_action_invokes_red_gate(self):
        ws = pathlib.Path(self._tmp) / "ws"
        ws.mkdir()
        # ledger state that routes to RED (brief_ready present)
        (ws / "ledger.jsonl").write_text(
            json.dumps({"ts": "2026-09-02T00:00:00Z", "type": "brief_ready",
                        "task": "3", "summary": "brief"}) + "\n",
            encoding="utf-8",
        )
        # stub red-gate that records the call and exits 0
        red_stub = self._stub(
            "red-gate",
            'echo "RED-GATE CALLED: $*" >> "$STUB_RED_LOG"; exit "${STUB_RED_EXIT:-0}"\n',
        )
        log = pathlib.Path(self._tmp) / "red.log"
        r = run_script(
            "orchestrator", [str(ws), "3"], cwd=self._tmp,
            env_extra={"RTK_ENABLED": "0", "RED_GATE_BIN": red_stub,
                       "STUB_RED_LOG": str(log)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("RED-GATE CALLED", log.read_text(encoding="utf-8"))
        self.assertIn("OUTCOME:", r.stdout)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bash skills/two-model-sdd-pipeline/tests/run-tests.sh`
Expected: failures (script missing).

- [ ] **Step 3: Implement**

```bash
#!/usr/bin/env bash
set -euo pipefail
# usage: orchestrator WS TASK [TOTAL]
[ $# -ge 2 ] || { echo "usage: orchestrator WS TASK [TOTAL]" >&2; exit 2; }
ws=$1; task=$2; total=${3:-}
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
action=$("$SCRIPT_DIR/route-next" "$ws" "$task" $total)
case "$action" in
  BRIEF*|CORRECTIVE*|ARBITRATE*|FINAL_REVIEW)
    echo "OUTCOME: $action"; exit 0 ;;
  RED*)
    "$SCRIPT_DIR/../../flutter-app-pipeline/scripts/red-gate" "$ws" "$task"
    # red-gate dispatched C; re-route
    action=$("$SCRIPT_DIR/route-next" "$ws" "$task" $total)
    echo "OUTCOME: $action"; exit 0 ;;
  CODER*|REVIEW*|FIX*|NEXT*)
    # gates owned by the per-task scripts; for generic engine run run-gates
    echo "OUTCOME: $action"; exit 0 ;;
  *)
    echo "orchestrator: unexpected action: $action" >&2; exit 1 ;;
esac
```

(Sequencer semantics: on `RED` it invokes red-gate (which dispatches C); the C→gates→review chain is owned by red-gate/green-gate per ADR-0001; orchestrator's job is the route→execute→handoff loop. In the Flutter layer this is the full chain; the generic engine's `run-gates` remains for non-Flutter.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `bash skills/two-model-sdd-pipeline/tests/run-tests.sh`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add skills/two-model-sdd-pipeline/scripts/orchestrator skills/two-model-sdd-pipeline/tests/test_orchestrator.py
git commit -m "feat(orchestrator): thin driver executing route-next actions"
```

---

### Task 10: Agent definitions — coder permissions, reviewer agent, controller narrowing

**Files:**
- Modify: `~/.config/opencode/agent/two-model-coder.md`
- Create: `~/.config/opencode/agent/two-model-reviewer.md`
- Modify: `~/.config/opencode/agent/two-model-controller.md`
- Modify: `~/.config/opencode/agent/flutter-pipeline.md`

**Interfaces:**
- Produces: `two-model-coder` (mode all, model `opencode-go/mimo-v2.5`, write-only rules, permissions: edit/read/glob/grep allow, bash restricted), `two-model-reviewer` (mode all, model `opencode-go/deepseek-v4-flash`, read-only, JSON verdict contract), controller narrowed (final-review fallback), flutter-pipeline agent doc corrected (graphify claim fixed).

- [ ] **Step 1: Write the agent definitions**

`two-model-coder.md`:

```markdown
---
description: Operational tier of the two-model pipeline (MiMo V2.5). Write-only: implements code to satisfy a RED test; never runs tests or analysis.
mode: all
model: opencode-go/mimo-v2.5
permission:
  edit: allow
  read: allow
  glob: allow
  grep: allow
  bash:
    "*": deny
  webfetch: deny
  task: deny
---

You are the Operational tier (Coder). Write-only executor:
- Implement exactly what the brief + RED tests require. Nothing extra (YAGNI).
- NEVER write or edit test files. If a test looks wrong, report TEST_DEFECT with the reason.
- NEVER run test or analysis commands. Script A runs all gates and feeds you failures.
- Do not commit. Do not spawn subagents.
- English for all comments and identifiers; UI copy keeps the product's locale.
- Report: status (DONE / DONE_WITH_CONCERNS / BLOCKED / TEST_DEFECT), files changed, one-line summary.
```

`two-model-reviewer.md`:

```markdown
---
description: Strategic tier of the two-model pipeline (DeepSeek v4 Flash). Architectural reviewer of compiler-approved code; returns a structured JSON verdict.
mode: all
model: opencode-go/deepseek-v4-flash
permission:
  edit: deny
  read: allow
  glob: allow
  grep: allow
  bash:
    "*": deny
    "git log*": allow
    "git diff*": allow
  webfetch: deny
  task: deny
---

You are the Code Reviewer (D). Strict read-only. Review compiler-approved code
(tests + analysis already passed). Scope: design, architecture, spec compliance,
interface discipline. Return EXACTLY one JSON object:

{"verdict":"APPROVED|SEND_BACK|ESCALATE","findings":[{"severity":"Critical|Important|Minor","file":"...","line":N,"issue":"...","fix":"..."}],"minors":[...],"summary":"..."}

No prose outside the JSON. Minor findings do not require code changes.
```

`two-model-controller.md`: narrow to final-review fallback (keep mode all, model deepseek-v4-flash, note it is only used for holistic review / arbitration fallback when B is unavailable).

`flutter-pipeline.md`: fix line 20 (remove "red-gate rebuilds the graph after RED is verified, green-gate rebuilds it after a commit" — graphify is now post-commit-only via green-gate); describe the script-autonomous flow (red-gate dispatches C; green-gate dispatches D; route-next CORRECTIVE/ARBITRATE).

- [ ] **Step 2: Verify agents are targetable headlessly**

Run: `opencode run --agent two-model-reviewer --format json "Reply with: OK"`
Expected: exit 0, no subagent-fallback warning.

- [ ] **Step 3: Run both test suites to confirm no regressions**

Run: both `run-tests.sh`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add ~/.config/opencode/agent/two-model-coder.md ~/.config/opencode/agent/two-model-reviewer.md ~/.config/opencode/agent/two-model-controller.md ~/.config/opencode/agent/flutter-pipeline.md
git commit -m "feat(agents): write-only coder, reviewer agent, corrected pipeline doc"
```

---

### Task 11: Prompt templates — coder/reviewer rewrite, controller-brief conversion, strategic-coder deletion

**Files:**
- Modify: `skills/two-model-sdd-pipeline/coder-prompt.md`
- Modify: `skills/two-model-sdd-pipeline/reviewer-prompt.md`
- Modify: `skills/two-model-sdd-pipeline/controller-brief-prompt.md`
- Delete: `skills/two-model-sdd-pipeline/strategic-coder-prompt.md`

**Interfaces:**
- Consumes: agent definitions (Task 10), `graphify-subgraph` output (Task 5), `review-package` output.
- Produces: coder template (write-only, no test commands), reviewer template (JSON verdict contract, no test/analyze scope), controller-brief converted to B-side guidance (how the strategist session writes a brief), strategic-coder prompt deleted.

- [ ] **Step 1: Rewrite `coder-prompt.md`**

Write-only version: brief path → read, implement, report. Remove all `scripts/cmd` test-running instructions (replaced by "Script A runs the gates"). Keep TEST_DEFECT rule. Add "your session may be resumed for fix rounds — build on prior round context."

- [ ] **Step 2: Rewrite `reviewer-prompt.md`**

JSON verdict contract (from Task 10), scope = design/architecture/spec-compliance/interfaces on the committed diff; explicit "do NOT run tests or analysis — already green." Fresh-per-task framing retained; correction-loop resume note (same D session when reviewing a corrective brief).

- [ ] **Step 3: Convert `controller-brief-prompt.md` to B guidance**

Rename purpose: "How the strategist session (B) writes a task brief" — brief structure (task statement, exact values, RED tests, EXPECTED-RED, out-of-scope), graphify-subgraph feed, no dispatch template.

- [ ] **Step 4: Delete `strategic-coder-prompt.md`**

```bash
git rm skills/two-model-sdd-pipeline/strategic-coder-prompt.md
```

- [ ] **Step 5: Run both test suites to confirm no regressions**

Run: both `run-tests.sh` (incl. `test_skill_content.py`)
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add skills/two-model-sdd-pipeline/coder-prompt.md skills/two-model-sdd-pipeline/reviewer-prompt.md skills/two-model-sdd-pipeline/controller-brief-prompt.md
git commit -m "feat(prompts): write-only coder, JSON reviewer, B-side brief guidance, drop strategic coder"
```

---

### Task 12: Skill docs — two-model + flutter-app pipeline SKILL.md rewrites

**Files:**
- Modify: `skills/two-model-sdd-pipeline/SKILL.md`
- Modify: `skills/flutter-app-pipeline/SKILL.md`
- Test: `skills/*/tests/test_skill_content.py`

**Interfaces:**
- Produces: SKILL.md describing the script-autonomous loop (B writes briefs; Script A dispatches C/D; route-next CORRECTIVE/ARBITRATE; context retention within task; observability via logs; graphify timing). Remove Strategic Coder role table entries, STRATEGIC action, "fresh reviewer every task" invariant (superseded by ADR-0003).

- [ ] **Step 1: Update `two-model-sdd-pipeline/SKILL.md`**

Rewrite: Roles (Script A / B / C / D; Strategic Coder removed), per-task loop (BRIEF → RED → CODER → GATES → GREEN → REVIEW → ROUTE), ledger types (`corrective`, `arbitrate`, `review_json`), route-next actions, context retention rule, observability rule, `orchestrator` driver invocation, `dispatch`/`token-kill`/`graphify-*` script references.

- [ ] **Step 2: Update `flutter-app-pipeline/SKILL.md`**

Section 3/4: red-gate dispatches C on success; green-gate chains analyze + commit + graphify-update + D dispatch; D receives the review package (JSON verdict); graphify is post-commit only; RTK wrapper wiring for flutter test/analyze; isolation rule kept.

- [ ] **Step 3: Update `test_skill_content.py` files**

Adjust assertions that reference removed content (STRATEGIC, Strategic Coder, "fresh reviewer every task") to the new invariants (CORRECTIVE/ARBITRATE, write-only Coder, context retention).

- [ ] **Step 4: Run both test suites**

Run: both `run-tests.sh`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add skills/two-model-sdd-pipeline/SKILL.md skills/flutter-app-pipeline/SKILL.md skills/*/tests/test_skill_content.py
git commit -m "docs(skills): script-autonomous pipeline loop, roles, ledger, invariants"
```

---

### Task 13: READMEs + doc-check + push (end of session)

**Files:**
- Modify: `README.txt`
- Modify: `README-LLM.md`
- Run: `skills/two-model-sdd-pipeline/scripts/doc-check` (deterministic gate)

**Interfaces:**
- Consumes: everything above. Produces: updated READMEs reflecting the implemented pipeline; `doc-check` exit 0; git push to origin/main.

- [ ] **Step 1: Update `README-LLM.md`**

Section 5 (roles: drop Strategic Coder, add Script A/B/C/D mapping), section 6 (script table: add `dispatch`, `token-kill`, `orchestrator`, `graphify-update`, `graphify-subgraph`; update route-next actions), section 7 (invariants: graphify post-commit only; context retention; observability), section 11 (fix the stale variant table — Operational = `opencode-go/mimo-v2.5`, no `variants` block exists).

- [ ] **Step 2: Update `README.txt`**

Human-facing: describe the script-autonomous flow, new scripts, roles, and the observability model (tail `<ws>/*.log`).

- [ ] **Step 3: Run doc-check**

Run: `skills/two-model-sdd-pipeline/scripts/doc-check` (or per its usage)
Expected: exit 0 (READMEs updated to match pipeline changes).

- [ ] **Step 4: Commit READMEs**

```bash
git add README.txt README-LLM.md
git commit -m "docs: reflect script-autonomous pipeline in READMEs"
```

- [ ] **Step 5: Push to GitHub (incl. graph)**

```bash
git push origin main
```

Expected: origin/main updated with all tasks. (The developer's instruction: README.txt AND README-LLM.md must be updated before the push — Steps 1–4 guarantee that. The Graphify graph `graphify-out/` is gitignored; if the developer wants the graph committed, add it explicitly in this step.)