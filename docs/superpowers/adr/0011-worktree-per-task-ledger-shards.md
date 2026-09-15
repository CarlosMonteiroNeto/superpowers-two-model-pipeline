# ADR-0011: Worktree-per-task isolation with per-worktree ledger shards

- **Status:** Accepted
- **Date:** 2026-09-15
- **Related:** ADR-0010 (plan-derived wave scheduling), ADR-0012 (script-owned
  integration gate)

## Context

Parallel tasks need isolated working copies and isolated ledger writes. Two
facts shape the answer:

- `pipeline-workspace` resolves its directory from `git rev-parse
  --show-toplevel`, so a git linked worktree already gets its own
  `.superpowers/two-model/<slug>/` workspace — isolation falls out of the
  existing design.
- The ledger is a plain append-only file. Two concurrent unlocked `>>` appends
  interleave and corrupt lines, and `ledger-append` is a read-then-write, not an
  atomic cross-process operation. A lock primitive is not portable in git-bash
  on Windows, the pipeline's primary platform.

Gates for recording a decision (all three): reversal cost — high; reach —
project-level; a rejected alternative exists.

## Decision

- One git worktree **plus** branch `task/<N>` per dispatched task, allocated by
  `worktree-alloc` from the integration HEAD and stored under the already
  gitignored `.superpowers/two-model/worktrees/`.
- Each worktree seeds its own workspace: a copy of `plan.json` and a fresh
  `ledger.jsonl` carrying **only** the branch `gate` entry copied from the
  integration ledger.
- A task's ledger writes land in its own worktree shard. On integration,
  `ledger-merge` folds the shard into the integration ledger by re-emitting
  every entry **through `ledger-append`** (the sole writer), so escaping and the
  partition mirror stay in one place; it skips `gate` entries and
  content-identical duplicates (identity = the entry minus `ts`, idempotent
  re-runs) and rebuilds partitions via `ledger-migrate`.
- `worktree-release` removes the worktree and the branch **only** after the
  branch tip is proven merged into the integration HEAD (and differs from its
  allocation base); it never removes on failure.

## Consequences

- No lock primitive is required: shards are implied by the existing workspace
  resolution and are portable on Windows/git-bash.
- The ledger stays single-writer per file (`ledger-append`), preserving one
  escaping path and one partition mirror.
- Isolation implies a merge step and a shard-merge step; both must be
  script-owned and idempotent (ADR-0012).
- The worktree lifecycle must be tracked (`worktree_alloc`/`worktree_release`)
  so `final-gate` can detect a wave still in flight.
- Each worktree carries its own `--continue --session` context within a task
  (ADR-0003), one interpreter, untouched.

## Alternatives rejected

- **`flock` on one shared ledger**: rejected — no portable locking in git-bash
  on Windows; a held lock stalls the whole wave, a crashed holder is
  unrecoverable, and a lock primitive must be carried for every append. Shards
  are simpler and already fall out of `git rev-parse --show-toplevel`.
- **Two unlocked `>>` appends to the shared ledger**: rejected — interleaved,
  corrupted JSONL lines; `ledger-append`'s read + write is not atomic across
  processes.
- **Copy the whole workspace into each worktree**: rejected — the workspace
  directory is per-toplevel by construction; copying forks plan/ledger state and
  defeats idempotent re-derivation.
- **Auto-remove the worktree on failure**: rejected — destroys the only copy of
  the debug state and the lost shard; parity with `session-clean` and the
  non-destructive default.
