# Skill Routing Table

Keyword (lowercase substring of intent) -> exactly one skill. The cross-skill
eval asserts each sample intent routes to exactly the listed skill.

| Keyword | Skill |
|---|---|
| ambiguous requirement | requirements |
| sequence diagram | design-oo-ux |
| boundary value | verification-test |
| ec2 | cloud-deploy |
| definition of done | quality-gate |
| sprint retrospective | agile-loop |
| wcag audit | a11y-ethics |
| high cohesion low coupling | coding-standards |

## Route-elsewhere matrix

| From | To |
|---|---|
| requirements | design-oo-ux for diagrams; agile-loop for backlog mechanics |
| design-oo-ux | requirements for ambiguity; superpowers apple-design (vendored) for visual feel/execution; ui-ux-pro-max-skill (external, approval required) as fallback |
| coding-standards | systematic-debugging for failures; verification-test for test design |
| verification-test | systematic-debugging for root cause; open-mercato om-integration-tests (external, approval required) for browser QA |
| cloud-deploy | ops-engineering-skills cicd-tooling (external, approval required) for pipelines |
| quality-gate | verification-test for executable cases; google/mantis (external, approval required) for security audit |
| agile-loop | requirements for ambiguity; quality-gate plus verification-test for agile QA mechanics |
| a11y-ethics | ui-ux-pro-max-skill (external, approval required) for visual execution; design-oo-ux for structure |

## Single-debug-skill rule

Exactly one debugging skill may be installed per workspace: keep
systematic-debugging OR diagnosing-bugs, never both. (Both
skills/coding-standards/SKILL.md and skills/verification-test/SKILL.md
reference the SAME single debugging skill systematic-debugging; that is
compliant — one distinct debug skill, referenced twice.)
