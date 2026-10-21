---
name: verification-test
description: Use when planning tests, designing black/white-box cases, scaffolding TDD Red tests, or selecting automation and regression candidates.
---

# Verification Test

## When to Use This Skill
- Test plan (IEEE 829), traceability, environment and defect workflow.
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
6. Output: test plan + case list + RED scaffold for Agente operador.
