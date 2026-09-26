# R3: Shared pipeline integration and acceptance

**Status:** Complete planning artifact; implementation has not started.
**Spec:** [transition contract](../../specs/2026-09-25-codex-pipeline-design.md).
**Decisions:** [confirmed record](../../specs/2026-09-25-confirmed-pipeline-decisions.md).
**Roadmap:** [round sequence](../../../../roadmap.md).
**Plan:** [plan.json](plan.json).

## Prerequisites

- [R1](../2026-09-25-codex-pipeline/plan.json) accepted with commit and verification evidence.
- [R2](../2026-09-25-r2-worker-runtime/plan.json) accepted with commit and verification evidence.

Recheck paths/interfaces against accepted predecessor commits before execution;
refresh implementation drift without reopening the user's confirmed choices.
Do not execute transition-backlog.json or the deferred R6 plan.

## Tasks

- [ ] 1. Isolate runs, worktrees and shared state with durable ownership. Dependencies: none within this round.
- [ ] 2. Wire normalized outcomes into RED, GREEN and independent review. Dependencies: 1.
- [ ] 3. Apply director proposals through canonical script transactions. Dependencies: 1, 2.
- [ ] 4. Require a candidate-bound closing verdict and branch-wide verification. Dependencies: 1, 2, 3.
- [ ] 5. Connect the complete Codex launcher, cancellation and explicit publication. Dependencies: 1, 2, 3, 4.
- [ ] 6. Ship the Codex workflow through skills, documentation and both package paths. Dependencies: 5.
- [ ] 7. Prove the complete adaptation with an acceptance harness and support matrix. Dependencies: 6.

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

Next: [R4](../2026-09-25-r4-execution-efficiency/plan.json).
