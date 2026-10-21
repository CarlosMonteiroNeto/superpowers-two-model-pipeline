# PDF Grounding — Design OO UX

Sources: OO fundamentals (U1-U2), UML and Unified Process (U1-U2), Usability and UX (U1/U3). English synthesis, no verbatim excerpts.

## OO Essentials
- Objects are runtime instances with identity, state, and behavior; classes are static templates defining attributes and methods shared by instances.
- Abstraction keeps only behavior-relevant properties visible and hides incidental implementation detail behind clear class boundaries.
- Encapsulation bundles state with behavior and restricts direct attribute access, exposing controlled methods that preserve invariants.
- Polymorphism lets subtypes respond to the same message with specialized behavior, enabling substitutability through common interfaces.
- Association is a structural link between classes, generalization is an is-a subtype hierarchy, and dependency is a transient uses relationship.
- Prefer composition over inheritance: reuse behavior by owning collaborators instead of extending superclasses, limiting coupling to stable interfaces.
- Keep class cohesion high and coupling low by assigning each responsibility to exactly one class and routing cross-class interaction through explicit messages.

## UML and UP Essentials
- Static family captures structure: class, object, component, deployment, package, and composite-structure diagrams.
- Dynamic family captures time-ordered behavior: sequence, collaboration/communication, state machine, and activity diagrams.
- Functional family captures intended use: use-case diagrams plus supporting textual scenarios and system sequence contracts.
- Sequence diagrams order messages along a time axis to show call order and lifelines; collaboration diagrams emphasize network topology and context over timing.
- Unified Process runs four phases: conception (vision and scope), elaboration (architecture baseline plus major-risk elimination), construction (incremental build), transition (delivery and handover).
- Conception exit requires agreed scope boundaries and feasibility; elaboration exit requires an executable architecture baseline and retired critical risks.
- Scope delimitation lists in-scope use cases and actors explicitly and defers the rest, so each iteration has verifiable completion criteria.

## UX Essentials
- Design centered on users starts from observed tasks and contexts, iterates with real feedback, and measures task success rather than opinion.
- Fidelity ladder moves low (paper sketches and wireframes for flow) to mid (clickable mockups for layout) to high (interactive prototypes for visual and behavioral validation).
- Match prototype fidelity to the question asked: test structure with low fidelity, test interaction with mid fidelity, test look-and-feel with high fidelity.
- POUR accessibility requires content to be perceivable (contrast, text alternatives), operable (keyboard paths, timing), understandable (predictable labels), and robust (assistive-technology compatible).
- Apply contrast and keyboard checks at every fidelity level: verify text contrast ratios and confirm all actions are reachable and visible without a pointer.
- Use Material Design and Human Interface Guidelines as component pointers for spacing, touch targets, and platform conventions, adapting rather than copying blindly.
- Record UX acceptance per brief as observable criteria: task completion steps, expected feedback, and accessibility checks the prototype must satisfy.
