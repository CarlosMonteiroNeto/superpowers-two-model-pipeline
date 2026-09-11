# ADR-0007: Coder owns the RED/GREEN loop; script approves green

- **Status:** Accepted
- **Date:** 2026-09-11
- **Supersedes:** ADR-0002 (write-only coder)

## Context

ADR-0002 made the Agente operador write-only: it authored the RED tests and the
implementation, but never ran anything. The script (`coder-gate`) proved the RED
retrospectively by stashing the implementation files listed in the plan task's
`touches`, re-running the operador's new test files, and requiring the failure
output to contain the task's `expected_red`, then restoring and hash-comparing.

That retrospective proof is sound only when the tests compile *without* the
implementation under test — i.e. a behavior change to already-committed code.
For greenfield work it fails structurally: stashing a brand-new module leaves
the test importing a missing file, so the fail-run is a compile error, not the
expected behavior failure, and `expected_red` never appears. The loop then never
converges. This blocked the first real feature work (a catalog module in the
perfume-pos project) — the operador implemented before the RED could be proved,
and `coder-gate` looped indefinitely.

## Decision

The Agente operador owns the whole RED/GREEN loop:

1. Author the RED tests.
2. RUN them itself and confirm they fail for the brief's expected reason.
3. Save that failing output to `<ws>/task-N-red.txt`.
4. Implement until the tests pass, and run them green.
5. Report DONE.

`coder-gate` no longer stashes and re-runs. Before approving green it verifies
the saved RED evidence exists and contains the task's `expected_red`; then it
runs the authoritative gate (full suite + analyze + format via `green-gate`, or
`run-gates`) and, on green, commits and dispatches the revisor. A missing or
wrong-reason evidence file is its own failure round with a dedicated fix prompt.
The retry loop stays unbounded; only `TEST_DEFECT` escalates to Agente diretor.

The operador's bash permission is narrowed to the test/analyze/format commands
(`flutter test|analyze|pub get`, `dart test|analyze|format|pub get`); git
commands and everything else stay denied, so Script CEO still owns every commit.

## Consequences

- Greenfield, UI, and scaffold tasks are now TDD-able: the operador can create a
  new file, run its new test, see it fail, then implement — no compile-error
  false RED.
- The RED is self-reported by the operador. `coder-gate`'s evidence check is an
  artifact check (does the saved output contain `expected_red`?), not a re-run;
  a determined operador could fabricate or weaken the evidence. This is the
  accepted trade for unblocking greenfield, and it is mitigated by: the narrow
  grep on the expected reason, the review of test-vs-acceptance fit, and
  `red-integrity` hash-compares where a snapshot exists.
- The operador's context now carries test output (the thing ADR-0002 avoided);
  token cost per task rises, offset by far fewer dead retry rounds.
- `red-integrity` no longer has a `coder-gate`-written snapshot by default; it
  remains available when a snapshot is present.

## Alternatives considered

- **Keep the stash RED-proof and pre-commit stub scaffolds** (so tests compile
  against committed stubs): rejected — heavy controller-side ceremony and it
  still could not express deletion/scaffold tasks.
- **Two-phase dispatch** (operador writes RED + runs it, script verifies, then
  resumes to implement): rejected as unnecessary once the operador runs the RED
  itself; the script's evidence check covers the integrity need without an extra
  round trip.
- **Fabrication-proof re-run of the RED by the script**: rejected — that is the
  stash RED-proof by another name, with the same greenfield failure.
