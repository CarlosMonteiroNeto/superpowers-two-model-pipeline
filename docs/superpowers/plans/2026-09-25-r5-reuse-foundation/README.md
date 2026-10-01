# R5: Generic reuse, requirement profiles and templates

**Status:** Implementation complete locally; uncommitted for review on `codex/r5-reuse-foundation`. No push or PR was created.
**Spec:** [transition contract](../../specs/2026-09-25-codex-pipeline-design.md).
**Decisions:** [confirmed record](../../specs/2026-09-25-confirmed-pipeline-decisions.md).
**Roadmap:** [round sequence](../../../../roadmap.md).
**Plan:** [plan.json](plan.json).

## Prerequisites

- [R1](../2026-09-25-codex-pipeline/plan.json) accepted at `58810ac42b959b02529c73837e32ed7a8f757c79`; closure evidence is recorded in its README and plan.
- [R2](../2026-09-25-r2-worker-runtime/plan.json) accepted at `4383bba954233a2541a28ff366ffe8618c3c3c9a`; recorded shell/full-suite limitations are followed by later successful R4 full-suite runs.
- [R3](../2026-09-25-r3-pipeline-integration/plan.json) source accepted at `6cddf38ce55f2a2a590656ee34278891b0afcb45`, acceptance bound at `abe4bc56a404d4421ec05dda4ae1546ae673f8c7`; see its README and the [support matrix](../../../testing/codex-pipeline-support-matrix.md).
- [R4](../2026-09-25-r4-execution-efficiency/plan.json) accepted at `817da04e7d92983bb33cecdc38115b4babeceb7a`; full shared suite 1,100 passed (2 skipped) and Flutter suite 150 passed. See [R4 closure](../2026-09-25-r4-execution-efficiency/README.md) and [results](../2026-09-30-r4-impact-efficiency-results.md).

Use the normal Superpowers SDD workflow: implement each task with RED/GREEN,
focused review and verification. Do not invoke the Two Model Pipeline runner,
task dispatcher, or its orchestration scripts as the workflow. Recheck paths
and interfaces against accepted predecessor commits; refresh implementation
drift without reopening confirmed choices. Do not execute transition-backlog.json
or the deferred R6 plan.

## Tasks

- [x] 1. Audit every Flutter phase and assign shared capability ownership. Dependencies: none within this round.
- [x] 2. Extract generic catalog and adoption contracts from Flutter. Dependencies: 1.
- [x] 3. Generalize deterministic recall and template refresh. Dependencies: 1, 2.
- [x] 4. Introduce applicable baseline requirement profiles. Dependencies: 1, 2.
- [x] 5. Build safe template repository and promotion workflows. Dependencies: 1, 2, 3, 4.
- [x] 6. Generalize research, dependency preparation and compatible adoption. Dependencies: 1, 2, 3, 4, 5.
- [x] 7. Integrate reuse into planning and prove ecosystem compatibility. Dependencies: 1, 2, 3, 4, 5, 6.

## Execution and verification

This run uses native Superpowers SDD, serial execution, and local-only changes;
no remote publication or automatic merge is authorized. The user requested Luna
at medium effort, but the active session model cannot be changed through the
available controls. Preserve that limitation in status reporting; do not claim
that Luna medium was used.

Execution baseline: `817da04e7d92983bb33cecdc38115b4babeceb7a` (`origin/main`;
R4 accepted source). The `baseline_commit` field in `plan.json` remains the
historical planning baseline from 2026-09-25.

The JSON defines exact files, interfaces, acceptance and future verification files.
These test files are deliverables, not claims of existing/passing tests. Observe
meaningful RED and preserve raw output. Run required complete suites at closure;
new regressions block. Proven inherited failures require an explicit candidate-bound
user waiver and must never be reported as green.

This completes active roadmap scope. The new brainstorming classifier remains deferred.

### Implementation closure

- Shared suite: 1,152 passed, 2 skipped; Flutter suite: 151 passed.
- After the final requirement-profile applicability refinement, all 53 R5-focused tests passed; the directly affected Flutter recall and `pub-sync` checks passed (12 tests).
- The shared generic profile no longer adds accessibility requirements to non-UI work. The shared UI profile adds accessibility only when applicable; Flutter forms compose it with Flutter-specific form requirements.
- The R5 plan records local completion. Changes remain uncommitted for review; there is no push, PR, or remote publication.
