# ADR-0004: Graphify — post-commit update only, subgraph extraction for B and D

- **Status:** Accepted
- **Date:** 2026-09-02

## Context

Graphify was made Controller-side and lazy in a prior change (query at brief
time, rebuild only when stale). The developer's architecture re-ties the graph
to the deterministic layer with two rules: (1) the graph is updated only after an
approved task's commit — never per Coder iteration (that would be wasted
overhead); (2) when B is called for the next brief (and when D reviews), Script A
extracts only the affected-dependency subgraph — interfaces, models, and callers
of the module — and sends that slice instead of whole source files.

## Decision

- `graphify-update` runs as part of the green-gate chain, only after a task is
  approved and committed.
- `graphify-subgraph <ws> TASK` queries the graph (`explain` / `path`) for the
  task's `touches`/`depends_on` modules and writes `<ws>/task-N-interfaces.md`
  (capped, ~100 lines). This file replaces the main agent's manual interface
  gathering for both B's next brief and D's review.
- The graph exposes structure, not method bodies; the subgraph is the only code
  context sent to B per task.

## Consequences

- B's per-task prompt input shrinks to the affected slice — direct token savings
  on the strategic tier.
- `graphify-subgraph` becomes the single deterministic replacement for the one
  LLM-composed header slice (interfaces) identified in the header analysis.
- The graph can lag uncommitted work by design; B never needs it for the task in
  flight, only for the next task, so post-commit freshness is sufficient.

## Alternatives considered

- **Update per Coder iteration:** rejected by the developer — unnecessary
  overhead; the graph is consumed at brief time and review time, not mid-edit.
- **Keep the main agent gathering interfaces (current):** rejected — it is the
  only non-deterministic slice in subagent headers and defeats the script-driven
  dispatch design.