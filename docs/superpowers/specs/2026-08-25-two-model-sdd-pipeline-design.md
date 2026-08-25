# Superpowers Pipeline — Hybrid Orchestrated Architecture

Custom fork of `superpowers:subagent-driven-development`. A deterministic
orchestrator script owns state and dispatch; every LLM call is an isolated,
stateless invocation fed exactly the context it needs. No agent holds a
continuous session across the branch.

## 0. Pre-Pipeline Gate

Before `brainstorming` starts, ask the user:

1. Whether this branch should use this pipeline at all.
2. Which model is the expensive/Strategic tier and which is the
   cheap/Operational tier (same API, different model selection).

If declined, fall back to native `subagent-driven-development` behavior.

## 1. Core Principles

- **Hybrid orchestration:** a deterministic script (the Orchestrator) manages
  state, git worktrees, task transitions, test execution, and retry-loop
  tracking. LLMs are invoked strictly for isolated reasoning, never for
  bookkeeping.
- **Stateless LLM calls:** no role is a persistent chat session. Every
  dispatch — Controller, Coder, Reviewer — is a fresh, isolated call fed
  curated context (a task brief, a diff, a ledger excerpt), not an
  accumulating conversation. This is what prevents both context exhaustion
  and context-pollution-driven review bias.
- **Git + plan + ledger as source of truth:** continuity across tasks comes
  from the JSON plan, the git history, and a script-maintained ledger — not
  from any LLM's memory.

## 2. Roles

### Orchestrator (deterministic script, no LLM)

- Manages git worktrees and branch state.
- Iterates the task plan, dispatching each role with curated context.
- Runs the test suite (per-task and full-suite) and static analysis
  (`flutter analyze`), and reports pass/fail back to whichever role needs it.
- Tracks retry-loop state and triggers escalation after 2 failed rounds.
- Performs commits and the final merge.
- Appends structured decisions (review outcomes, escalation events,
  interface changes) to the ledger — the ledger is written by the script
  from structured LLM output, not maintained by an LLM as an ongoing job.

### Controller (Strategic/expensive LLM, stateless per dispatch)

- Brainstorming (initial).
- Plan writing (initial).
- RED test generation, folded into each task's brief and produced
  just-in-time — immediately before that task is dispatched, not batched
  upfront for the whole plan. This avoids tests going stale against
  interface changes made by earlier tasks.
- Final branch review and consolidation (see §5).
- Arbitration if the Orchestrator detects a deadlock.

### Coder (Operational/cheap LLM, per task, stateless)

- Implements code to satisfy the RED test.
- Up to 2 rounds per task.
- On success: hands the result to the Orchestrator for the standard
  wrap-up (test run, analysis, commit) and report generation.
- On failure after 2 rounds: this is the escalation trigger. No task needs
  to be pre-classified as complex — the process reveals it organically.
- Never writes or edits tests.

### Strategic Coder (Strategic/expensive LLM, spawned on demand)

- Invoked only when a task escalates.
- Receives the current diff and the list of failing tests.
- Explicitly decides whether to keep or discard the Coder's partial work —
  never automatic in either direction.
- Implements the failing tests directly.

### Code Reviewer (Strategic/expensive LLM, ephemeral, fresh per task)

- Spawned fresh for every task review, strict read-only mode.
- Context is built by the Orchestrator: the task diff plus affected
  interface dependencies — never raw conversation history, never
  accumulated context from other tasks.
- Reviews every task's diff uniformly, including escalated ones. Because
  the Reviewer is never the same dispatch as whoever implemented the code
  (Coder or Strategic Coder), this structurally prevents the reviewer from
  grading its own work — no special-casing needed for escalated tasks.
- Decides: approve, send back for fixes, or escalate further.

## 3. Pipeline Flow

1. Controller generates the plan (JSON list of tasks).
2. Orchestrator iterates the plan. For each task:
   a. Controller generates the task brief, including the RED test,
      just-in-time.
   b. Coder attempts implementation (up to 2 rounds).
   c. On success, Orchestrator runs tests/analysis and dispatches Code
      Reviewer with curated diff + interface context.
   d. On failure after 2 rounds, Orchestrator dispatches Strategic Coder
      with the diff and failing tests; Strategic Coder implements; Code
      Reviewer reviews it the same way as any other task.
3. Orchestrator records the outcome (approved / sent back / escalated) in
   the ledger and moves to the next task.
4. After all tasks: final branch review (§5), then merge.

## 4. Escalation Handling

- Trigger: 2 failed rounds by the Coder on a given task.
- Strategic Coder receives the diff + failing tests, decides explicitly
  whether to build on the partial work or discard it, then implements.
- The resulting code goes through the same Code Reviewer role as any other
  task — no separate self-review step is needed, since implementer and
  reviewer are already architecturally distinct roles in this pipeline.

## 5. Final Branch Review (`finishing-a-development-branch`)

| Part | Owner | Needs accumulated context? |
|---|---|---|
| Merge | Orchestrator | No — deterministic |
| Full test suite revalidation | Orchestrator | No — execution, not judgment |
| Holistic final review | Controller (stateless dispatch) | Yes, but curated, not raw |

- Orchestrator generates the whole-branch diff (`merge-base..head`), same
  pattern as native `review-package`.
- Controller receives that diff plus the ledger (the accumulated record of
  decisions, escalations, and rejection reasons from every task) — two
  curated artifacts, not the branch's conversation history.
- If the final review finds issues: treat as escalation at task scope —
  Controller dispatches a targeted fix, or reopens the plan if the issue is
  structural. No need to reprocess the whole branch, only the part the diff
  flags.

## 6. Context & Cost Optimization Rules

- No LLM role ever holds a continuous session across tasks or across the
  branch — every dispatch is stateless and fed only what that call needs.
- The ledger, not agent memory, carries continuity: it is written by the
  Orchestrator from structured outputs, and read by any role that needs
  prior-decision context (e.g., the Controller's final review).
- RED tests are generated just-in-time, per task, never batched in advance.
- The Code Reviewer's context is script-curated (diff + affected
  interfaces) specifically to avoid both under-informed review and
  attention dilution from unrelated accumulated history.

## 7. Brainstorming Enrichment (`grill-with-docs` merge)

The native `brainstorming` skill keeps everything in conversation until the
final design doc is written — no incremental persistence, no formal gate
distinguishing a trivial exchange from a decision worth keeping permanently.
This merges in `grill-with-docs`'s incremental-persistence pattern without
replacing brainstorming's flow.

- As soon as a term, decision, or constraint resolves during the dialogue —
  at any step, not only at the end — it is written immediately to
  `CONTEXT.md` (glossary), not batched into the final spec.
- A resolved decision becomes an ADR only when it passes all three of
  `grill-with-docs`'s gates simultaneously. Most sessions still produce zero
  ADRs — this is expected, not a failure of the process.
- Fact-finding clarifying questions (e.g., objective, constraints only the
  developer knows) stay fully open-ended, exactly as in native
  brainstorming — no preset options, to avoid anchoring the developer to
  the assistant's own assumptions.
- Design-choice steps (proposing approaches, the existing "2-3 options"
  moment) present exactly 3 suggestions plus a free-form custom-answer
  option — formalizing what brainstorming already does informally at that
  step only.
- Scope stays separated so the two artifacts don't duplicate: `CONTEXT.md`
  and ADRs hold vocabulary/decisions that persist beyond this branch
  (project-level); the brainstorming spec doc holds the design specific to
  this feature/branch.

## 8. Language Policy

- All artifacts and all assistant responses are produced in English by
  default — task briefs, RED tests, design docs, `CONTEXT.md`, ADRs, ledger
  entries, review reports — regardless of the developer's own language.
- Exception: the software's UI (user-facing strings, labels, copy) defaults
  to the developer's language, not English.
- Rationale: English-only context artifacts measurably reduce token count
  per artifact, which matters directly for the pipeline's cost/time
  efficiency goal (§0, §6).
