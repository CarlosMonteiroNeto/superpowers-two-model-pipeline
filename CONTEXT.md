# CONTEXT.md — Glossary (two-model pipeline)

Resolved terms and decisions that persist beyond any single branch. Branch-specific
design lives in the spec; this file holds the vocabulary and binding constraints the
pipeline runs on. Updated as terms resolve during brainstorming (Incremental
Persistence — architectural path only).

## Roles and actors

- **Script A (Orchestrator)** — the deterministic, modular bash layer that owns the
  per-task flow: gates, test/analyze decisions, subagent dispatch, routing, commits,
  and graph maintenance. A thin driver script (`orchestrator`) plus specialized
  sub-scripts (red-gate, green-gate, dispatch, cmd, token-kill, graphify-update,
  graphify-subgraph, route-next, review-package, ledger-append). Script A is never an
  LLM; its verdicts are exit codes and its outputs are files.
- **B (Strategist / main session)** — the interactive OpenCode session the developer
  opened. Owns brainstorming, the JSON plan, task breakdown, per-task briefs + RED
  tests, corrective briefs, TEST_DEFECT arbitration, and the final holistic review.
  Receives feedback only through Script A's outputs (stdout, ledger, gate reports);
  its context is preserved across tasks.
- **C (Coder)** — Operational tier (`opencode-go/mimo-v2.5`). Write-only executor:
  receives the brief + RED tests, writes implementation code. Never runs tests or
  analysis — Script A decides task-tests / full-suite / analyze passes. Context is
  zeroed per task; fix rounds resume the same session within a task.
- **D (Code Reviewer)** — Strategic tier (`opencode-go/deepseek-v4-flash`). Reviews
  only compiler-approved code (tests + syntax already green). Evaluates design,
  architecture, spec compliance, and interface discipline. Returns a structured JSON
  verdict (APPROVED / SEND_BACK / ESCALATE + findings + minors). Context kept during
  the task's correction loops; zeroed after the task is approved.
- **Strategic Coder** — REMOVED. Escalation no longer dispatches a strategic coder;
  the Coder's overflow escalates to B for brief/test viability arbitration.

## Deterministic gates and flows

- **red-gate** — verifies the brief's RED tests fail for the expected reason
  (`EXPECTED-RED:` substring in the report). On success, Script A dispatches C
  directly (item 4). No main-agent intermediation.
- **green-gate** — chains full suite + `flutter analyze` + format check + commit.
  The test/analyze pass/fail decisions are made inside the script (item 2). On
  success, Script A updates the graph + reads the subgraph BEFORE the commit
  (so the graph enters the task's own commit and is read immediately after
  being written), then dispatches D directly (item 3).
- **route-next** — deterministic router; Script A executes its emitted action.
  Actions: BRIEF / RED / CODER N ROUND / REVIEW / FIX / CORRECTIVE / ARBITRATE /
  NEXT / FINAL_REVIEW. `STRATEGIC` action removed (Strategic Coder removed).
- **dispatch** — NEW script. Headless subagent launcher: `opencode run --agent
  <coder|reviewer> --dir <worktree> --file <brief> --format json --prompt <filled>`.
  Fix/correction rounds append `--continue --session <id>`. Full JSON event stream
  teed to `<ws>/task-N-coder.log` / `<ws>/task-N-reviewer.log` for observability.
- **cmd** — command runner; RTK-compressed LLM-facing stdout, full output to files.
  RTK filter map extended: `flutter test` → `rtk test`, `flutter analyze` → `rtk err`,
  git diff → `rtk diff`, JSON → `rtk json`.
- **token-kill** — NEW script. RTK-based minification: error-log minification,
  comment/whitespace stripping from source fed to C/D, report trimming.
- **graphify-update** — NEW script. Rebuilds the project graph just before the
  task's commit (green-gate / coder-gate chain), so the regenerated graph enters
  the task's own commit; never per C iteration. The `graphify-subgraph` read
  runs immediately after.
- **graphify-subgraph** — NEW script. Queries the graph (`explain` / `path`) for the
  task's `touches`/`depends_on` modules and writes `<ws>/task-N-interfaces.md` — the
  affected-dependency slice fed to B's next brief and D's review. Replaces the main
  agent's manual interface gathering.

## Context and cost rules

- **Context retention:** C and D keep their sessions until D approves the task
  (within-task fix/correction loops resume the same session). Both are zeroed at
  task approval; fresh dispatch per task.
- **B's context:** preserved across the branch; final holistic review runs in a fresh
  `/new` session fed only the original plan + consolidated diff + ledger.
- **Observability:** the developer watches C/D progress via workspace log files
  (teed by `dispatch`); headless subagent sessions never pollute the main session's
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
- Loop budget: round 1 + 3 fixes (4 total Coder attempts) — confirmed.
- Operational tier model: `opencode-go/mimo-v2.5` (C). Strategic tier:
  `opencode-go/deepseek-v4-flash` (D and B-side judgment). The README-LLM variant
  table is stale and will be corrected (no `variants` block exists in opencode.jsonc).
- Final review via `/new` + clean context — confirmed.
- Subagent headers: fixed templates + deterministically-resolved per-task values;
  the only LLM-composed slice (interfaces file) becomes graphify-subgraph output.