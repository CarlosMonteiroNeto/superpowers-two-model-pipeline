# Round 1: safe shared harness foundation

**Status:** Complete planning artifact; implementation has not started.
**Spec:** [transition contract](../../specs/2026-09-25-codex-pipeline-design.md).
**Decisions:** [confirmed record](../../specs/2026-09-25-confirmed-pipeline-decisions.md).
**Roadmap:** [round sequence](../../../../roadmap.md).
**Plan:** [plan.json](plan.json).

## Prerequisites

Reviewed source baseline and an explicitly requested implementation workflow.

Recheck paths/interfaces against accepted predecessor commits before execution;
refresh implementation drift without reopening the user's confirmed choices.
Do not execute transition-backlog.json or the deferred R6 plan.

## Tasks

- [ ] 1. Make harness synchronization non-destructive. Dependencies: none within this round.
- [ ] 2. Define shared runtime configuration and backend capability reports. Dependencies: none within this round.
- [ ] 3. Define shared invocation and semantic result schemas. Dependencies: 2.
- [ ] 4. Install immutable harness versions and bind projects with canonical documentation. Dependencies: 1, 2, 3.

## Execution and verification

At each new run confirm backend, operator/reviewer models (director defaults to
reviewer unless overridden), local-only versus push-and-PR, and concurrency.
Offer saved model choices; resume retains the manifest. No automatic merge.
Use an isolated checkout and pinned supervisor outside worker edits.
Bootstrap through an explicitly launched development workflow; the current runner is not the finished shared pipeline. R3 is an integration milestone, and R4 must enforce the agreed policies before unattended production adoption.

The JSON defines exact files, interfaces, acceptance and future verification files.
These test files are deliverables, not claims of existing/passing tests. Observe
meaningful RED and preserve raw output. Run required complete suites at closure;
new regressions block. Proven inherited failures require an explicit candidate-bound
user waiver and must never be reported as green.

Next: [R2 worker runtime](../2026-09-25-r2-worker-runtime/plan.json).
