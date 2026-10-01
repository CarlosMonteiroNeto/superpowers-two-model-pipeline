# R3: Shared pipeline integration and acceptance

**Status:** Implemented with documented limitations; acceptance bound at `abe4bc5`.
**Spec:** [transition contract](../../specs/2026-09-25-codex-pipeline-design.md).
**Decisions:** [confirmed record](../../specs/2026-09-25-confirmed-pipeline-decisions.md).
**Roadmap:** [round sequence](../../../../roadmap.md).
**Plan:** [plan.json](plan.json).

## Prerequisites

- [R1](../2026-09-25-codex-pipeline/plan.json) accepted at `58810ac42b959b02529c73837e32ed7a8f757c79`.
- [R2](../2026-09-25-r2-worker-runtime/plan.json) accepted at `4383bba954233a2541a28ff366ffe8618c3c3c9a` with the verification limits recorded in its README.

Recheck paths/interfaces against accepted predecessor commits before execution;
refresh implementation drift without reopening the user's confirmed choices.
Do not execute transition-backlog.json or the deferred R6 plan.

## Tasks

- [x] 1. Isolate runs, worktrees and shared state with durable ownership. Dependencies: none within this round.
- [x] 2. Wire normalized outcomes into RED, GREEN and independent review. Dependencies: 1.
- [x] 3. Apply director proposals through canonical script transactions. Dependencies: 1, 2.
- [x] 4. Require a candidate-bound closing verdict and branch-wide verification. Dependencies: 1, 2, 3.
- [x] 5. Connect the complete Codex launcher, cancellation and explicit publication. Dependencies: 1, 2, 3, 4.
- [x] 6. Ship the Codex workflow through skills, documentation and both package paths. Dependencies: 5.
- [x] 7. Prove the complete adaptation with an acceptance harness and support matrix. Dependencies: 6.

## Historical execution notes

The original pre-execution workflow text is superseded by the completed status
and acceptance record below. R3 is closed with the compatibility limits recorded
in its support matrix.

Next: [R4](../2026-09-25-r4-execution-efficiency/plan.json).

## Acceptance evidence and limitations

- Source commit: `6cddf38ce55f2a2a590656ee34278891b0afcb45`; acceptance bound at
  `abe4bc56a404d4421ec05dda4ae1546ae673f8c7`.
- The [support matrix](../../../testing/codex-pipeline-support-matrix.md)
  records the 947-test generic suite, offline Codex acceptance and live Codex
  evidence.
- Full unattended OpenCode parity remains unproven because headless closing
  returned HTTP 403. The protected-path test demonstrated detection at closing,
  not write-time prevention; broad platform certification is not claimed.
