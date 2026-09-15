# ADR-0012: Integration is a script-owned serial merge gate

- **Status:** Accepted
- **Date:** 2026-09-15
- **Related:** ADR-0010 (plan-derived wave scheduling), ADR-0011
  (worktree-per-task isolation)

## Context

With waves (ADR-0010) and worktree-per-task isolation (ADR-0011), every wave
must fold its task branches back into the integration branch. Letting each agent
merge its own work, or the driver merge on its own judgment, reintroduces LLM
judgment and non-deterministic ordering. A single "merge the wave at the end"
step cannot attribute a red suite to a task, and a red integration branch — even
briefly — poisons every subsequent task and forces a global re-run.

Gates for recording a decision (all three): reversal cost — high; reach —
project-level; a rejected alternative exists.

## Decision

- `integrate` is the integrator. For each task in **ascending id order** it
  `git merge --no-commit --no-ff task/<N>`, runs the **full gate after each
  individual merge** (`green-gate --no-commit` for `lang=flutter`, else
  `run-gates`), and `git commit --no-edit` on green; on conflict, red gate, or
  commit failure it `git merge --abort`s that task and ledgers
  `integration_failed`, then continues with the remaining tasks.
- No agent merges its own work. Workers never commit; the gate chain commits
  inside a worktree, and only the integrator commits to the integration branch.
- After the code outcome for a task is known, `ledger-merge` folds that task's
  shard into the integration ledger and `worktree-release` removes the
  worktree/branch.
- Integration-failure recovery is **bounded**: the driver makes exactly **one**
  re-attempt per failed task in its existing worktree (running it alone), then
  **blocks** with an actionable message. It never self-heals in a loop; a true
  in-place corrective (re-opening a task that already has `task_complete`) is
  deferred.

## Consequences

- A break is localized to the task that caused it, and the integration branch is
  never left red — the "each wave leaves the tree green" contract holds.
- Integration is serial and runs one full suite per merged task; slower than a
  single wave-end run, but deterministic and diagnosable.
- The integrator is the only new committer; the existing gates and agent roles
  are untouched.
- `final-gate` gains blockers for a pending worktree, a leftover `task/<N>`
  branch, and a newest `integration_failed` without a later completion.

## Alternatives rejected

- **Merge at wave end** (one merge + one suite for the whole wave): rejected —
  cannot attribute a red suite to a task; one bad task forces the whole wave to
  re-run.
- **Agent-driven merge** (the task's agent merges its own branch): rejected —
  violates "workers never commit" and "scripts decide", and orders merges by LLM
  judgment.
- **Commit-and-fix-forward** (leave the integration branch red and repair
  later): rejected — poisons every subsequent task and destroys per-wave
  greenness.
- **Unbounded integration-failure self-heal**: rejected — unbounded token spend
  behind a silent loop; a human blocker beats a runaway spend.
