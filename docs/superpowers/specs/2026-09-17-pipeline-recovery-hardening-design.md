# Pipeline Recovery Hardening

## 1. Purpose and reviewed baseline

Repair the four defects reproduced during the repository review of
`b014887749abfb541e99a6357208a31207d1c002` in
`CarlosMonteiroNeto/superpowers-two-model-pipeline`. This document and the
companion plan are an execution handoff, not a claim that the fixes exist.

Companion plan:
`docs/superpowers/plans/2026-09-17-pipeline-recovery-hardening-plan.json`.

Category context: developer automation; deterministic, ledger-driven coding
pipeline; isolated task worktrees, script-owned gates, and resumable agent
execution. These are existing project capabilities, not a new product design.

### 1.1 Review evidence

| Finding | Reproduced behavior | Required outcome |
| --- | --- | --- |
| F1, P1 | Two approved branches enter batch integration; its gate fails; `git reset --hard` deletes an unrelated tracked edit. | Reject a dirty integration checkout before mutation. |
| F2, P1 | A task branch merges a tracked plan with two tasks; the integration workspace still contains one; `wave-next` emits `FINAL_REVIEW`. | Refresh the scheduling snapshot from the integrated tracked plan. |
| F3, P1 | A task has `red_check`, `TEST_DEFECT`, a later arbitration resolution, and a refreshed brief; routing invokes `coder-gate`, which reads the old failure and blocks without dispatching the coder. | Begin a new execution attempt after resolution. |
| F4, P2 | A generic gate passes with nothing to commit; `coder-gate` exits zero without a commit or reviewer dispatch; routing returns to `CODER`. | Empty and failed commits return explicit blocking failures. |

The review ran 62 existing scheduling, parsing, routing, and integration tests
successfully. Separate disposable-repository probes exposed the four gaps.
The review did not execute live providers or a real Flutter application.
Regression tests must reconstruct fixtures from this specification; do not
depend on the reviewer's temporary directories or session history.

## 2. Global constraints and boundaries

- All artifacts, test names, comments, diagnostics, and documentation are English-only.
- No new production dependencies, provider calls in tests, or changes to model selection.
- Preserve public CLI arguments and existing successful execution paths; mechanical failures must propagate nonzero exit codes.
- Preserve append-only ledger history through `ledger-append`, including its per-task partitions; never rewrite old events to manufacture progress.
- Never stash, discard, clean, force-remove, or commit user changes as a recovery mechanism.
- Keep changes limited to the four findings and their regression coverage and documentation.
- `touches` contains implementation and documentation paths only; author new test files outside `touches`, as required by `brief-scaffold` and `keep-discard`.
- Existing committed tests remain unchanged; add regression modules and reuse their fixture conventions without weakening existing assertions.
- Keep Bash/Git Bash and native Python path compatibility, including repository paths containing spaces.
- The executor records real RED evidence before implementing each behavior and runs the authoritative gates afterward.

This work does not redesign wave scheduling, solve concurrent director plan-edit
conflicts, add automatic integration conflict resolution, implement crash-safe
transactions for every ledger write, or introduce a general no-op approval
protocol. Empty-commit automatic approval is deliberately outside scope: a
missing commit is not proof of review or task completion.

## 3. Design requirements

### 3.1 F1: refuse integration from a dirty checkout

`integrate` must check the integration repository's index and working tree
before any merge, reset, release, or success event. Staged changes, unstaged
tracked changes, and non-ignored untracked files all block integration. Ignored
pipeline workspaces do not count as dirt. A status command failure also blocks;
empty output from a failed command must not be mistaken for a clean checkout.

On rejection, exit 1, identify the dirty checkout in stderr, and append an
`integration_failed` event with a dirty-worktree reason for each requested
task. This preserves `run-pipeline`'s existing failure/recovery protocol. Preserve
HEAD, index entries, worktree bytes, untracked files, task branches, and task
worktrees. Do not emit `integrated` or release any task.

Once the entry precondition is satisfied, retain the current clean-tree batch
gate and per-task fallback. An approved no-op branch must obey the same entry
check. This is an entry safety boundary, not a filesystem lock against a human
editing concurrently with an already-running integration.

Regression module: `skills/two-model-sdd-pipeline/tests/test_integrate_dirty_guard.py`.
Use real disposable Git repositories and an overridden gate executable. Cover
staged, unstaged, and untracked dirt; a two-task batch; a single task; an
approved no-op; status-command failure; and ignored-workspace-only changes.
Compare file bytes, staged blobs, HEAD, branches, and ledger event types before
and after a rejected call. The clean-tree fallback must still integrate good
tasks when a sibling's gate fails.

### 3.2 F2: refresh the integrated scheduling snapshot

The tracked plan at `PLAN` is authoritative. `$WS/plan.json` is a derived
scheduling snapshot. After every invocation of `INTEGRATE_BIN` that may have
changed HEAD, reload the tracked plan before computing failed-task membership,
task counts, another wave, or final-review readiness. This includes a partly
successful batch that returns nonzero and a successful recovery integration.

Refresh the existing workspace only: preserve ledger entries, partitions,
session records, briefs, and reports. Validate the candidate before replacing
the snapshot, and use a temporary file plus atomic replacement so a failed
read/parse cannot truncate the last valid copy. Avoid copying a file onto
itself when the source already is the workspace plan. At minimum reject an
unreadable file, invalid JSON, a non-object root, a missing/non-list/empty
`tasks`, missing required task fields (`id`, `title`, `summary`, `acceptance`),
duplicate or nonpositive integer IDs, and empty/non-list acceptance criteria.
Do not continue using stale data after any refresh failure: return a clear
blocker while retaining the old snapshot for inspection.

An explicit `TOTAL` argument must not silently hide a changed task count.
Before closing or advancing after a refresh, reject a TOTAL that differs from
the current plan count. With TOTAL omitted, always derive it from the refreshed
snapshot. Preserve serial behavior except for the same explicit mismatch check.

Regression module: `skills/two-model-sdd-pipeline/tests/test_plan_refresh_after_integration.py`.
Reproduce a task adding task 2 to the tracked plan. After integration the next
wave must include task 2, not `FINAL_REVIEW`. Also cover changed dependencies
and acceptance, partial batch success, recovery integration, invalid/missing
plan data, TOTAL mismatch, source-equals-destination, and paths with spaces.
Use real refresh/scheduler logic; stub provider dispatches only where needed.

### 3.3 F3: restart execution after a resolved arbitration

Treat the latest `arbitrate_resolved` event as an execution-attempt boundary
for an incomplete task. Preserve older events as history, but do not let a
pre-boundary `red_check`, `commit`, review verdict, or failure log advance the
new attempt. A completed task keeps its existing terminal behavior.

Required progression:

1. The director returns successfully and the plan refresh succeeds. Only then
   append `arbitrate_resolved`.
2. Route to BRIEF and scaffold the corrected acceptance criteria.
3. Route to RED even if the previous attempt already committed or dispatched.
4. Before dispatch, archive prior active coder/reviewer logs, parsed review,
   and RED evidence into an attempt-specific directory inside the workspace.
   Do not overwrite an earlier archive on resume. Keep per-agent session IDs.
5. Dispatch the toolchain-selected coder on the corrected brief, resuming its
   own session when present; otherwise start fresh. The Flutter red-gate stays
   a thin delegating shim, not a second implementation.
6. Gate and review the new result using only current-attempt evidence. A fresh
   REVIEW may not parse the archived verdict. Only a fresh approval completes
   the task.

If the new dispatch is interrupted, propagate its nonzero status and do not
enter `coder-gate` using archived evidence. A subsequent genuine escalation
after the director ruling must retain the existing bounded-blocker policy;
this change must not create an unbounded director loop. No-change rulings are
allowed to retry once; a genuine repeated failure still blocks. Do not reset
or drop implementation commits or partial work during arbitration.

Regression module: `skills/two-model-sdd-pipeline/tests/test_arbitration_execution_retry.py`.
Exercise both pre-commit `TEST_DEFECT` and post-commit review `ESCALATE` through
the real router/orchestrator/task runner with deterministic dispatch stubs.
Assert corrected brief contents, coder dispatch before gate evaluation, correct
per-agent session selection, archival preservation, fresh RED requirements,
fresh reviewer output, fresh approval, interruption behavior, and bounded
re-escalation. Include histories with and without per-task ledger partitions.

### 3.4 F4: distinguish gate success from commit success

The generic path in `coder-gate` must distinguish three outcomes after the
tests and analysis pass:

| Outcome | Required behavior |
| --- | --- |
| Changes staged and commit succeeds | Keep the existing commit event, review package, and reviewer dispatch sequence. |
| No staged changes | Exit 1 with an explicit empty-commit blocker; do not dispatch review or record commit/task completion. |
| Staging, staged-diff inspection, or commit fails | Exit 1, retain useful command diagnostics, preserve changes, and do not dispatch review or record commit/task completion. |

Do not turn a commit failure into `TEST_DEFECT`, run an automatic empty commit,
or infer approval from a green suite. A `coder_round` PASS may describe test
success, but the enclosing operation must return nonzero, causing
`orchestrator`/`task-run` to stop instead of immediately routing back to CODER.
Check Git exit codes explicitly; a nonzero staged-diff result can mean changes
or an error, and those cases must not be conflated.

Regression module: `skills/two-model-sdd-pipeline/tests/test_coder_commit_outcomes.py`.
Cover a clean checkout with valid RED evidence, a failing commit hook, a staging
error, a staged-diff inspection error, and the successful commit control. Prove
that `task-run` terminates on the failed/empty paths without repeated gate or
provider calls. Do not extend this task into Flutter green-gate's separate
commit semantics; preserve that path and run its existing suite for compatibility.

## 4. File ownership and task graph

| Task | Production/documentation files | Depends on |
| --- | --- | --- |
| 1: protect integration checkout | `skills/two-model-sdd-pipeline/scripts/integrate` | none |
| 2: refresh plan snapshots | `skills/two-model-sdd-pipeline/scripts/run-pipeline`, `skills/two-model-sdd-pipeline/scripts/pipeline-workspace` | 1 |
| 3: restart resolved arbitration | `skills/two-model-sdd-pipeline/scripts/task-run`, `skills/two-model-sdd-pipeline/scripts/route-next`, `skills/two-model-sdd-pipeline/scripts/red-gate` | none |
| 4: terminate failed commits | `skills/two-model-sdd-pipeline/scripts/coder-gate` | 3 |
| 5: verify composed recovery and document it | `README.txt`, `README-LLM.md`, `CONTEXT.md` | 1, 2, 3, 4 |

At maximum parallelism 2 the intended dependency layers are {1, 3}, {2, 4},
then {5}. No production path is owned by two tasks. New test modules have
separate owners and remain outside `touches`. Task 5 additionally owns the new
`skills/two-model-sdd-pipeline/tests/test_recovery_hardening_e2e.py` module.

## 5. Validation and completion

For each task, create its regression module, run it against the old behavior,
save real failing-run evidence, implement, and rerun it. Provider stubs must
produce realistic JSONL text events and record calls; no network is required.
Use `ledger-append` or migrate deliberately seeded histories before exercising
partitioned routing. Set subprocess timeouts so a regression fails the test
instead of hanging indefinitely.

Run from the repository root with Python 3, Git, Bash, and ShellCheck available:

```bash
python3 -m unittest discover -s skills/two-model-sdd-pipeline/tests -p 'test_*.py' -v
python3 -m unittest discover -s skills/flutter-app-pipeline/tests -p 'test_*.py' -v
bash scripts/lint-shell.sh skills/two-model-sdd-pipeline/scripts/integrate skills/two-model-sdd-pipeline/scripts/run-pipeline skills/two-model-sdd-pipeline/scripts/pipeline-workspace skills/two-model-sdd-pipeline/scripts/task-run skills/two-model-sdd-pipeline/scripts/route-next skills/two-model-sdd-pipeline/scripts/red-gate skills/two-model-sdd-pipeline/scripts/coder-gate
git diff --check
```

Use the pipeline's `skills/two-model-sdd-pipeline/scripts/cmd` wrapper for
LLM-facing command output and save full reports outside tracked source files.
The operator's RED evidence for `lang=python` must be real pytest JSON-report
output, not fabricated JSON or plain unittest text. Existing unittest tests
can be run under pytest with pytest-json-report in the execution environment;
these are execution tooling, not new project runtime dependencies. Verify the
report with `red-form-check` before invoking the green gate.

Task 5 tests the composed flow: task 1 needs arbitration, a director edit adds
a later task, the fresh coder/reviewer approve, integration refreshes the plan,
and the added task executes before closing. Also verify that an integration
dirty-tree rejection and a generic commit failure halt before closing. Stub
dispatch and gates as appropriate, but keep actual task routing, plan refresh,
ledger propagation, and disposable Git integration in the exercised path.

Update the three owned documentation files with implemented behavior and
recovery guidance, then run `doc-check` at the final committed checkpoint.
Report every command and any pre-existing/environmental failures separately;
do not weaken checks to obtain green. Completion requires all four regression
groups, composed-flow coverage, and the applicable existing suites to pass.

## 6. Executor handoff and bootstrap

Read this spec and every plan constraint before editing. Compare the current
checkout with the reviewed baseline and revalidate any finding whose code has
changed. Use an isolated feature checkout. Commit/carry these two artifacts
into it before allocating task worktrees so workers can read the tracked plan.
Do not publish, push, or open a PR merely because this handoff exists.

This repository is the pipeline implementation itself. Its `package.json`
causes automatic toolchain resolution to choose Node commands that do not run
these Python/Bash regression suites. If using `run-pipeline`, seed a manual
`gate` through `ledger-append` with `lang=python`, an explicit unittest test
command, and the explicit shell lint command above before launch. Verify that
the selected coder can execute the required Python test tooling. The Flutter
suite remains a mandatory final compatibility check.

Do not blindly run the unfixed pipeline against itself: its arbitration and
commit-recovery defects are the subject of this plan. Use an independently
validated controller/runtime, or have the receiving agent execute the plan
task by task with the same RED/GREEN and review obligations. Never hot-swap
the scripts of an active run, silently install a newer pipeline, or bypass
scope/RED/review checks. If a runtime scope issue arises, document the exact
blocker rather than adding test files to `touches` or weakening existing tests.

The receiving agent owns implementation and verification. This planning task
creates only the spec and machine-readable plan; it does not start agents,
modify runtime scripts, commit, or launch the pipeline.
