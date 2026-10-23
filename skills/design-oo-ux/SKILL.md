---
name: design-oo-ux
description: Use when designing OO classes, selecting UML diagrams, defining UP phase exit criteria, choosing UX prototype fidelity, evaluating interfaces, reviewing data-entry forms, validation, masks, or date/phone entry, or building/reviewing gesture-driven UI, spring animations, drag/swipe/sheet interactions, momentum, interruptible transitions, translucent materials, depth, typography, reduced-motion, or Apple-style design foundations. Interface guidance prevails over structure on conflict.
---

# Design (OO, UML, UP, UX & Interface)

One design entry point. The structural part (OO, UML, UP, UX) lives in
this file. The interface and motion craft lives in
`references/apple-design.md` and **wins on conflict**.

## Precedence

- Structure answers *what the parts are and how they relate*.
- Interface answers *how it responds, moves, and feels*.
- When they conflict (motion, materials, typography, the eight
  principles), interface wins. Keep the structural input in the plan
  task's `acceptance` next to the feel requirements: addition, not
  substitution.

## When to Use This Skill

- Class/method design, encapsulation, inheritance vs composition.
- Which UML diagram to draw (static vs dynamic vs functional).
- Prototype fidelity choice (paper/wireframe vs mockup vs high-fidelity)
  and POUR accessibility.
- Data-entry form UX: validation timing, masks, required cues, and
  date/phone controls.
- Gesture-driven UI, springs, drag/swipe/sheet interactions, momentum,
  interruptible transitions, translucent materials, typography,
  reduced-motion, and Apple-style design foundations.

## Structural checklist (grounded: OO U1-U2, Usabilidade U1/U3)

1. State object/class/attribute/method boundaries; prefer composition
   over inheritance.
2. Pick exactly one UML diagram type and justify (sequence=time,
   collaboration=context, execution=physical).
3. UP gate: conception (scope) vs elaboration (architecture baseline +
   risk elimination).
4. UX: fidelity ladder low->mid->high; apply POUR + Nielsen heuristics +
   contrast/keyboard checks.
5. Output: diagram prompt + class sketch + UX acceptance for the brief.

## Form UX applicability (conditional)

Use this gate when the brief includes a data-entry form or changes one. Derive
the form contract from the product's constraints, not from a generic checklist.
Record one decision per row: `apply`, `adapt`, or `defer` with the reason.

| Candidate behavior | Apply when | Acceptance criterion |
|---|---|---|
| Validate on blur and submit; revalidate edits after first blur | the value is user-entered | every invalid field shows its own inline message; one submit reports all invalid fields |
| Required and format cue before input | the value is required or constrained | visible label/helper names the expected format; required state is explicit |
| Domain mask and canonical wire value | the domain has a fixed format | mask while typing; save validates the domain shape and writes its canonical representation |
| Calendar-only date control | the product fixes the display format and excludes typed dates | the field is read-only, displays the agreed format, and opens a calendar as the only entry path |
| Legacy display/edit policy | stored records may use older formats | an unchanged legacy value is preserved; editing a value produces the canonical representation |
| Confirmation, success feedback, or autofill | the action or platform makes it relevant | acceptance states the chosen behavior and where it appears |

The form section is complete only when every row has a decision and the
approved criteria are present in the plan. An unapproved generic item remains
`defer` or out of scope; it does not become an acceptance criterion.

## Interface & motion

Before designing or reviewing any interactive surface, read
`references/apple-design.md`. It carries the full rules: response, 1:1
tracking, interruptibility, springs, velocity handoff, momentum
projection, spatial consistency, rubber-banding, gesture details, frame
smoothness, materials, multimodal feedback, reduced motion, typography,
the eight principles, and process.

Non-negotiables to carry into the spec and plan even before opening the
reference:

- Respond on pointer-down; feedback is continuous during the gesture.
- Drag tracks 1:1 from the grab offset; never center-snap on grab.
- Animations are interruptible and start from the current on-screen
  value.
- Gesture-driven motion uses springs, not fixed-duration transitions or
  keyframes.
- Momentum is projected from release velocity, not snapped from the
  release point.
- Respect `prefers-reduced-motion`, `prefers-reduced-transparency`, and
  `prefers-contrast`.

## Route elsewhere

- Ambiguous requirements -> resolve in `brainstorming`.
- Full pipeline QA in browser -> external skill (human approval
  required; fallback only).

## Output

Structural artifacts plus interface acceptance criteria, ready to become
spec sections and plan task acceptance. When forms apply, include the form
decision table with any deferred items kept outside scope.
