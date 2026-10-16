---
name: coding-standards
description: Use when modularizing code, reviewing types/scope/input validation, or enforcing pure-function and no-global-state rules before implementation.
---

# Coding Standards

## When to Use This Skill
- Function vs procedure boundaries, cohesion/coupling review.
- Type/scope/casting and input-validation review.
- Top-down decomposition with Entry->Process->Exit framing.

## Route elsewhere
- Debugging a failure -> systematic-debugging (keep exactly one debugging skill installed).
- Test design -> verification-test.

## Checklist (grounded: Algoritmos U1-U3)
1. Require pseudocode + top-down breakdown before coding.
2. Enforce: initialize always, prefer locals, validate inputs (range, division-by-zero).
3. Pure functions: return values instead of mutating globals; encapsulate shared state.
4. Recursion only with explicit base case and stack justification; else iterate.
5. Output: module/function sketch + review checklist for the brief.
