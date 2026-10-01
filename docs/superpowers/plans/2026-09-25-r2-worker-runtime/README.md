# R2: Worker runtime, prompts and backend adapters

**Status:** Implemented with documented verification limitations; closure recorded at `4383bba`.
**Spec:** [transition contract](../../specs/2026-09-25-codex-pipeline-design.md).
**Decisions:** [confirmed record](../../specs/2026-09-25-confirmed-pipeline-decisions.md).
**Roadmap:** [round sequence](../../../../roadmap.md).
**Plan:** [plan.json](plan.json).

## Prerequisites

- [R1](../2026-09-25-codex-pipeline/plan.json) accepted at `58810ac42b959b02529c73837e32ed7a8f757c79`.

This historical round is complete. Its closure evidence and remaining shell-suite
limitations are recorded below; do not interpret the original future-execution
notes as the current round status. Do not execute transition-backlog.json or the
deferred R6 plan.

## Tasks

- [x] 1. Build complete context packages and executable toolchain descriptors. Dependencies: none within this round.
- [x] 2. Build reusable skill-source discovery and refresh. Dependencies: 1.
- [x] 3. Resolve pinned task skills and adapted upstream prompt headers. Dependencies: 1, 2.
- [x] 4. Enforce separate Codex and OpenCode role policies. Dependencies: 1, 3.
- [x] 5. Implement both backend adapters with shared session lifecycle. Dependencies: 1, 3, 4.
- [x] 6. Ship and verify worker runtime contracts for both backends. Dependencies: 1, 2, 3, 4, 5.

## Historical execution notes

The original pre-execution workflow text is superseded by the completed status
and closure evidence below. R2 is closed; its documented verification limits
remain part of the evidence and are not hidden by later R4 reruns.

## Closure evidence and limitations

- Accepted source/closure commit: `4383bba954233a2541a28ff366ffe8618c3c3c9a`
  (`docs(sdd): close r2 worker runtime round`), present in `origin/main`.
- Detailed task and closure history: [R2 SDD progress](../../../../.superpowers/sdd/r2-worker-runtime-codex/progress.md).
- Flutter regression suite passed (150 tests). The generic suite ran 853 tests
  with 2 skips and one stale README assertion; the assertion was corrected and
  passed focused verification, but the full generic suite was not rerun at R2
  closure. Legacy package/sync shell checks were environment-inconclusive.
- These limitations are historical R2 evidence; R4 later reran the full shared
  and Flutter suites successfully at its accepted candidate.

Next: [R3](../2026-09-25-r3-pipeline-integration/plan.json).
