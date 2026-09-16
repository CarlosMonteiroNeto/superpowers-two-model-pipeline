# ADR-0013: `integrate` skips the post-merge suite when the merge is tree-equivalent

- **Status:** Accepted
- **Date:** 2026-09-15

## Context

Parallel waves integrate one task branch at a time (`git merge --no-commit
--no-ff task/<N>`) and run the FULL gate after **every** merge, so a
partially-approved wave can never leave the integration tree broken
(ADR-0012). That per-merge suite is the wave mode's dominant cost: a single
Flutter task pays the suite three times — once in the operador's own RED/GREEN
loop, once in `coder-gate`'s authoritative `green-gate`, and once again in
`integrate`.

For a wave whose first task was allocated from the current integration HEAD,
the merge cannot change the tree: `HEAD` is an ancestor of `task/<N>`, so the
`--no-ff` merge produces exactly the tree of `task/<N>`'s tip commit — the very
content `green-gate` already validated before committing it. Re-running the
suite there verifies bytes that have already been verified.

## Decision

`green-gate` records the tree hash it validated on the ledger `commit` entry
(`tree=<git rev-parse HEAD^{tree}>`). `integrate`, before merging, computes an
eligibility flag; after merging, it skips the gate when the flag holds and
ledgers the skip (never silently):

```
gated_tree = last `commit` entry's tree= in the task's shard
task_tree  = git rev-parse task/<N>^{tree}
eligible   = gated_tree == task_tree            (the recorded proof matches)
          && git status --porcelain is empty     (nothing else staged)
          && git merge-base --is-ancestor HEAD task/<N>   (HEAD is the base)
```

On `eligible`, `integrate` skips `green-gate`/`run-gates`, appends
`integrate_suite_skipped N "ff-equivalent tree=<sha>"`, and proceeds to commit,
ledger-merge and worktree-release. Any condition failing falls back to running
the gate — the safe default. Non-Flutter tasks record no `tree=`, so they never
skip.

## Consequences

- The first task of every wave skips its post-merge suite (~10-14 min of a
  Flutter full suite per skipped merge). In a wave of N tasks, later tasks
  still run it: once earlier merges advance HEAD, `HEAD` is no longer an
  ancestor of their branches, so their merges genuinely combine trees.
- The number of full-suite runs per task drops toward the trust model's
  minimum: `coder-gate`'s authoritative run, plus the operador's own loop.
- The skip is provable, not heuristic: two independent conditions (the recorded
  validated tree hash AND ancestry) plus a clean-tree check. A skip can never
  apply to a tree that differs from what was gated.
- The failure mode is bounded: a wrongly-skipped suite would leave a red tree
  that the next task's gate, or `final-gate`, catches.
- `integrate_suite_skipped` is a first-class ledger entry, so the optimization
  is auditable and testable, never invisible.

## Alternatives considered

- **Always run the suite after every merge** (status quo): rejected — it
  re-verifies provably-identical content, and the wave mode's cost was the
  observed complaint.
- **Run the suite once per wave instead of once per merge:** rejected — it
  makes a failure unattributable to a single task and weakens the
  "green after every merge" invariant ADR-0012 established.
- **Trust the operador's or `coder-gate`'s word that the tree is unchanged**
  (no recorded hash, ancestor check only): rejected — the recorded `tree=` is
  the evidence; `git merge-base --is-ancestor` alone is a reasoning step, not a
  proof of content identity.
