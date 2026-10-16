---
name: requirements
description: Use when eliciting, clarifying, or validating software requirements, detecting ambiguity, or trading off NFRs before architecture decisions.
---

# Requirements

## When to Use This Skill
- Requirements are vague, volatile, or untestable.
- Choosing architecture drivers from NFRs (performance vs security vs availability).
- Writing or refining user stories with INVEST criteria.

## Route elsewhere
- UML/diagram choice -> design-oo-ux.
- Sprint/backlog ordering mechanics -> agile-loop.

## Checklist (grounded: Eng Software U1, Agile U4)
1. List the 7 elicitation tasks; mark which are unresolved.
2. Flag scope/comprehension/volatility risks explicitly.
3. Separate functional vs non-functional vs domain rules.
4. NFR decision: performance=few large components, security=layers, availability=redundancy, maintainability=small components; record the trade-off.
5. Output: clarified requirement list + acceptance criteria for the brief.
