# ADR-0001: Script-autonomous subagent dispatch (B out of the per-task hot path)

- **Status:** Accepted
- **Date:** 2026-09-02

## Context

The pipeline's per-task loop today is driven by the main agent (the Orchestrator
session): it runs the gates, then dispatches the Coder and Reviewer through the
`task` tool, reads route-next, and loops. The developer wants the deterministic
layer (Script A) to own dispatch end to end — red-gate dispatches C, green-gate
dispatches D, route-next passes between tasks — so the interactive session is out
of the hot path and receives feedback only through script outputs.

## Decision

Script A dispatches C and D headlessly via a new `dispatch` script wrapping
`opencode run --agent <two-model-coder|two-model-reviewer> --dir <worktree>
--file <brief> --format json --prompt <filled-template>`. Fix/correction rounds
append `--continue --session <id>` to resume the same session. B (the main
session) writes briefs, reads script stdout/ledger/gate reports, and is never a
link in the dispatch chain. The `STRATEGIC` route-next action and the Strategic
Coder role are removed; escalation becomes `ARBITRATE` to B.

## Consequences

- Main-session context stays clean: only script stdout and curated files enter it.
- C/D progress is observable via teed workspace logs (`task-N-coder.log`,
  `task-N-reviewer.log`) without polluting session history.
- Headless `opencode run --agent` for subagent-mode agents is unverified in the
  docs — an implementation spike must confirm it (and `--continue --session`
  resume semantics) before the rest is built.
- `--auto` vs explicit agent permissions must be decided per agent definition.

## Alternatives considered

- **B executes every dispatch** (script decides, session launches): rejected —
  keeps the session in the hot path, contradicting the developer's items 3/4/7.
- **Persistent `opencode serve` daemon + `--attach`:** rejected for now — more
  moving parts (daemon lifecycle); revisit as a speed upgrade if cold boots hurt.