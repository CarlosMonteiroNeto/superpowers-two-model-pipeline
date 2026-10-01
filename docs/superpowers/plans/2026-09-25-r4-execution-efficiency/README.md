# R4: Bounded dispatch and affected verification

**Status:** Implemented with documented limitations; accepted at `817da04` on 2026-09-30.
**Spec:** [transition contract](../../specs/2026-09-25-codex-pipeline-design.md).
**Decisions:** [confirmed record](../../specs/2026-09-25-confirmed-pipeline-decisions.md).
**Roadmap:** [round sequence](../../../../roadmap.md).
**Plan:** [plan.json](plan.json).

## Prerequisites

- [R1](../2026-09-25-codex-pipeline/plan.json) accepted at `58810ac42b959b02529c73837e32ed7a8f757c79`.
- [R2](../2026-09-25-r2-worker-runtime/plan.json) accepted at `4383bba954233a2541a28ff366ffe8618c3c3c9a`, with historical verification limits recorded in its README.
- [R3](../2026-09-25-r3-pipeline-integration/plan.json) source accepted at `6cddf38ce55f2a2a590656ee34278891b0afcb45`, acceptance bound at `abe4bc56a404d4421ec05dda4ae1546ae673f8c7`; see [support matrix](../../../testing/codex-pipeline-support-matrix.md).

Recheck paths/interfaces against accepted predecessor commits before execution;
refresh implementation drift without reopening the user's confirmed choices.
Do not execute transition-backlog.json or the deferred R6 plan.

## Tasks

- [x] 1. Centralize correction routing and enforce dispatch budgets. Dependencies: none within this round.
- [x] 2. Build evidence-bound affected-test selection. Dependencies: none within this round.
- [x] 3. Record baseline failures and explicit closing waivers. Dependencies: none within this round.
- [x] 4. Apply impact gates at task, integration and closing boundaries. Dependencies: 1, 2, 3.
- [x] 5. Add dispatch-cost audits, documentation and acceptance. Dependencies: 1, 2, 3, 4.

## Historical execution notes

The original pre-execution workflow text is superseded by the completed status
and closure evidence below. R4 is closed with the compatibility and measurement
limits recorded in its results report.

## Closure evidence

- All five tasks are implemented and reviewed. Task 5's independent review was
  approved and its changes are included in the R4 branch merged by `817da04`.
- `python -m unittest discover -s skills/two-model-sdd-pipeline/tests -v` —
  1,100 tests passed; 2 skipped because the local Windows `zip` command does
  not accept file lists from stdin.
- `python -m unittest discover -s skills/flutter-app-pipeline/tests -v` —
  150 tests passed.
- Workload, cache, and gate measurements and their limits are recorded in the
  [R4 results report](../../2026-09-30-r4-impact-efficiency-results.md).
- The acceptance is fixture-based. It does not claim live provider capability
  or production cost savings; the small synthetic workloads showed no net
  speedup.

Next: [R5](../2026-09-25-r5-reuse-foundation/plan.json).
