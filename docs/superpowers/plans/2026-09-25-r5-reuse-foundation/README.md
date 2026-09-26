# R5: Generic reuse, requirement profiles and templates

**Status:** Complete planning artifact; implementation has not started.
**Spec:** [transition contract](../../specs/2026-09-25-codex-pipeline-design.md).
**Decisions:** [confirmed record](../../specs/2026-09-25-confirmed-pipeline-decisions.md).
**Roadmap:** [round sequence](../../../../roadmap.md).
**Plan:** [plan.json](plan.json).

## Prerequisites

- [R1](../2026-09-25-codex-pipeline/plan.json) accepted with commit and verification evidence.
- [R2](../2026-09-25-r2-worker-runtime/plan.json) accepted with commit and verification evidence.
- [R3](../2026-09-25-r3-pipeline-integration/plan.json) accepted with commit and verification evidence.
- [R4](../2026-09-25-r4-execution-efficiency/plan.json) accepted with commit and verification evidence.

Recheck paths/interfaces against accepted predecessor commits before execution;
refresh implementation drift without reopening the user's confirmed choices.
Do not execute transition-backlog.json or the deferred R6 plan.

## Tasks

- [ ] 1. Audit every Flutter phase and assign shared capability ownership. Dependencies: none within this round.
- [ ] 2. Extract generic catalog and adoption contracts from Flutter. Dependencies: 1.
- [ ] 3. Generalize deterministic recall and template refresh. Dependencies: 1, 2.
- [ ] 4. Introduce applicable baseline requirement profiles. Dependencies: 1, 2.
- [ ] 5. Build safe template repository and promotion workflows. Dependencies: 1, 2, 3, 4.
- [ ] 6. Generalize research, dependency preparation and compatible adoption. Dependencies: 1, 2, 3, 4, 5.
- [ ] 7. Integrate reuse into planning and prove ecosystem compatibility. Dependencies: 1, 2, 3, 4, 5, 6.

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

This completes active roadmap scope. The new brainstorming classifier remains deferred.
