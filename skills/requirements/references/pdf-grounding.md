# PDF Grounding — Requirements

## Software requirements engineering essentials (Eng Software U1)
- The 7 elicitation tasks are initiation, elicitation, elaboration, negotiation, specification, validation, and management; track which are unresolved for each requirement.
- Requirements problems include wicked problems plus scope, comprehension, and volatility risks; flag each risk explicitly before committing to a design.
- Separate functional requirements (what the system does) from non-functional requirements (quality constraints) and domain rules (business/legal constraints).
- Use scenario-based, class-based, and flow-oriented models to make vague requirements concrete and testable.
- Capture behavior with use cases and sequence diagrams, linking each flow to its acceptance criteria.
- Let NFRs drive architecture trade-offs: performance favors few large components, security favors layers, availability favors redundancy, maintainability favors small components; record the chosen trade-off.
- Document the architecture with the 4+1 views (logical, process, development, physical, scenarios) and apply MVC to separate model, view, and controller responsibilities.

## Agile backlog essentials (Agile U4)
- Apply INVEST criteria: Independent, Negotiable, Valuable, Estimable, Small, Testable; reject stories that fail testability.
- Write stories in who/what/why format: as a <role>, I want <goal>, so that <benefit>.
- Attach explicit acceptance criteria to every story so validation is mechanical, not subjective.
- Use Definition of Ready (DoR) as the entry gate: story clarified, sized, and testable before sprint planning.
- Use Definition of Done (DoD) as the exit gate: coded, tested, reviewed, and accepted against the criteria.
- Keep the backlog ordered by value and risk, refining top items first as volatility demands.
