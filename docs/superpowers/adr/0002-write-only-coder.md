# ADR-0002: Write-only Coder; test/analyze decisions live in the script

- **Status:** Accepted
- **Date:** 2026-09-02

## Context

Today the Coder runs test commands itself (through `scripts/cmd`) to iterate, and
the Orchestrator re-runs the suite + analysis at wrap-up. The developer's
architecture makes C a pure executor: it writes code against the brief + RED
tests, and Script A decides whether the task tests, the full suite, and
`flutter analyze` pass — feeding failures back to C for a fix round.

## Decision

C never invokes test or analysis commands. Script A runs the gate sequence:
task tests → full suite → analyze, in that order, each pass/fail decided by exit
code inside the script. On any failure, Script A resumes the same C session with
the failure output (minified by `token-kill`) for the next fix round. Budget:
round 1 + 3 fixes (4 attempts total), then `ARBITRATE` to B.

## Consequences

- C's context stays minimal (no command output ever enters it); token cost per
  task drops.
- The test/analyze verdicts are deterministic and observable in gate report files.
- Round-trip latency per fix increases (C cannot self-iterate quickly), mitigated
  by resuming the same session so it keeps its mental model of the code.

## Alternatives considered

- **C iterates with `scripts/cmd` (current behavior):** rejected — puts command
  output in C's context and duplicates gate logic across C and the Orchestrator.
- **2-round budget (current):** rejected in favor of 4 total attempts per the
  developer's decision.