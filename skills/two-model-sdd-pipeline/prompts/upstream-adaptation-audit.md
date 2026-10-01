# Upstream adaptation audit

Date: 2026-10-01. Plan: Agent Instructions and Autonomy, Task 1.
Reference: `upstream-lock.json` (revision `b36e0829c6d0140e93cfef2ca599b1b07d4a7797`,
tag `v6.3.0`, network policy `offline`).

## Provenance verification

The pinned upstream object `b36e0829c6d0140e93cfef2ca599b1b07d4a7797` is
absent from this repository (`git cat-file -t` fails) and the lock
declares an offline network policy, so source bytes were NOT re-verified
against upstream in this checkout. Recorded discrepancy: provenance
claims rest on the lock file alone until an online verification runs.
No source was substituted: adaptation records cite the exact recorded
revision, and no local skill file was presented as upstream.

## Manual fidelity comparison

Each `adaptation-map.json` record was compared against the destination
section named in its `destination` field:

- Operator `Test and implementation loop`: retains Iron Law, Red-Green-Refactor
  (observed RED, minimal GREEN), Name-the-Break and Exercise-the-Real-Thing;
  replaces Common Rationalizations with direct rules. Investigate-first,
  root-cause debugging, narrow reproduction, working-path comparison, and
  evidence-backed test correction live in `Investigation and debugging`.
- Operator `Verification boundaries`, `Self-review and evidence`:
  verification Iron Law retained; self-review covers diff inspection and
  honest reporting.
- Operator `Pipeline authority`: Task Loop and Finish replaced by Script CEO
  ownership; implementer template retained with bounded scope and
  dispatch-budget retries (unbounded-retry language removed from
  `coder-prompt.md`).
- Reviewer `Independent review`: reviewer template, code-reviewer Issues, and
  Gate Function retained; How-to-Request and Response Pattern replaced by
  package-based script routing.
- Reviewer `Read-only authority`: unchanged; workers never approve RED,
  commit, or dispatch.
- Director `Bounded escalation judgment`: Phase 1 retained for
  evidence-based escalation judgment; Phase 4 replaced (proposal only);
  scoped re-review retained.
- Shared `Pipeline authority`: Skill Priority replaced; workers receive the
  approved role package instead of reselecting skills.

## Omissions with reasons

- Upstream orchestration freedoms (recursive brainstorming, worker-side agent
  selection, interactive approval, worker commits/publication) are omitted
  everywhere: scripts own control state.
- Worker web research stays restricted per existing policy: prompts do not
  grant it.
- `coder-gate` retry behavior is still unbounded in code; the instruction
  now cites the dispatch budget as authority. Budget enforcement is Task 5
  scope (`dispatch_budget.py` default `[5, 3, 3]`); existing
  `test_coder_gate.py` expectations were left untouched.

## Structural check

`test_prompt_adaptation_contract.py` enforces the map shape (source
identity fields plus non-empty `destination`) and the template contract
(investigation/debugging markers, no unbounded-retry promises) on every
run, so future edits cannot silently drop provenance or reintroduce the
removed language.
