# PDF Grounding — Verification Test (Teste U1-U4)

## 1. Test Foundations (Teste U1)
- Testing has two goals: validation (the system meets expectations) and defect-finding (exposing faults before release); plan cases for both, not only happy paths.
- V&V levels run unit -> integration -> system -> acceptance; each level needs its own environment, entry criteria, and responsible owner.
- IEEE 829 artifacts structure the effort: test plan, test design specification, test case specification, test procedure, test log, and incident/defect report.
- The test cycle splits roughly 10% plan / 40% design / 45% execute / 5% deliver; under-investing in design produces weak coverage that execution cannot recover.
- Traceability links each requirement to its cases and results so gaps and requirement changes surface mechanically.
- Defect workflow is report -> triage -> fix -> retest -> regression check; every incident record keeps severity, steps to reproduce, environment, and observed versus expected output.

## 2. Test Design — Black-Box and White-Box (Teste U2-U3)
- Equivalence partition: split each input interval into 1 valid plus 2 invalid partitions and pick at least one representative value per partition.
- Boundary value analysis (BVA): test edges and outputs at min-1/min/min+1 and max-1/max/max+1 because faults cluster at limits, not at midpoints.
- Orthogonal arrays and error-guessing complement partitions: cover representative input combinations and inject historically likely mistakes (empty, null, zero, overflow, format edge cases).
- White-box base-path: build the flow graph, compute McCabe V(G) = E - N + 2, and derive one independent path per unit of complexity for the basis set.
- Loop boundaries: exercise n-1/n/n+1 iterations plus zero, single-pass, and maximum-pass cases; nested loops get boundary tests inside-out.
- Alpha versus beta: alpha runs in-house with developer observation, beta runs with real users in their environment; acceptance, regression, and non-functional (performance, load, security, usability) cases complete the design set.

## 3. Advanced and Niche Topics (Teste U3, niche)
- Mutation testing (DeMillo): seed small faults (mutants) into the code and require the suite to kill them; surviving mutants reveal weak assertions — niche, use only when coverage is already strong.
- Object-oriented test specifics: test encapsulation boundaries via public contracts, cover inheritance overrides per subclass, and verify polymorphic dispatch across the hierarchy — niche for OO-heavy codebases.
- Model-based testing (MBT) with finite state machines: derive cases from states and transitions to cover unreachable states and illegal transitions — niche pointer, apply when a formal behavior model exists.
- Concurrency and exception-path testing belong here too: force interleavings, timeouts, and every catch/finally branch rather than assuming sequential success paths.
- Statistical and reliability-oriented sampling (operational profiles, usage-weighted cases) is a niche complement when release risk must be quantified.
- Rule: treat this whole section as opt-in; default engagements stop at Section 2 unless the codebase or risk profile explicitly demands these techniques.

## 4. Applied Testing and Automation (Teste U4)
- Web specifics: cover navigation flows, form validation, session/authentication states, and cross-browser rendering against a fixed supported matrix.
- Mobile specifics: cover installation/update flows, network on/off transitions, interruptions (calls, notifications), and device fragmentation on representative targets.
- TDD FIRST discipline: Fast, Independent, Repeatable, Self-validating, Timely; cycle Red (one failing test) -> Green (minimal code) -> Refactor, and prove red-green with a revert check.
- Automation triage: automate smoke plus regression plus critical plus repetitive cases first; one-shot exploratory cases stay manual.
- Selenium-class tooling: drive browser UI through scripted locators and assertions with isolated test data; keep locators stable and suites runnable headless in CI.
- Continuous integration: every commit triggers build plus smoke plus unit suites in a dedicated isolated prod-like environment; broken builds block merge until green.
