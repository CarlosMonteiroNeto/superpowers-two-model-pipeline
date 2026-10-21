---
name: quality-gate
description: Use when defining Done, running SQA/SQC checks, costing quality trade-offs, or auditing compliance against ISO and maturity models.
---

# Quality Gate (overlay)

## When to Use This Skill
- Definition of Done, SQA vs SQC classification, good-enough dilemma.
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
5. Output: Done checklist + audit findings appended to the brief.
