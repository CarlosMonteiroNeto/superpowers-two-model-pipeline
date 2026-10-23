---
name: a11y-ethics
description: Use when auditing usability heuristics, checking WCAG/POUR accessibility, auditing data-entry forms and input validation, or reviewing gamification and personalization for ethical risks.
---

# A11y Ethics (overlay)

## When to Use This Skill
- Nielsen 10-heuristic inspection, usability test metrics (completion/time/error/satisfaction).
- POUR checks (alt-text, keyboard, plain language, screen-reader robustness) + responsive checks.
- Ethics review: transparency, privacy, equity, consent, auditability of personalization.

## Route elsewhere
- Visual execution -> external ui-ux-pro-max-skill (approval required).
- Prototype structure -> design-oo-ux.

## Checklist (grounded: Usabilidade U2/U4)
1. Heuristic pass: categorize by navigation/legibility/feedback; prioritize by severity.
2. Metrics: completion rate, mean time, error rate, satisfaction; combine quanti + quali.
3. POUR + responsive breakpoints; automated validators complement but never replace PCD testing.
4. Ethics: disclose personalization, secure consent, keep user control + auditable algorithms.
5. Output: findings table + required fixes for the brief, with applicability
   recorded for form-specific items.

## Form review gate (conditional)

Use this gate when the audited flow contains a data-entry form or input
validation. Review the controls the flow actually uses, then mark each finding
`blocking`, `follow-up`, or `out of scope` with the product constraint.

- Fields: programmatic label, visible format cue, required semantics, input
  purpose, 48dp target, contrast, and readable error beside the field.
- Errors: specific correction text, not color alone; announce the result;
  focus the first invalid field; do not punish typing before the first blur.
- Keyboard and reader: logical focus order, visible focus, complete keyboard
  operation, and a calendar/mask control that a screen reader can operate.
- Date/phone controls: the product decides calendar-only versus typed dates and
  the accepted numbering plan. Calendar-only is compliant when typed dates are
  prohibited; do not demand a manual fallback the brief excludes.
- Legacy values: keep invalid stored values visible for correction, preserve
  unchanged values, and explain the required fix.

Only applicable blocking findings gate release. A generic checklist item keeps
its `out of scope` decision with the reason.
