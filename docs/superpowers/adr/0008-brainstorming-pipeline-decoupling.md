# ADR-0008: Decouple brainstorming from the pipeline; script-owned RED form; punctual task ownership

- **Status:** Accepted
- **Date:** 2026-09-12
- **Supersedes:** ADR-0006 (Agente diretor owns tasks, estrategista ends at plan+spec)
- **Amends:** ADR-0001 (script-autonomous dispatch), ADR-0007 (coder-owned RED/GREEN loop)

## Context

Three problems accumulated:

1. Brainstorming and the pipeline share one interactive session, and the design
   asked that session to serve as the exception owner (corrective/arbitrate/
   closing). That couples reliability to a warm provider cache: after the TTL
   expires, every exception turn re-bills the accumulated prefix.
2. `expected_red` is planner-authored. It duplicates the coder's test planning
   and is only a lexical proxy the coder can satisfy by construction — never an
   independent semantic guarantee.
3. The Agente diretor expands the plan shell, so planning is not cleanly
   separated from execution.

## Decision

- **Two sessions, one file interface.** The brainstorming session produces the
  spec and a COMPLETE `plan.json` (tasks with `acceptance`, `spec_refs`,
  `touches`, `depends_on`; no `expected_red`) and then stops. A separate clean
  session launches `run-pipeline`. The script reads only the plan file and the
  ledger.
- **`expected_red` is removed.** RED integrity is split: a deterministic
  `red-form-check` validates the form of the saved machine-readable RED (suite
  loaded, ≥1 test executed, failed as assertion/runtime); the operador
  pre-approves the reason before implementing (a self-check and the reviewer's
  artifact, not a guarantee); the revisor is the **sole independent semantic
  guarantee** (test-vs-acceptance).
- **No EXPAND.** `tasks_usable` checks `acceptance` only.
- **Task ownership is punctual.** The task-generator is dispatched per
  corrective/arbitrate episode with script-controlled context (findings + full
  plan.json + target task + spec_refs), resuming only within the episode, and
  once for closing with a curated package (plan + spec + consolidated diff +
  full ledger). No cross-branch persistent session.
- **The interactive session stays out of the dispatch chain** (ADR-0001 held;
  only the executor identity changed).

## Consequences

- Planning is complete before execution; no expansion hop.
- The semantic guarantee lives in exactly one place (the revisor); the coder's
  reason declaration is a pre-filter, documented as such.
- Every reasoning call is script-dispatched with curated context; correctness
  and economy no longer depend on cache warmth.
- A reduced-context task-generator now needs the full plan.json to avoid
  interface/dependency conflicts — the plan is compact metadata, so this is
  cheap.
- Bootstrap: this branch's own tasks still carry `expected_red` and are run by
  the old scripts until each task lands; task order prevents a broken transition.

## Alternatives considered

- **Interactive session as persistent exception owner** (corrective/arbitrate/
  closing): rejected — it re-bills its whole accumulated prefix after cache TTL
  expiry and cannot discard that prefix; only a fresh process gives controlled
  context.
- **Keep planner-authored `expected_red`**: rejected — duplicates test planning
  and is a proxy the coder can satisfy by construction, not independent.
- **Coder self-approves the RED reason as the guarantee**: rejected — implementer
  grades its own homework; kept only as a pre-filter with the revisor as the
  sole guarantee.
- **Reopen the brainstorming session for the holistic closing review**: rejected
  — full context reload and breaks the decoupling; strengthen the spec instead.
- **Reduced-context task-generator without the full plan**: rejected — it cannot
  set `touches`/`depends_on`/`spec_refs` safely without the coordination map.
