# ADR-0006: Agente diretor owns tasks; Agente estratégico ends at plan+spec; Agente operador authors RED

- **Status:** Accepted
- **Date:** 2026-09-10

## Context

Agente estratégico authored every per-task artifact (briefs, RED tests,
EXPECTED-RED, corrective briefs) and ruled every arbitration — the
strategist session was a link in the per-task chain despite "never sits
in the dispatch chain". The developer's architecture removes Agente
estratégico from the loop entirely after plan+spec: a new agent generates
all tasks at once and stays available for corrective tasks and closing;
Agente operador authors RED tests; Script CEO receives every result and
drives every transition. Script CEO is invokable anywhere as
`scripts/run-pipeline PLAN_FILE`.

Display names: Script CEO (= Script A), Agente estratégico (= B),
Agente diretor (= task creator), Agente operador (= coder),
Agente revisor (= reviewer). Machine identifiers (`two-model-coder`,
`coder_round`, flags, paths) are unchanged.

## Decision

- Agente estratégico writes plan shell + spec only. Agente diretor
  (`two-model-task-generator`, Strategic tier) expands `tasks[]`
  (acceptance + expected_red), appends corrective tasks (`corrects: N`),
  performs branch closing. Dispatched once per branch; resumed only on
  demand; task text in, never diffs/logs.
- No `task-N-task.md` files: enriched `plan.json` (tracked) is the only
  task record. Briefs are scaffolded mechanically per task (transient).
- Agente operador writes RED tests + implementation in one session. RED is
  proved by execution (RED-proof: stash `touches`, new tests must fail
  with the task's `expected_red`, restore, hash-compare at commit).
  Agente revisor judges test-vs-acceptance fit.
- Corrective tasks are normal plan tasks routed to the original operador
  session. TEST_DEFECT is ruled by Agente diretor (fix task, re-scaffold).
- Closing by Agente diretor (final-gate with short-circuit, review
  package, assessment), then default push+PR.
- `dispatch` prints a live progress digest to stdout; full JSON still
  lands in the log.

## Consequences

- Operador-authored RED weakens the old ground-truth guarantee
  (implementer grades its own homework); mitigated by RED-proof +
  diretor-authored `expected_red` + revisor test-scope. Accepted residual.
- Agente diretor session persists across the branch (context discipline
  required: task text only).
- Retired from the flow: estrategista briefs/RED/correctives/arbitration/
  holistic review; red-gate materialization; red-integrity old definition.

## Rejected alternatives

- Agente estratégico keeps authoring RED (rejected: keeps it in the
  per-task chain).
- Two-phase operador dispatch, tests-first (rejected: doubles dispatches;
  revisor verification deemed sufficient).
- Separate `task-N-task.md` files (rejected: redundant with plan.json).
- Raw HTTP model calls (rejected: keep current dispatch; add live digest
  for observability instead).
