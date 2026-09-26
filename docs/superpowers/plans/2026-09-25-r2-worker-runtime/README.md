# R2: Worker runtime, prompts and backend adapters

**Status:** Complete planning artifact; implementation has not started.
**Spec:** [transition contract](../../specs/2026-09-25-codex-pipeline-design.md).
**Decisions:** [confirmed record](../../specs/2026-09-25-confirmed-pipeline-decisions.md).
**Roadmap:** [round sequence](../../../../roadmap.md).
**Plan:** [plan.json](plan.json).

## Prerequisites

- [R1](../2026-09-25-codex-pipeline/plan.json) accepted with commit and verification evidence.

Recheck paths/interfaces against accepted predecessor commits before execution;
refresh implementation drift without reopening the user's confirmed choices.
Do not execute transition-backlog.json or the deferred R6 plan.

## Tasks

- [ ] 1. Build complete context packages and executable toolchain descriptors. Dependencies: none within this round.
- [ ] 2. Build reusable skill-source discovery and refresh. Dependencies: 1.
- [ ] 3. Resolve pinned task skills and adapted upstream prompt headers. Dependencies: 1, 2.
- [ ] 4. Enforce separate Codex and OpenCode role policies. Dependencies: 1, 3.
- [ ] 5. Implement both backend adapters with shared session lifecycle. Dependencies: 1, 3, 4.
- [ ] 6. Ship and verify worker runtime contracts for both backends. Dependencies: 1, 2, 3, 4, 5.

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

Next: [R3](../2026-09-25-r3-pipeline-integration/plan.json).
