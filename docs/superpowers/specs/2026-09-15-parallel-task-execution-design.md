# Parallel Task Execution — Design (two-model-sdd-pipeline engine)

**Date:** 2026-09-15
**Target:** `skills/two-model-sdd-pipeline` (engine). `flutter-app-pipeline` inherits it unchanged.
**Supersedes:** the pre-review spec `parallel-agent-execution-spec.md` (written at
`ea72521`, before the repo-review fixes landed). This document reconciles that spec
with the engine as it actually exists at `4aec81a`.
**Status:** approved direction (4 decisions locked, see §1.3); awaiting user review of
this written spec before `writing-plans`.

---

## 1. Context

### 1.1 Goal

Today `run-pipeline` is strictly serial: `first_incomplete` picks the lowest-id task
without a `task_complete`, the orchestrator drives that one task, repeat. This design
lets **mutually independent tasks run concurrently**, without changing the founding
rule: *LLMs reason; scripts decide*. Parallelism is a scheduling decision computed by
scripts from declared plan data — never a runtime judgment by an LLM.

### 1.2 The model being replicated

Software teams parallelize by (1) freezing shared interfaces before implementation,
(2) exclusive file ownership, (3) isolated working copies, (4) one integration gate
with tests. The fork already has primitives for all four — `touches`, `interface-check`,
per-task commits, `final-gate`. What is missing is a **scheduler** and **worktree
isolation**.

### 1.3 Locked decisions (user, 2026-09-15)

1. **Ledger concurrency = per-worktree shards + `ledger-merge`** (not `flock` on a
   shared ledger). Rationale: `pipeline-workspace` resolves its directory from
   `git rev-parse --show-toplevel` (`pipeline-workspace:42-44`), so a linked worktree
   already gets its own `.superpowers/two-model/<slug>/`; shards fall out of the
   existing design, need no locking primitive, and are portable on Windows.
2. **`--max-parallel` default = 2.** Concurrent `opencode run` dispatches cost real
   tokens and rate-limit; 2 is the safe default.
3. **Phased delivery in waves**, one `plan.json`, each wave leaving the tree green and
   the serial path working. The worktree/integration path only becomes active when the
   user passes `--max-parallel N>1`.
4. **Every new/changed script follows the `write-script` skill** (exit-code families,
   ledger-append as sole writer, `cmd`/`dispatch` boundaries, idempotency, non-destructive
   defaults, Windows/git-bash rules, resource-profile header, one unit test per script +
   README/doc-check). See §3.6.

### 1.4 Category Skeleton — N/A

The brainstorming skill's Category Skeleton (generic/specific category + original
implementations) drives template search for **new apps**. This is an **engine change**,
not an app; no template search or per-task dependency research applies. Recorded as an
explicit, justified deviation.

---

## 2. Reconciled baseline (what already exists at `4aec81a`)

Every "old spec" assumption, re-verified against the live files:

| Old-spec assumption | Reality | Consequence for this design |
|---|---|---|
| `depends_on` must be added | Exists; read by `brief-scaffold:59`, `interface-check:46` | Only needs to become **authoritative for scheduling** + documented |
| `interface-check` is unwired (H1) | Wired post-commit as `interface_touched` (`coder-gate:245`, `green-gate:112`) | Reuse as the post-merge guard; **fix** its `depends_on`-as-path bug (`interface-check:46`) |
| `keep-discard` would DISCARD every task (H3) | Fixed; exempts newly authored tests via `pathclass.is_test_path` | Reuse as-is; not part of this extension |
| `ledger-append` is unlocked, "prefer shards `ledger-N.jsonl`" | Partition `ledger-task-<N>.jsonl` + global mirror exists (`dca5ae2`) but as a **read-perf** feature; two unlocked `>>` appends | Add **shard-per-worktree** + `ledger-merge`; guard `ledger-migrate` (its `rm -f ledger-task-*.jsonl` is hostile to concurrency) |
| `orchestrator` is a drifted duplicate (H2) | Collapsed; it is the single dispatch table (`H2` done) | The wave loop reuses `orchestrator` with cwd inside each worktree |
| `red-gate`s diverged (H4) | Unified; Flutter file is a shim | Untouched |
| `final-gate` iterates `seq 1..TOTAL`, short-circuits on `HEAD == last commit sha` | Confirmed (`final-gate:64-86`, `54-62`) — assumes one linear commit sequence | Needs new "no worktree / no unmerged task branch / no failed integration" checks |
| — | `dispatch --workdir` exists but **no caller** (`dispatch:46`) | Worktree isolation can use the cwd of the whole gate chain instead |
| — | `max-parallel`, `flock`: **0** hits in code. `wave` appears once as an advisory comment | All of the scheduler is new |

The single pre-existing hook is `coder-gate:239-241`:
> "surface a touched cross-task interface for the revisor and the **(future) wave
> scheduler**. Advisory only — sequential ordering is already enforced by depends_on."

---

## 3. Design

### 3.1 Scheduling model

- The plan declares, per task, `depends_on: [task_ids]` (empty = no predecessor) and
  `touches: [paths]`. Both are **authoritative** for scheduling.
- A **wave** is a maximal set of ready tasks with pairwise-disjoint `touches`, capped
  by `--max-parallel`.
- A task is **ready** when every id in `depends_on` is complete and the task itself is
  not complete.
- A task is **complete** when it has a `task_complete` entry and no newer
  `integration_failed` entry (see §3.4).
- Any type/interface/model consumed by ≥2 tasks must be authored in an earlier wave
  (or the plan skeleton) and frozen before the consuming wave runs. **Contract-producing
  tasks are always a wave of their own** (their `touches` overlap the consumers'
  `depends_on`-implied need, so the disjointness rule already defers them).
- Corrective work (`corrects: N`) is **never given its own parallel slot**. A corrective
  episode is owned inline by the parent task's `task-run` (in the parent's worktree, see
  §3.2); `wave-next` never schedules a `corrects` task as a wave member. Because
  worktrees isolate files, a parent's corrective episode does not contend with sibling
  tasks in the same wave — the "runs alone" rule is about *slots*, not global serialization.

### 3.2 Components

All new/changed scripts live in `skills/two-model-sdd-pipeline/scripts/`. All honor the
existing env-override convention where relevant.

#### `touches-overlap WORKSPACE ID [ID...]` (new)

- Reads `<ws>/plan.json`; compares the declared `touches` of the given ids **pairwise**
  by exact path equality (the same comparison `interface-check:49` already uses).
- Exit `0` disjoint (`TOUCHES-OVERLAP: disjoint`); `1` overlap — prints the conflicting
  pairs and the shared files to stderr; `2` usage / missing plan / unknown id.
- Pure read; writes nothing.

#### `wave-next WORKSPACE [MAX_PARALLEL]` (new)

- Reads `<ws>/plan.json` and the merged ledger (`<ws>/ledger.jsonl`).
- If every task is complete → print `FINAL_REVIEW`, exit `0`.
- Compute the ready set (§3.1). If empty and tasks remain → stderr
  `WAVE_EMPTY: nothing runnable (blocked)` and exit `1`.
- If any ready task is a corrective (`corrects`) → emit exactly that task (`RUN <id>`),
  exit `0` (never parallelized). Normally the parent's `task-run` resolves its corrective
  inline, so this is a defensive guard for an interrupted/leftover corrective.
- Otherwise greedily select ready tasks in ascending id order, adding a task only when
  its `touches` are disjoint from every already-selected task (reusing the
  `touches-overlap` logic), stopping at `MAX_PARALLEL` (default 2). Emit one
  `RUN <id>` line per selected task.
- Exit `2` usage. `wave-next` never routes inside a task — `route-next` remains the
  per-task router, unchanged.

#### `ledger-merge INTEGRATION_WS SOURCE_LEDGER [SOURCE_LEDGER...]` (new)

- Re-emits each source entry **through `ledger-append`** — the only ledger writer
  (write-script §2) — parsing the source JSON and replaying its
  `type`/`task`/`summary`/extras, so JSON escaping and the partition mirror stay in one
  place. It never `echo … >>` a ledger by hand.
- Skips `gate` entries (branch-level, already present) and content-identical entries
  (identity = the entry minus `ts`, since `ledger-append` restamps it — idempotent
  re-runs, write-script §5: re-derive, don't accumulate).
- Rebuilds partitions via `ledger-migrate` after the merge.
- Exit `0` merged; `2` usage.

#### `worktree-alloc WORKSPACE TASK` / `worktree-release WORKSPACE TASK` (new)

`worktree-alloc`:
- `git worktree add <repo>/.superpowers/two-model/worktrees/task-<N> -b task/<N> <integration HEAD>`
  (the worktrees dir sits under the already-gitignored `.superpowers/two-model/`).
- Creates the worktree's own workspace dir and seeds it: `plan.json` copied from the
  integration workspace, a fresh `ledger.jsonl` containing **only** the branch `gate`
  entry copied from the integration ledger.
- Ledgers `worktree_alloc` (task `N`) into the **integration** ledger.
- Prints `WORKTREE=<path>` and `WS=<worktree_ws>` (one per line).
- Exit `0`; `1` already allocated; `2` usage.

`worktree-release`:
- Refuses unless the task branch is merged into the integration HEAD; then
  `git worktree remove --force <path>`, `git worktree prune`, `git branch -d task/<N>`.
- Ledgers `worktree_release`. **Never** auto-removes on failure (debugging parity with
  `session-clean`).
- Exit `0` released; `1` not merged / not found; `2` usage.

#### `task-run WORKSPACE TASK TOTAL` (new — pure extraction)

- The per-task lifecycle currently inlined in `run-pipeline:206-386`, scoped to one
  task: loop `orchestrator` → parse `OUTCOME` → on `REVIEW` run `parse-review` + ledger
  `review_outcome` + (APPROVED) `task_complete` + `reconcile_parents`; on `SEND_BACK`
  run the diretor `CORRECTIVE` branch; on `ESCALATE` run the `ARBITRATE` branch.
- Operates on whatever working tree its **cwd** resolves to, using the workspace passed
  in. This is the unit that runs inside a worktree, and the unit the serial path runs in
  the repo root.
- Exit `0` task complete; `1` task ended without completion (escalated/blocked);
  `2` usage.

This extraction is a **refinement over the old spec** (which assumed `orchestrator`
alone could be the per-task unit). `orchestrator` deliberately hands `REVIEW`/
`CORRECTIVE`/`ARBITRATE` back to its caller (`orchestrator:78-83`), so a per-task loop
must own them; extracting it keeps **one** implementation shared by the serial and wave
paths (the H2 lesson: never two copies of the routing logic).

#### `integrate WORKSPACE TASK [TASK...]` (new — the integrator, script not LLM)

- Runs after a wave's `task-run` processes return. For each task in **ascending id
  order**:
  1. `git merge --no-commit --no-ff task/<N>` in the integration working tree.
  2. Conflict → `git merge --abort`; ledger `integration_failed N conflict`; continue.
  3. Run the full gate (`run-gates`, or `green-gate --no-commit` for `lang=flutter`)
     — the **full suite after each individual merge**, never once at wave end, so a
     break is localized to the task that caused it.
  4. Red → `git merge --abort`; ledger `integration_failed N gates`; continue.
  5. Green → `git commit --no-edit`; ledger `integrated N sha=<sha>`; `worktree-release`.
- After the code outcome for a task is known, `ledger-merge` that task's worktree ledger
  into the integration ledger.
- Exit `0` all integrated; `1` ≥1 `integration_failed` (the rest integrated); `2` usage.

**Refinement over the old spec:** the old spec said "do not roll back the wave" on
failure. This design keeps the *wave* intact but rolls back the *individual* failing
merge (`--no-commit` + `--abort`), so the integration branch is never left red. A red
integration branch would poison every subsequent task in the wave and force a global
re-run — strictly worse. The failed task is routed to a corrective (below).

#### `run-pipeline` (changed)

```
run-pipeline PLAN_FILE [TOTAL] [--no-push] [--max-parallel N]
```

- `N` default `2`.
- **`N == 1`**: the serial path is behavior-preserving (advances via `route-next`
  instead of `first_incomplete`; the ledger sequence is asserted by a regression test) —
  task-run in the repo root, no worktrees, no `integrate`. This is the explicit
  regression contract: the serial flow stays reachable.
- **`N > 1`**: wave loop
  ```
  loop:
    w = wave-next WS N          # RUN ids | FINAL_REVIEW | blocked
    FINAL_REVIEW -> break
    worktree-alloc for each w
    run task-run per worktree in parallel (bounded by N); wait
    integrate WS w...           # merge + per-merge full suite
    for each task the integrator failed or that ended un-approved:
      diretor corrective/arbitrate, then task-run that task ALONE (max-parallel 1)
      integrate that task again
  ```
- Excess ready tasks beyond `N` are simply deferred: `wave-next` never emits more than
  `N`, so the next loop iteration picks them up.
- Integration-failure recovery is **bounded and does not self-heal**. On `integrate`
  exit `1` the driver makes exactly **one** re-attempt per failed task (reusing the
  existing worktree — `worktree-alloc` exit `1` — and running `task-run` alone), then
  **blocks** with an actionable message if it still fails; it never loops unbounded.
  A true in-place corrective is **deferred**: re-opening a task that already has
  `task_complete` is forbidden by `route-next`'s decision order (the `has_complete`
  rule fires before the `SEND_BACK` rule), so an injected episode is inert. Changing
  that order means changing the already-reviewed router (the C1 `ARBITRATE` work) and
  is out of scope here. This is consistent with the fork's stance that a human blocker
  beats a silent/unbounded spend.
- Closing (`final-gate` → package → diretor) and push/PR are unchanged except for the
  new `final-gate` checks.

#### `final-gate` (changed)

Add blockers (existing checks unchanged):
- a `worktree_alloc` with no matching `worktree_release`;
- a `task/<N>` branch still present for a complete task;
- a task whose newest event is `integration_failed` without a later completion;
- a pending integration (worktree allocated) at closing time.

### 3.3 Data flow (one wave, `N=2`)

```
plan.json ──> wave-next ──> RUN 3 / RUN 5
                              │
              worktree-alloc 3│  worktree-alloc 5
                              ▼                  ▼
                   (cd wt3) task-run 3    (cd wt5) task-run 5     ← parallel
                              │                  │
                         wt3/ledger          wt5/ledger
                              └────────┬─────────┘
                                  integrate 3 5      ← ascending id, per-merge suite
                              merge task/3 → gates → merged
                              merge task/5 → gates → conflict/red -> abort + integration_failed
                              ledger-merge → integration ledger
                                       │
                          (failed 5) diretor corrective, task-run 5 alone, integrate 5
                                       ▼
                              next wave / FINAL_REVIEW
```

### 3.4 Error handling

- **Merge conflict** → `merge --abort`, `integration_failed N conflict`; the task stays
  un-integrated and is a bounded, non-self-healing blocker: exactly one re-integrate
  attempt in its existing worktree (meaningful for an un-approved task; a no-op for a
  conflict on an approved one), then a human block (§3.2).
- **Post-merge gate red** → `merge --abort`, `integration_failed N gates`; same path.
- **Dispatch interrupted** (`rc=124`) → already terminal via `dispatch_interrupted`
  (`red-gate:64-74`); `task-run` returns non-zero and the task is not integrated.
- **Escalation (`TEST_DEFECT`/`scope_violation`)** → `task-run` runs the `ARBITRATE`
  branch; if arbitration does not resolve, `route-next` already exits 1 (C1) and the
  task ends un-approved.
- **Blocked wave** (`WAVE_EMPTY`, exit 1) → `run-pipeline` reports BLOCKED and exits 1,
  matching today's contract (fix + re-run continues).
- Never roll back the *wave*; only the individual failing merge.

### 3.5 Testing strategy

Standard `unittest` suites in `skills/two-model-sdd-pipeline/tests/` (run by
`run-tests.sh`), following the existing temp-git-repo pattern used by
`test_run_pipeline.py`:

- `touches-overlap`: disjoint / overlap / usage / unknown id.
- `wave-next`: readiness on `depends_on`; disjoint-only selection; `MAX_PARALLEL` cap;
  corrective emitted alone; `FINAL_REVIEW`; `WAVE_EMPTY` → exit 1.
- `ledger-merge`: skips `gate`, dedups identical lines, rebuilds partitions, idempotent.
- `worktree-alloc` / `worktree-release`: creates/removes the worktree + branch, seeds
  the ledger, refuses release when unmerged, records the ledger entries.
- `integrate`: clean merge → `integrated` + release; conflict → abort +
  `integration_failed conflict`; gate-red → abort + `integration_failed gates`; the
  suite runs **after each merge** (assert via a fake gate that fails on the 2nd merge).
- `task-run`: single-task behavior identical to today's inline loop.
- `run-pipeline --max-parallel 1`: regression — the serial path is behavior-preserving
  (advances via `route-next` instead of `first_incomplete`; the ledger sequence is
  asserted by a regression test).
- `final-gate`: each new blocker fires, and none false-positives on a clean serial run.

### 3.6 Script conventions (binding — `write-script`)

Every new/changed script obeys the `write-script` skill. The non-negotiable points for
this extension:

- **Exit-code families (write-script §1).** `wave-next` and `touches-overlap` are
  *deciders*: `0` clean/routed, `1` domain failure, `2` usage — no invented fourth
  meaning. `integrate` and `task-run` follow the loop-family convention: `0` success,
  `1` failure/blocked, `2` usage. Each file header documents its own table.
- **Ledger (write-script §2).** `ledger-append` is the sole writer. New types —
  `worktree_alloc`, `worktree_release`, `integrated`, `integration_failed` — all get a
  named consumer: `wave-next`/`final-gate` read them for completion and closing; none is
  a "comment with extra steps". Every terminal outcome ledgers its reason before a
  non-zero exit (the `dispatch_interrupted` lesson).
- **Compression (write-script §3).** `integrate` runs the full gate through the existing
  `run-gates` / `green-gate --no-commit` (already `cmd`-wrapped); no new direct shell-out
  to `flutter`/`dart`. New commands would extend `cmd`'s `case`, not bypass it.
- **Dispatch (write-script §4).** `task-run` spawns no LLM itself; it drives
  `orchestrator` → `red-gate`/`coder-gate` → `dispatch` (and the diretor via `dispatch`).
  No second `opencode` call path.
- **Idempotency (write-script §5).** All scripts re-derive from plan + ledger; a re-run
  of `run-pipeline` continues where it stopped. No counters, no process-local state.
- **Fail-fast (write-script §6).** Validate at the top; capture callee exit codes with
  `rc=0; … || rc=$?`, never `cmd; rc=$?`.
- **Non-destructive default (write-script §7).** `worktree-release` runs only on a
  successful, merged integration; it never auto-removes on failure. `integrate` aborts
  the individual failing merge rather than committing red.
- **Observability (write-script §9).** Reports to files; stdout carries only verdicts and
  `OUTCOME:` lines.
- **Windows/git-bash (write-script §10).** `PYTHONUTF8=1` + `PYTHONIOENCODING=utf-8`;
  `cygpath -w` for any path handed to native Python; tolerate CRLF; no heredoc inside a
  pipe (use `python3 -c '…'`); avoid `awk -v` with Windows paths in `ledger-merge`.
- **Resource-profile header (write-script §11).** Each new script's header states:
  dispatch (none — no LLM spawn), context tokens (stdout not LLM-facing), ledger I/O
  (partition vs global), subprocess shape, wall-clock (parallelizable vs serial-chain),
  git (index/diff/commit).
- **Tests + docs (write-script §12).** One `tests/test_<script>.py` per script, asserting
  exit codes; `doc-check` requires `README.txt`/`README-LLM.md` updated in the same
  change.

---

## 4. Invariants preserved

- **LLMs reason; scripts decide** — the scheduler is a script reading declared plan data.
- **`route-next` unchanged** — the per-task router inside each worktree.
- **`red-gate` / `coder-gate` / `green-gate` / `red-form-check` / `parse-review`
  untouched** — they run identically, just inside a worktree with a task-scoped
  workspace.
- **Agent prompts and roles untouched** — no agent knows it is running in parallel.
- **ADR-0003 (cache/session)** — within-task `--continue --session` still applies per
  worktree.
- **`scripts/cmd` + RTK** — untouched; each process writes to its own workspace file.
- **Ledger via script** — the integrator appends through `ledger-append`/`ledger-merge`,
  never prose.
- **Workers never commit** — only the gate chain (inside a worktree) and the integrator
  commit.

---

## 5. Plan-authoring changes (Agente estratégico, Phase 2c)

- `depends_on` is now **binding for scheduling**, not just brief metadata: empty = no
  predecessor; a task is dispatched only when all its `depends_on` are complete.
- `touches` is **authoritative for scheduling**: a task is parallelized only when its
  `touches` are disjoint from every other task in the same wave.
- Contract-producing tasks (a shared type/interface/model consumed by ≥2 tasks) are a
  wave of their own and must land before the consuming wave.
- Corrective tasks (`corrects: N`) are never parallelized.
- Fix `interface-check`'s bug: it currently concatenates `depends_on` (task **ids**) with
  `touches` (paths) as if both were paths (`interface-check:46`); `depends_on` must be
  dropped from the file-consumption set.
- Docs to update (task in the plan): `skills/two-model-sdd-pipeline/SKILL.md` (schema +
  rules), `skills/writing-plans/SKILL.md`, `skills/brainstorming/SKILL.md` (plan
  completeness list), `README.txt`, `README-LLM.md`, `CONTEXT.md`.

---

## 6. ADRs

- **ADR-0010 — Wave scheduling is plan-derived, not runtime-inferred.** `depends_on` +
  `touches` are authoritative; the scheduler is a script, never an LLM judgment.
  (Gates: reversal cost — high; reach — project-level; rejected alternative —
  LLM-inferred readiness.)
- **ADR-0011 — Worktree-per-task isolation and per-worktree ledger shards.** Supersedes
  the single-workspace/single-linear-commit assumption; the integrator merges shards.
  (Gates: reversal cost — high; reach — project-level; rejected alternative —
  `flock` on one shared ledger.)
- **ADR-0012 — Integration is a script-owned serial merge gate.** No agent merges its
  own work; the integrator merges in deterministic id order with a full suite after
  each merge. (Gates: reversal cost — high; reach — project-level; rejected
  alternative — merge at wave end / agent-driven merge.)

---

## 7. Implementation order (plan waves)

Each wave leaves the tree green and the serial path intact.

1. **Foundations** — `touches-overlap` + tests; fix `interface-check`'s `depends_on`
   bug + tests; plan-authoring rules in `SKILL.md` / `writing-plans`.
2. **Ledger shards** — `ledger-merge` + tests; `ledger-migrate` concurrency guard.
3. **Worktrees** — `worktree-alloc` / `worktree-release` + tests.
4. **Scheduler** — `wave-next` + tests.
5. **Extraction** — `task-run` (pure refactor; the serial path is behavior-preserving —
   advances via `route-next` instead of `first_incomplete`; the ledger sequence is
   asserted by a regression test).
6. **Integrator** — `integrate` + `final-gate` additions + tests.
7. **Driver** — `run-pipeline` wave loop + `--max-parallel` (default 2), with the
   `--max-parallel 1` regression test.
8. **Docs + ADRs** — `README.txt`, `README-LLM.md`, `CONTEXT.md`, `SKILL.md`;
   ADR-0010/0011/0012.

---

## 8. Out of scope / deliberately unchanged

- No new tiers, agents, or prompts.
- No change to the revisor's sole-semantic-guarantee role.
- No knowledge graph.
- No `flock`/lockfile primitive (shards make it unnecessary).
- No auto-removal of a worktree on failure.
- The Flutter layer inherits the engine with no Flutter-specific change.
