# ADR-0004: Graphify — update before commit, subgraph read immediately after, for B and D

- **Status:** Amended (supersedes the original "post-commit update only" decision)
- **Date:** 2026-09-02 (amended 2026-09-05)

## Context

Graphify was made Controller-side and lazy in a prior change (query at brief
time, rebuild only when stale). The developer's architecture re-ties the graph
to the deterministic layer with two rules: (1) the graph is updated only at the
moment it is about to be read — never per Coder iteration (that would be
wasted overhead), and never orphaned (updated but unread); (2) when B is
called for the next brief (and when D reviews), Script A extracts only the
affected-dependency subgraph — interfaces, models, and callers of the module —
and sends that slice instead of whole source files.

## Decision (amended 2026-09-05)

- `graphify-update` runs as part of the green-gate / coder-gate chain,
  **immediately before the task's commit**, so the regenerated graph artifacts
  (graphify-out/) enter the task's own commit. It is never per Coder iteration.
- `graphify-subgraph <ws> TASK` runs **immediately after** `graphify-update`
  (still before the commit) and queries the graph (`explain` / `path`) for the
  task's `touches`/`depends_on` modules, writing `<ws>/task-N-interfaces.md`
  (capped, ~100 lines). This file replaces the main agent's manual interface
  gathering for both B's next brief and D's review; `review-package` inlines it
  into the review package D receives.
- The graph exposes structure, not method bodies; the subgraph is the only code
  context sent to B per task.
- Both graph steps are best-effort: a missing graphify binary never blocks the
  gate (the gate's verdict stays the test/analyze exit code).

### What changed from the original decision

The original ADR said `graphify-update` runs only **after** a task is approved
and committed, and that "the graph can lag uncommitted work by design". The
developer's later feedback (2026-09-05) required the graph to **enter the
commit** it describes and to be **read immediately after being written** — an
update that is never read is orphaned work. The ordering is therefore inverted:
update → read → commit. The commit still happens before review (the full
commit-after-approval inversion was considered and rejected as too costly for
the benefit).

## Consequences

- B's per-task prompt input shrinks to the affected slice — direct token savings
  on the strategic tier.
- `graphify-subgraph` becomes the single deterministic replacement for the one
  LLM-composed header slice (interfaces) identified in the header analysis.
- The graph is never orphaned: every `graphify-update` in the gate chain is
  immediately followed by the `graphify-subgraph` read that consumes it.
- Because the graph is updated before the commit, the regenerated artifacts are
  part of the task's own commit — D's review and the next brief both read the
  freshest graph.

## Alternatives considered

- **Update per Coder iteration:** rejected by the developer — unnecessary
  overhead; the graph is consumed at brief time and review time, not mid-edit.
- **Post-commit update only (original ADR):** rejected by the developer's
  2026-09-05 feedback — the graph lagged uncommitted work and was never read in
  the scripted flow; the write was orphaned.
- **Commit after reviewer approval (full inversion):** considered and rejected —
  the cost (working-tree diffs, a post-approval commit step, red-integrity
  rework) outweighed the benefit; commit-before-review is kept.
- **Keep the main agent gathering interfaces (current):** rejected — it is the
  only non-deterministic slice in subagent headers and defeats the script-driven
  dispatch design.