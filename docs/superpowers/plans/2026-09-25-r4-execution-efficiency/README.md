# R4: Bounded dispatch and affected verification

**Status:** In progress; execution authorized for the isolated R4 run recorded in `plan.json`.
**Spec:** [transition contract](../../specs/2026-09-25-codex-pipeline-design.md).
**Decisions:** [confirmed record](../../specs/2026-09-25-confirmed-pipeline-decisions.md).
**Roadmap:** [round sequence](../../../../roadmap.md).
**Plan:** [plan.json](plan.json).

## Prerequisites

- [R1](../2026-09-25-codex-pipeline/plan.json) accepted with commit and verification evidence.
- [R2](../2026-09-25-r2-worker-runtime/plan.json) accepted with commit and verification evidence.
- [R3](../2026-09-25-r3-pipeline-integration/plan.json) accepted at `6cddf38`, acceptance bound at `abe4bc5`; see [support matrix](../../../testing/codex-pipeline-support-matrix.md).

Recheck paths/interfaces against accepted predecessor commits before execution;
refresh implementation drift without reopening the user's confirmed choices.
Do not execute transition-backlog.json or the deferred R6 plan.

## Tasks

- [ ] 1. Centralize correction routing and enforce dispatch budgets. Dependencies: none within this round.
- [ ] 2. Build evidence-bound affected-test selection. Dependencies: none within this round.
- [ ] 3. Record baseline failures and explicit closing waivers. Dependencies: none within this round.
- [ ] 4. Apply impact gates at task, integration and closing boundaries. Dependencies: 1, 2, 3.
- [ ] 5. Add dispatch-cost audits, documentation and acceptance. Dependencies: 1, 2, 3, 4.

## Execution and verification

At each new run confirm backend, operator/reviewer models (director defaults to
reviewer unless overridden), local-only versus push-and-PR, and concurrency.
Offer saved model choices; resume retains the manifest. No automatic merge.
Use an isolated checkout and pinned supervisor outside worker edits.
Use the accepted shared runtime and enforce prerequisite policy contracts.

The JSON defines exact files, interfaces, acceptance and future verification files.
These test files are deliverables, not claims of existing/passing tests. Observe
meaningful RED and preserve raw output. Run required complete suites at closure;
new regressions block. Proven inherited failures require an explicit candidate-bound
user waiver and must never be reported as green.

Next: [R5](../2026-09-25-r5-reuse-foundation/plan.json).
