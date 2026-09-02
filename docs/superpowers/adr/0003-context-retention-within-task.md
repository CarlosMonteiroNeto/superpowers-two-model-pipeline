# ADR-0003: C and D retain context within a task until D approves

- **Status:** Accepted
- **Date:** 2026-09-02

## Context

The current pipeline dispatches the Coder fresh per round and the Reviewer fresh
per task (anti-bias: "a reused Reviewer grades with stale attention"). The
developer wants the opposite for within-task loops: C and D keep their context
until the task is approved by D, so fix/correction loops resume the same session
and the review of a correction reuses the reviewer's prior findings. Context is
still zeroed per task.

## Decision

Within a task: C round 1 creates a session; rounds 2+ and fix rounds resume it
via `dispatch --continue --session <id>`. D's first dispatch creates a session;
SEND_BACK correction loops resume the same D session with the corrective brief +
new diff appended. At `APPROVED`, both sessions are closed and the next task
starts fresh dispatches. Minor findings do not trigger fix loops — B documents
them (PARKED ledger entries).

## Consequences

- Review bias risk changes shape: D now re-reviews its own prior findings in a
  corrective loop. Mitigation: each D resume is fed the new diff + the previous
  verdict explicitly; the final verdict on a corrected task is still a fresh
  judgment call recorded in the ledger.
- Provider cache reuse improves (stable prefix + appended deltas per session).
- The README-LLM "fresh reviewer every task" invariant is superseded for
  within-task correction loops.

## Alternatives considered

- **Fresh D per correction round (current):** rejected — forces D to re-derive
  findings each loop and multiplies strategic-tier token spend.
- **Fresh C per round (current):** rejected — loses the coder's working context
  and duplicates brief re-reading.