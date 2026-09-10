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
  opened. Owns brainstorming, the plan shell + spec, then DONE. Never in the
  per-task loop.
- **Agente diretor** — Strategic tier (`two-model-task-generator`). Expands the
  plan shell into full tasks (acceptance + expected_red), appends corrective
  tasks, performs branch closing. Dispatched once per branch; resumed only on
  demand; task text in, never diffs/logs.
- **Agente operador** — Operational tier (`opencode-go/deepseek-v4-flash`). Write-only executor:
  receives the scaffolded brief, authors RED tests, writes implementation code. Never runs tests or
  analysis — Script CEO decides task-tests / full-suite / analyze passes. Context is
  zeroed per task; retries resume the same session within a task.
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
  (statement, acceptance, EXPECTED-RED, RED order). No LLM call.
- **red-gate** — verifies the scaffolded brief exists. On success, Script CEO
  dispatches Agente operador directly (item 4), then chains coder-gate.
  No main-agent intermediation.
- **green-gate** — chains full suite + `flutter analyze` + format check + commit.
  The test/analyze pass/fail decisions are made inside the script (item 2). On
  success (after the RED-proof), Script CEO commits, then dispatches Agente
  revisor directly (item 3).
- **coder-gate** — unbounded retries until green; RED-proof (stash touches,
  new tests must fail with expected_red, restore, snapshot); red-integrity
  pre-commit. Only TEST_DEFECT leaves the loop.
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
  Agente diretor persists across the branch on task text only.
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
- C is write-only; test/analyze decisions live inside the script — confirmed.
- Loop: unbounded retries until green, no failure counting — confirmed.
- Operational tier model: `opencode-go/deepseek-v4-flash` (C). Strategic tier:
  `opencode-go/muse-spark-1.3-contributor` (D and B-side judgment). The README-LLM variant
  table is stale and will be corrected (no `variants` block exists in opencode.jsonc).
- Final review via `/new` + clean context — confirmed.
- Subagent headers: fixed templates + deterministically-resolved per-task values.