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
  brief-scaffold, dispatch, cmd, token-kill, route-next, review-package,
  ledger-append). Script CEO is never an
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
- **Agente operador** — Operational tier (`opencode-go/deepseek-v4-flash`). Owns the RED/GREEN loop:
  receives the scaffolded brief, authors RED tests, RUNS them and saves the machine-readable output
  (form-checked by the script), DECLARES and confirms the expected reason before implementing (a
  self-check, not a guarantee), then writes implementation code and runs the tests green. May run
  test/analyze/format, never git; Script CEO verifies the RED form and decides the authoritative
  gate. Context is zeroed per task; retries resume the same session within a task.
- **Agente revisor** — Strategic tier (`opencode-go/muse-spark-1.3-contributor`). Reviews
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
  failed as assertion/runtime — never a compile/load red); red-integrity
  pre-commit when a snapshot exists. Only TEST_DEFECT leaves the loop.
- **route-next** — deterministic router; Script CEO executes its emitted action.
  Actions: BRIEF / RED / CODER / REVIEW / CORRECTIVE / ARBITRATE /
  NEXT / FINAL_REVIEW. `STRATEGIC` action removed (Strategic Coder removed).
- **dispatch** — NEW script. Headless subagent launcher: `opencode run --agent
  <coder|reviewer|task-generator> --dir <worktree> --file <brief> --format json --prompt <filled>`.
  Fix/correction rounds append `--continue --session <id>`. Full JSON event stream
  teed to `<ws>/task-N-coder.log` / `<ws>/task-N-reviewer.log` for observability,
  plus a live progress digest on stdout.
- **cmd** — command runner; RTK-compressed LLM-facing stdout, full output to files.
  RTK filter map extended: `flutter test` → `rtk test`, `flutter analyze` → `rtk err`,
  git diff → `rtk diff`, JSON → `rtk json`.
- **token-kill** — NEW script. RTK-based minification: error-log minification,
  comment/whitespace stripping from source fed to operador/revisor, report trimming.

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
- **RTK = Token Killer:** every command an LLM could see runs through `cmd`/`token-kill`;
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
- Operational tier model: `opencode-go/deepseek-v4-flash` (C). Strategic tier:
  `opencode-go/muse-spark-1.3-contributor` (D and B-side judgment). The README-LLM variant
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