---
name: verification-test
description: Use when planning tests, designing black/white-box cases, planning form validation and input-mask coverage, scaffolding TDD Red tests, or selecting automation and regression candidates.
---

# Verification Test

## When to Use This Skill
- Test plan (IEEE 829), traceability, environment and defect workflow.
- Form validation, mask, canonical-payload, and legacy-value coverage.
- Case design: equivalence partition, BVA, base-path (McCabe V(G)=E-N+2), alpha/beta, regression.
- FIRST TDD scaffold and smoke/regression automation triage.

## Route elsewhere
- Debugging root cause -> systematic-debugging.
- Full pipeline QA in browser -> external open-mercato om-integration-tests (approval required).

## Checklist (grounded: Teste U1-U4)
1. Plan: 10% plan / 40% design / 45% execute / 5% deliver; IEEE 829 artifacts.
2. Black-box: 1 valid + 2 invalid partitions per interval; test edges + outputs.
3. White-box: base-path set from flow graph; loop boundaries n-1/n/n+1.
4. TDD: Red (one failing FIRST test) -> Green (minimal) -> Refactor; prove red-green by revert check.
5. Automation: smoke + regression + critical + repetitive first; dedicated isolated prod-like env.
6. Output: test plan + case list + RED scaffold for Agente operador; when a
   form applies, include the form matrix and its scope decisions.

## Form test matrix (conditional)

Use this matrix when the change adds or edits a data-entry form. Map every case
to an acceptance criterion and the product's actual entry mode.

- Fields: empty, boundary, malformed, and valid values; required and format cues.
- Timing: before first blur, after blur, submit with every field invalid, then
  correct one field and retry.
- Dates: displayed format, selectable range, impossible dates, timezone-safe
  date-only storage; test the calendar-only path when typed dates are excluded.
- Phones: mask and cursor behavior, accepted digit count and DDD, canonical wire
  value on save, and unchanged legacy display.
- Payload: canonical value on create/update; server rejection keeps input; an
  unchanged legacy value is not silently rewritten.
- UI and platform: keyboard inset, 360px width, 200% text, Android + web parity.
- Regression: open, display, and save an existing record without changing its
  untouched fields.

Do not create cases for a fallback or feature the brief excludes. Record it as
out of scope with the product constraint.
