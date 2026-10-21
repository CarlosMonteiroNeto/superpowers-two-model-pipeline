---
name: design-oo-ux
description: Use when designing OO classes, selecting UML diagrams, defining UP phase exit criteria, choosing UX prototype fidelity, evaluating interfaces, or building/reviewing gesture-driven UI, spring animations, drag/swipe/sheet interactions, momentum, interruptible transitions, translucent materials, depth, typography, reduced-motion, or Apple-style design foundations. Interface guidance prevails over structure on conflict.
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
spec sections and plan task acceptance.
