# ADR-0017: An approved no-op task integrates and releases

- **Status:** Accepted
- **Date:** 2026-09-16
- **Related:** ADR-0011 (worktree per task), ADR-0012 (script-owned integration gate)

## Context

`worktree-release` requires the task branch's tip to differ from the allocation
base recorded by `worktree-alloc`; `integrate` merges the branch and commits the
merge. Both assume the task committed something.

A task can be approved with **zero commits**: `green-gate` exits 0 with "nothing
to commit" (there was nothing to change), the revisor still runs and approves,
and the shard holds `task_complete`. Then:

- `integrate` merges a branch whose tip equals HEAD, runs the gate, and
  `git commit` fails with "nothing to commit" → `integration_failed commit`;
- the worktree is never released (release refuses on `tip == base`);
- `final-gate` check 7 then blocks the branch on the leftover `task/<N>` branch.

So a legitimate, reviewed no-op strands the wave and blocks closing.

## Decision

- **`integrate`** classifies an approved task whose branch tip equals its
  `worktree_alloc` base as a **no-op**: it ledgers `integrated N "no-op (no
  commits)"`, folds the shard and releases the worktree, without merging,
  gating, or committing anything (there is nothing new to verify).
- **`worktree-release`** keeps its "never release a never-worked branch" guard,
  but the guard now consults the task's shard: a branch whose tip equals its base
  is released only when the shard holds `task_complete`, proving the no-op was
  reviewed. An unapproved never-worked branch is still kept as the only debug
  copy.

## Consequences

- A reviewed no-op task closes cleanly instead of blocking the wave and the
  closing gate.
- The `tip == base` release is no longer a blind hole: it is gated on the
  approval evidence, the same signal `integrate` uses everywhere else.
- `final-gate`'s leftover-branch blocker keeps its meaning - a leftover branch
  now always means a genuinely unresolved task.

## Alternatives considered

- **Drop the `tip != base` guard outright:** rejected - it would release a
  never-worked, unapproved branch and destroy the only debug copy.
- **Refuse to let a no-op task be approved (fail the gate on "nothing to
  commit"):** rejected - "the acceptance is already satisfied, nothing to
  change" is a legitimate outcome, and failing it would send the operador into a
  fix loop with nothing to fix.
- **Have `final-gate` ignore leftover branches:** rejected - it would mask
  genuinely unintegrated tasks.
