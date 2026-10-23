---
name: quality-gate
description: Use when defining Done, gating form features, running SQA/SQC checks, costing quality trade-offs, or auditing compliance against ISO and maturity models.
---

# Quality Gate (overlay)

## When to Use This Skill
- Definition of Done, SQA vs SQC classification, good-enough dilemma.
- Form-feature release gates: input contract, validation evidence, legacy data.
- Compliance mapping (ISO 9001/25010/12207) to artifacts; audit route.
- Maturity self-check (CMMI/MPS.BR) as-is vs to-be pointer.

## Route elsewhere
- Executable test cases -> verification-test.
- Security audit execution -> external google/mantis (approval required).

## Checklist (grounded: Qualidade U1-U4 + Eng Software U2)
1. Set Done from ISO 25010 product + quality-in-use characteristics.
2. Separate SQA (process defense of the customer) from SQC (product checks).
3. Cost lens: prevention + appraisal + internal/external failure; apply Pareto 80/20.
4. Metrics: dynamic (execution) vs static (representation); GQM top-down for new metrics.
5. Output: Done checklist + audit findings appended to the brief; when forms
   apply, include the form contract and scope decisions.

## Form Done gate (conditional)

Use this gate when Done covers a data-entry form. The product contract, not a
generic form checklist, supplies the blocking items.

- Validation timing: blur and submit behavior, all-invalid reporting, and
  correction without punishing typing are stated and evidenced.
- Input contract: field masks, accepted numbering plan, date entry mode,
  required fields, and canonical save format match the approved spec.
- Legacy behavior: unchanged old values are preserved; editing produces the
  canonical value; no silent rewrite is accepted.
- Evidence: form acceptance table linked to tests; a server-side check for any
  client validation; 360px and 200% text; Android + web evidence.
- Scope: every generic checklist row is `apply`, `defer`, or `out of scope`
  with an owner and reason. Only applicable rows become release blockers.

A waiver names the risk, owner, and expiry. Client validation is SQC, not a
security control; server enforcement needs its own test evidence.
