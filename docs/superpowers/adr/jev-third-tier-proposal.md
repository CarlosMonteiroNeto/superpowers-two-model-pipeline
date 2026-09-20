# Proposed: advisory trust tier and reviewer no-bypass boundary

Status: Proposed for maintainer review. This document is not an accepted ADR
and intentionally has no numbered ADR identifier.

## Context

Jev can provide bounded semantic advice at several pipeline sites, including
the Site 4 choice of procedural reviewer depth. Advice is useful only when the
runtime keeps the existing script-owned boundaries and retains enough evidence
for an independent reviewer. A classifier response is typed and calibrated
metadata; it is not an approval, a test result, or a replacement for the
reviewer.

## Proposal

Place Jev in a trust tier below the Script CEO and the Agente revisor. The
classifier may produce an advisory choice and telemetry through the private
Jev store. Deterministic scripts enforce evidence budgets, policy bindings,
thresholds, exclusions, timeouts, and fallback behavior. The existing
reviewer remains the sole semantic approval authority and continues to receive
the complete brief and diff.

For Site 4, the shared `review-package` boundary may append procedural
`focused_review` guidance only for an active calibrated policy with confidence
at least `0.9` and no deterministic exclusion. Off, shadow, unavailable,
uncertain, oversized or incomplete evidence, corrective work, fused provenance,
or an interface-touch advisory select standard guidance. The reviewer dispatch,
JSON verdict schema, approval criteria, ledger transitions, and routing remain
unchanged. A hook failure is an advisory fallback; failure to construct the
required baseline package remains a pipeline error.

## No-bypass constraints

- Jev cannot emit or infer `APPROVED`, `SEND_BACK`, or `ESCALATE`.
- Jev cannot substitute an agent or model, skip the reviewer, or alter routing.
- Jev cannot write `review_outcome`, `task_complete`, gate-success, corrective,
  or authoritative ledger entries.
- Focus guidance contains procedural attention only, with no approval
  probability or predicted verdict.
- Shadow agreement and executed reviewer outcomes remain separate offline
  evaluation populations. No observed metric activates a policy automatically.

## Consequences and review questions

The design preserves the current approval and routing guarantees while allowing
calibrated experiments to measure review depth. Maintainers should review the
trust-tier vocabulary, evidence accounting, and policy lifecycle before
accepting this proposal. Acceptance requires an explicit numbered ADR and an
independent review of the mocked evaluation evidence.
