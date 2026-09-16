# ADR-0015: Integrate the wave in one batch, bisect only on red

- **Status:** Accepted
- **Date:** 2026-09-16
- **Related:** ADR-0012 (script-owned integration gate), ADR-0013 (integrate suite skip)

## Context

ADR-0012 made `integrate` fold a wave in one task at a time, running the FULL
gate after **every** merge, so a partially-approved wave could never leave the
integration tree red. That per-merge gate is the wave path's dominant serial
cost: it runs after `wait`, with every worker idle, and a wave of N pays N full
suites to catch a cross-task coupling that is usually not there.

ADR-0013 removed the redundancy only for a merge that is provably
tree-equivalent to an already-gated commit - the first task of a wave. Later
merges still gate, because their merged tree genuinely combines untouched-and-
gated content.

The per-merge loop is valuable as a **fallback** (it isolates the culprit
without poisoning the wave), but it should not be the default path.

## Decision

For a wave of **≥2** approved tasks, `integrate`:

1. merges every task branch in ascending id order (`git merge --no-ff`, one
   merge commit each), recording each merge sha;
2. runs the Flutter/generic gate **once** on the combined tree - without the C2
   scope check, which a single keep-discard pass cannot apply to a multi-task
   `touches` set (each task's `coder-gate` already proved its own scope in its
   worktree);
3. on green: ledgers `integrated` for each task with its merge sha, folds each
   shard, releases each worktree;
4. on a conflict or a red gate: `git reset --hard` the pre-batch commit and runs
   the existing per-merge loop - which **is** the bisect (merge one, gate,
   `integration_failed` + `git merge --abort` on the failure, keep going).

A wave of **one** approved task keeps the per-merge path directly, so it still
carries the ADR-0013 provably-equivalent skip.

`final-gate`'s `tree_unchanged_since_green` now accepts the newest `commit`
**or** `integrated` ledger sha: after a wave, HEAD is a merge commit, so
comparing against a task-branch `commit` sha could never match and the closing
re-run was never skipped.

## Consequences

- The common (uncoupled) wave runs the suite once instead of N times.
- The "never leave the tree red" invariant is preserved: a red batch is reset
  before anything is recorded, and the fallback integrates each task
  individually exactly as before.
- A failing batch no longer aborts the wave: the bisect still lands the good
  tasks. The only extra cost is one wasted batched suite plus a reset when the
  batch is red - bounded and rare.
- The batch merges are real merge commits created before the gate; a red batch
  discards them with `git reset --hard`, so no partial integration is ever
  ledgered.
- `final-gate`'s closing suite is now actually skipped after a wave, removing a
  second redundant run.

## Alternatives considered

- **Keep gating after every merge (status quo):** rejected - it pays N suites
  for a coupling that is the exception, and the serial tail is pure idle.
- **Run the suite once per wave but never bisect:** rejected - a red wave would
  be unattributable and would block every task in it, violating ADR-0012's
  "a bad task can never poison the wave".
- **Gate the batch and, on red, attribute the failure by re-running the gate per
  task from scratch (no merge commits up front):** rejected - the up-front
  merges are what make the happy path cheap; the reset-and-bisect fallback
  reaches the same end state without paying two full passes in the common case.
