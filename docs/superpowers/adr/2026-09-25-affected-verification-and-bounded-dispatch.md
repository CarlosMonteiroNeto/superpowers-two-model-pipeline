# ADR: Bounded dispatch and evidence-based verification

- **Status:** Accepted
- **Date:** 2026-09-25
- **Related:** [ADR-0007](0007-coder-owned-red-green-loop.md), [ADR-0012](0012-script-owned-integration-gate.md)

## Context

The original coder-owned RED/GREEN loop allowed retries without a finite
dispatch budget. ADR-0012 also required a complete test gate after every
individual integration merge. R4 introduced bounded coder cycles and
evidence-bound affected verification, with complete configured suites retained
at final closing. These changes supersede the two earlier policies at those
specific points; the original ADRs remain unchanged as historical decisions.

Dispatch volume alone is not execution cost. One semantic invocation can use
multiple backend model turns, retry transport, include cached input, have
different latency, or require later repair for an escaped defect. Some
providers do not expose every usage field, and Jev is an optional advisory
call. Unknown observations must stay unknown.

## Decision

- Use the R4 configured coder-cycle budgets (default `[5, 3, 3]`, at most three
  cycles and eleven coder invocations) with explicit assessment/stop gates.
  There is no unbounded retry policy. See ADR-0007 for the superseded history.
- At task and integration boundaries, use the verified impact manifest to run
  affected checks; stale, missing or uncertain impact falls back to broader
  verification. At final closing, rerun every configured suite for affected
  toolchains. This supersedes ADR-0012's full-suite-after-every-merge rule,
  without removing its script-owned, serial integration or attribution rules.
- Every semantic dispatch call site, including dynamic dispatch and worker
  delegation, records role, trigger, expected frequency, budget, termination
  entry/condition, keep/remove/merge decision, and semantic justification.
  `dispatch-audit` checks added script lines for missing inventory,
  mechanical model routing, and call-bearing loops without a bounded exit.
- Cost reports keep semantic invocations, backend turns, transport retries,
  Jev calls, input/output/cached tokens, latency and escaped-defect
  observations separate. Metrics are aggregated only from observed records;
  an absent value is `null`. A reduction in invocation count alone never
  supports a savings claim.
- Acceptance is offline and fixture-based for Codex and OpenCode. It runs the
  regression and quality gates plus full configured suites at closure. Results
  identify candidate commit, runtime versions, commands, observed values and
  unknowns; fixtures do not certify live provider capability.

## Consequences

- A caller can compare cost only when baseline and candidate contain comparable
  observed usage and quality evidence. Otherwise the result is
  `insufficient_evidence`.
- The audit is a deterministic static guard, not a substitute for reviewing
  whether a semantic justification is sound or whether the acceptance tests
  prove behavior.
- Historical ADR-0007 and ADR-0012 remain available to explain why these rules
  changed.
