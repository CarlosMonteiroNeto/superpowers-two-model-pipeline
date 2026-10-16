# PDF Grounding — Quality Gate (Qualidade U1-U4 + Eng Software U2)

## 1. Quality Foundations (Qualidade U1)
- Quality is relative per stakeholder: users judge fitness for use, developers judge conformance to specification, and managers judge cost-benefit balance; the Definition of Done must reconcile all three views.
- Garvin defines 5 views of quality: transcendent (innate excellence), product-based (measurable attributes), user-based (fitness for use), manufacturing-based (conformance to requirements), and value-based (performance at an acceptable price).
- The gurus shaped modern practice: Shewhart introduced statistical control charts, Deming drove continuous improvement and the PDCA cycle, Juran set the quality trilogy of planning/control/improvement, Ishikawa added cause-effect diagrams and quality circles, Feigenbaum defined total quality control, and Crosby pushed zero defects and the cost of nonconformance.
- McCall and Boehm factor models decompose quality into product operation (correctness, reliability, efficiency, integrity, usability), product revision (maintainability, flexibility, testability), and product transition (portability, reusability, interoperability).
- ISO 25010 defines 8 product characteristics: functional suitability, performance efficiency, compatibility, usability, reliability, security, maintainability, and portability, plus quality-in-use characteristics (effectiveness, efficiency, satisfaction, freedom from risk, context coverage).
- SQA is process-oriented defense of the customer: audits and process checks that prevent defects by ensuring the team follows the documented process; SQC is product-oriented: inspections, reviews, and measurements that detect defects in artifacts.
- The good-enough dilemma bounds quality work: beyond a threshold, extra prevention and appraisal cost exceeds failure savings, so Done is set where stakeholder value minus quality cost is maximized, guided by Pareto 80/20 on defect causes.

## 2. Norms and Governance (Qualidade U2)
- ISO 9000 states quality fundamentals and vocabulary, ISO 9001 sets auditable requirements for a quality management system (customer focus, leadership, process approach, continual improvement), and ISO 9004 gives guidance for sustained success beyond minimum certification.
- The product-quality lineage runs from ISO 9126 (product quality model) plus ISO 14598 (evaluation process) into the SQuaRE 25000 series, which unifies quality model, measurement reference, requirements, and evaluation guidance in one family.
- ISO 12207 organizes software life-cycle processes into families: primary (acquisition, supply, development, operation, maintenance), supporting (documentation, configuration management, quality assurance, verification, validation, reviews, audits, problem resolution), and organizational (management, infrastructure, improvement, training).
- ISO 29110 (VSE) profiles tailor 12207-style processes for very small entities: a minimal management plus implementation process set with light deployment packages, so small teams get auditability without heavyweight overhead.
- Quality management (setting policy and objectives for the organization) differs from quality assurance (planned process activities giving confidence requirements will be met), quality control (operational product checks finding defects), and quality planning (defining which standards and metrics apply to a specific project).
- Compliance mapping connects each norm clause to concrete artifacts: 9001 clauses map to the quality plan and audit records, 25010 characteristics map to acceptance criteria in Done, and 12207 processes map to phase gates and review checklists.
- Audits follow a fixed route: plan scope against the norm, examine process records and product evidence, classify findings as conformities or nonconformities, and append corrective actions with owners and due dates to the brief.

## 3. Maturity and Improvement (Qualidade U3)
- SPI (software process improvement) runs assess-current-state, plan changes, implement pilots, then institutionalize; every cycle is measured so improvement claims rest on metric deltas rather than opinion.
- CMMI defines 5 maturity levels: 1 Initial (chaotic, hero-driven), 2 Managed (projects planned and controlled), 3 Defined (organization-wide standard process), 4 Quantitatively Managed (statistical control of subprocesses), 5 Optimizing (continuous causal improvement).
- MPS.BR defines 7 levels from G (partially managed) up to A (optimizing), mapped against CMMI-compatible process attributes so Brazilian organizations can progress stepwise toward higher maturity.
- SPICE (ISO 15504/33000) assesses process capability per process on a 0-5 scale, while COBIT governs IT at enterprise level by linking business goals to IT processes, controls, and maturity targets.
- Six Sigma DMAIC structures defect reduction: Define the quality goal, Measure current defects per million opportunities, Analyze root causes, Improve the process, Control with charts and gates to hold the gains.
- GQM (Goal-Question-Metric) derives metrics top-down: state a measurement goal, ask the questions that decide the goal, then define only the metrics that answer those questions, avoiding vanity dashboards.

## 4. Agile Quality (Qualidade U4 + Eng Software U2)
- The Agile Manifesto prioritizes individuals and interactions, working software, customer collaboration, and responding to change; quality follows from short feedback loops rather than heavy upfront specifications.
- Scrum frames quality per sprint (planning, daily sync, review, retrospective) while XP supplies engineering practices (pair programming, simple design, refactoring, collective ownership, coding standards) that keep defect injection low.
- A demo per sprint makes quality visible: stakeholders judge working increments against Done, and rejected stories return to the backlog with explicit quality gaps instead of vague rework.
- TDD plus CI plus regression forms the agile safety net: write one failing test, add minimal code, refactor (Red-Green-Refactor), then run the full suite on every commit so regressions surface within minutes.
- IEEE 1061 and GQM guide agile metrics: select validity-grounded product and process metrics top-down from release goals, combining velocity and burn-down with defect density, escaped defects, and lead time.
- Metrics split into dynamic (execution-based: failure rate, response time, MTBF observed under test or operation) versus static (representation-based: complexity, coupling, documentation completeness measured without running the code).
- Quality-in-use closes the loop: internal quality (code-level measures during development) predicts external quality (behavior observed in test), which predicts quality in use (effectiveness, satisfaction, and freedom from risk experienced by real users).
