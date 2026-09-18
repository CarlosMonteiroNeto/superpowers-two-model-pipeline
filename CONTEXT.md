# CONTEXT.md — Glossary (two-model pipeline)

Resolved terms and decisions that persist beyond any single branch. Branch-specific
design lives in the spec; this file holds the vocabulary and binding constraints the
pipeline runs on. Updated as terms resolve during brainstorming (Incremental
Persistence — architectural path only).

## Roles and actors

- **Script CEO (Orchestrator)** — the deterministic, modular bash layer that owns the
  per-task flow: gates, test/analyze decisions, subagent dispatch, routing, and
  commits. A thin driver script (`orchestrator`, topped by `run-pipeline` for
  full-branch runs) plus specialized sub-scripts (red-gate, green-gate,
  brief-scaffold, coder-gate, coder-agent-for, dispatch, cmd, route-next,
  keep-discard, interface-check, review-package, ledger-append). Script CEO is never an
  LLM; its verdicts are exit codes and its outputs are files.
- **Agente estratégico** — the interactive OpenCode session the developer
  opened for brainstorming. Produces the design spec and a COMPLETE `plan.json`
  (tasks with acceptance, spec_refs, touches, depends_on; no expected_red), then
  DONE. A separate clean session launches `run-pipeline`. Never in the per-task
  loop.
- **Agente diretor** — Strategic tier (`two-model-task-generator`). Punctual
  task owner: on corrective/arbitrate the script dispatches it with
  script-controlled context (findings + FULL `plan.json` + target task + cited
  spec_refs), resuming only within the same episode; closing is a one-shot
  curated package (plan + spec + consolidated diff + ledger). No EXPAND, no
  cross-branch persistent session.
- **Agente operador** — Operational tier (`opencode-go/deepseek-v4.1-flash`). Owns the RED/GREEN loop:
  receives the scaffolded brief, authors RED tests, RUNS them and saves the machine-readable output
  (form-checked by the script), DECLARES and confirms the expected reason before implementing (a
  self-check, not a guarantee), then writes implementation code and runs the tests green. May run
  test/analyze/format, never git; Script CEO verifies the RED form and decides the authoritative
  gate. Context is zeroed per task; retries resume the same session within a task.
- **Agente revisor** — Strategic tier (`opencode-go/deepseek-v4.1-flash`). Reviews
  only compiler-approved code (tests + syntax already green). Evaluates design,
  architecture, spec compliance (incl. spec-refs alignment), interface
  discipline, and test-vs-acceptance fit. Returns a structured JSON
  verdict (APPROVED / SEND_BACK / ESCALATE + findings + minors). Context kept during
  the task's correction loops; zeroed after the task is approved.
- **Strategic Coder** — REMOVED. Escalation no longer dispatches a strategic coder;
  TEST_DEFECT escalates to Agente diretor for task viability arbitration.

## Deterministic gates and flows

- **run-pipeline** — top-level Script CEO driver, invokable anywhere with a
  tracked plan: loops route-next → execute until FINAL_REVIEW → closing →
  push+PR. No Agente estratégico in the loop.
- **brief-scaffold** — mechanically scaffolds task briefs from plan tasks
  (statement, acceptance, spec_refs, reason-declaration and machine-readable RED
  instructions). No `expected_red`. No LLM call.
- **red-gate** — verifies the scaffolded brief exists. On success, Script CEO
  dispatches Agente operador directly (item 4), then chains coder-gate.
  No main-agent intermediation.
- **green-gate** — chains full suite + `flutter analyze` + format check + commit.
  The test/analyze pass/fail decisions are made inside the script (item 2). On
  success (after the RED-evidence check), Script CEO commits, then dispatches Agente
  revisor directly (item 3).
- **coder-gate** — unbounded retries until green; verifies the operador's saved
  RED evidence by FORM via `red-form-check` (suite loaded, ≥1 test executed,
  failed as assertion/runtime — never a compile/load red); the keep-discard
  scope gate runs before commit (out-of-scope → scope_violation → ARBITRATE),
  and interface-check is wired post-commit as an advisory ledger entry. Only
  TEST_DEFECT leaves the loop.
- **route-next** — deterministic router; Script CEO executes its emitted action.
  Actions: BRIEF / RED / CODER / REVIEW / CORRECTIVE / ARBITRATE /
  NEXT / FINAL_REVIEW. `STRATEGIC` action removed (Strategic Coder removed).
  `arbitrate_resolved` newer than the last escalation re-emits BRIEF; a
  re-escalation after a ruling is exit 1 (arbitration did not resolve);
  `scope_violation` escalates like `escalated`; the task count is read from
  JSON, never an `"id"` grep.
- **dispatch** — NEW script. Headless subagent launcher: `opencode run --agent
  <coder|reviewer|task-generator> --dir <worktree> --file <brief> --format json --prompt <filled>`.
  Fix/correction rounds append `--continue --session <id>`. Full JSON event stream
  teed to `<ws>/task-N-coder.log` / `<ws>/task-N-reviewer.log` for observability,
  plus a live progress digest on stdout.
- **cmd** — command runner; RTK-compressed LLM-facing stdout, full output to files.
  RTK filter map extended: `flutter test` → `rtk test`, `flutter analyze` → `rtk err`,
  git diff → `rtk diff`, JSON → `rtk json`.
- **coder-agent-for** — maps a resolve-toolchain lang to the operador variant
  (`two-model-coder-{python,node,rust,go}`) whose bash allowlist can run that
  ecosystem's tests; used by both red-gates, coder-gate, and the corrective path.

## Parallel task execution (2026-09-15)

- **wave** — a maximal set of ready tasks with pairwise-disjoint `touches`,
  capped by `--max-parallel` (default 2). Computed by `wave-next` from
  `plan.json` + the merged ledger; never inferred by an LLM (ADR-0010). A task
  is **ready** when every id in `depends_on` is complete and it is not itself
  complete; **complete** means a `task_complete` (or `integrated`) entry with no
  newer `integration_failed`.
- **ledger shard** — the per-worktree workspace ledger
  (`<worktree>/.superpowers/two-model/<slug>/ledger.jsonl`). A worktree has its
  own toplevel, so `pipeline-workspace` gives it its own workspace; the shard is
  seeded with only the branch `gate` entry. On wave close `ledger-merge` folds it
  into the integration ledger through `ledger-append` (ADR-0011).
- **integration branch** — the branch `run-pipeline` runs on; task branches
  (`task/<N>`) are merged into it one at a time by `integrate`. It is never left
  red: a conflict/red/commit failure aborts only the failing merge and ledgers
  `integration_failed` (ADR-0012).
- **task worktree** — one git worktree under
  `.superpowers/two-model/worktrees/task-<N>` on branch `task/<N>`, allocated by
  `worktree-alloc` from the integration HEAD and released by `worktree-release`
  only once the branch tip is proven merged (ADR-0011).

## Context and cost rules

- **Context retention:** operador and revisor keep their sessions until the
  revisor approves the task (within-task fix/correction loops resume the same
  session). Both are zeroed at task approval; fresh dispatch per task.
  Agente diretor is punctual: it resumes only within one corrective/arbitrate
  episode, and closing is one dispatch with a curated package — no cross-branch
  persistent session.
- **Observability:** the developer watches operador/revisor progress via the
  live dispatch digest plus workspace log files (teed by `dispatch`);
  headless subagent sessions never pollute the main session's
  history.
- **RTK compression:** every command an LLM could see runs through `cmd`;
  RTK is the pipeline's context-compression layer, not an optional extra.

## Category Skeleton

The **Category Skeleton** is a REQUIRED output of Phase 1a brainstorming. The
spec cannot be written without it. It consists of three fields in this exact
order:

1. **generic category** — the broad app family (e.g. POS, marketplace, CMS)
2. **specific category** — the niche within that family (e.g. women's fashion POS)
3. **original implementations** — the features that make it yours (e.g. voice
   command, auto-calc installments)

These fields drive downstream research: the generic + specific category compose
the template search query, and each original implementation becomes a per-task
pub.dev dependency-research target in Phase 2a.

## Decision points locked during brainstorming (2026-09-02)

- Items 1–7 of the pipeline-change request mapped in the design spec.
- Strategic Coder tier removed — confirmed by developer.
- C owns its RED/GREEN loop (runs its own tests, ADR-0007); the authoritative test/analyze decisions still live inside the script — confirmed.
- Loop: unbounded retries until green, no failure counting — confirmed.
- Operational tier model: `opencode-go/deepseek-v4.1-flash` (C). Strategic tier:
  `opencode-go/deepseek-v4.1-flash` (D and B-side judgment). The README-LLM variant
  table is stale and will be corrected (no `variants` block exists in opencode.jsonc).
- Final review via `/new` + clean context — confirmed.
- Subagent headers: fixed templates + deterministically-resolved per-task values.

## Decision points locked during brainstorming (2026-09-12)

- Brainstorming is decoupled: a prior session produces spec + complete
  `plan.json`; a separate clean session launches `run-pipeline`. The script is
  stateless toward the calling session (reads only the plan file and the ledger).
- `expected_red` is removed. RED integrity = deterministic form check
  (`red-form-check`) + operador reason pre-approval (self-check) + revisor as the
  SOLE independent semantic guarantee.
- The Agente diretor no longer expands; it is a punctual corrective/arbitrate/
  closing owner. Corrective/arbitrate get the full plan.json plus findings and
  the target task; closing gets the curated package.
- The interactive session is never the exception owner (cache/cost: a persistent
  session re-bills its accumulated prefix after TTL expiry).
- Holistic review stays artifact-driven (plan + spec + diff + ledger); the fix
  for missing holism is a stronger spec, not reopening the brainstorming session.
- ADR-0008 records this and supersedes ADR-0006 (amends ADR-0001/0007).

## Decision points locked during brainstorming (2026-09-15)

- Parallel tasks: `depends_on` + `touches` are scheduling-authoritative; waves
  are computed by `wave-next`, never inferred by an LLM (ADR-0010).
- Isolation: one git worktree + `task/<N>` branch per task, with a per-worktree
  ledger shard merged by the integrator (ADR-0011).
- Integration: `integrate` is a script-owned serial merge gate, full suite after
  each merge, aborting only the failing merge (ADR-0012).
- Defaults: `--max-parallel 2`; `--max-parallel 1` is the serial path,
  behavior-preserving (advances via `route-next` instead of `first_incomplete`;
  the ledger sequence is asserted by a regression test) - no worktrees, no
  `integrate`.
- Integration failure is a bounded blocker that does not self-heal: exactly one
  re-attempt per failed task in its existing worktree, then a human block. A
  true in-place corrective (re-opening a `task_complete` task) is **deferred** —
  `route-next`'s `has_complete` rule fires before `SEND_BACK`, so an injected
  episode would be inert; changing that order means changing the reviewed router
  and is out of scope.

## Recovery hardening (2026-09-17)

Four reproduced defects were repaired; each is an entry barrier, not a new
protocol.

- **Dirty integration checkout (F1).** `integrate` refuses to run from a dirty
  checkout before any merge/reset/release: staged changes, unstaged tracked
  edits, and non-ignored untracked files block, and a failing `git status`
  blocks too (fail closed). Rejection exits 1, identifies the dirty paths,
  ledgers `integration_failed N "dirty worktree"` for every requested task, and
  preserves HEAD, index, bytes, branches, and worktrees. The tracked plan is
  expected to be committed before a run (spec §6).
- **Stale scheduling snapshot (F2).** The tracked plan at `PLAN` is
  authoritative; `$WS/plan.json` is a derived snapshot. After every `integrate`
  that may change HEAD (including a partial nonzero batch and a successful
  recovery) `run-pipeline` refreshes the snapshot via `pipeline-workspace
  --refresh` before failed-task membership, task counts, the next wave, or
  closing. The refresh validates the minimum schema and replaces the snapshot
  atomically; a failure blocks and keeps the last valid copy. An explicit
  `TOTAL` that differs from the refreshed count blocks before advancing.
- **Resolved arbitration (F3).** The newest `arbitrate_resolved` is an
  execution-attempt boundary for an incomplete task: pre-boundary `red_check`,
  `commit`, review verdict, or failure log never advances the new attempt.
  `task-run` appends `arbitrate_resolved` only after the diretor returns and the
  refresh succeeds; the router then emits BRIEF then RED; `red-gate` archives
  the prior attempt's evidence into `<ws>/attempt-<k>/` (never overwriting an
  existing archive, keeping per-agent session records) and resumes the
  toolchain-selected coder. A fresh review may not parse the archived verdict,
  and a re-escalation after a ruling remains a bounded human blocker.
- **Gate vs commit success (F4).** In the generic `coder-gate`, a green suite is
  not commit success: a `git add` error, a staged-diff inspection error, an
  empty index, and a failed `git commit` each exit 1 with an explicit blocker,
  no revisor dispatch, no `commit`/`task_complete`, and the changes preserved.
  It is never converted to TEST_DEFECT, never an automatic empty commit, and
  approval is never inferred from a green suite; the exit stops
  `orchestrator`/`task-run` instead of re-routing to CODER.

Bounded re-escalation is preserved: a genuine second escalation after a ruling
still exits 1 (`arbitration did not resolve`), so the new attempt cannot become
an unbounded director loop.