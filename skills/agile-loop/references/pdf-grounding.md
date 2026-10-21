# PDF Grounding — Agile Loop (Gestao Agil U1-U4 + Qualidade U4)

## 1. Agile and Scrum Foundations (Gestao Agil U1)
- The Agile Manifesto states 4 values: individuals and interactions over processes and tools, working software over comprehensive documentation, customer collaboration over contract negotiation, and responding to change over following a plan.
- Incremental delivery replaces big-bang release: each increment adds a tested, integrated slice of working software, so feedback arrives early and risk compounds downward instead of upward.
- Scrum is a framework, not a methodology: it defines roles, events, and artifacts with fixed rules but leaves engineering techniques open, so teams plug in practices (TDD, CI, refactoring) without breaking the frame.
- The Product Owner owns value and order: sole authority over backlog priority, accepts or rejects increments, and translates stakeholder needs into ordered items the team can pull.
- The Development team owns delivery estimates: self-organizing, cross-functional, and accountable for turning backlog items into done increments within the sprint timebox.
- The Scrum Master owns process and impediments: coaches the framework, removes blockers, shields the team from external interruption, and enforces timeboxes without commanding the work.
- The 3 pillars are transparency (backlog, board, and increment visible to all), inspection (daily, review, and retro examine progress toward the goal), and adaptation (plan and process change as soon as deviation is detected).
- The 5 Scrum values are commitment, courage, focus, openness, and respect: the team commits to goals, shows courage on hard problems, stays focused per sprint, stays open about blockers, and respects every role.

## 2. Sprint Execution (Gestao Agil U2)
- Sprints run 14-30 days with a fixed goal: scope is frozen once planning ends, so the team can inspect real progress against a stable target instead of chasing moving requirements.
- Sprint planning is timeboxed at 8h for a 4-week sprint (shorter for shorter sprints) in two parts: what to build (PO proposes the goal, team selects backlog items) then how to build it (team decomposes items into tasks).
- The daily meeting is 15 minutes with 3 questions per member: what was done, what is next, and what blocks progress; it synchronizes the plan and surfaces impediments, never a status report to management.
- The sprint review demos working software to stakeholders: only done increments are shown, feedback becomes new or reordered backlog items, and undone work is never presented as progress.
- The retrospective is blameless with 3 questions: what went well, what to improve, and what to try next sprint; one or two actionable improvements enter the next sprint backlog with an owner.
- The Scrum Master watches for classic biases: anchoring on the first estimate spoken, groupthink silencing dissent in planning, and recency bias overweighting the last days of the sprint in the retro.
- Only done counts at sprint end: partially finished stories return to the product backlog, and velocity is computed exclusively from increments meeting the Definition of Done.

## 3. Backlog Mechanics (Gestao Agil U3-U4)
- The product backlog is a single ordered list: highest value and risk first, continuously refined so top items are small and testable while lower items stay coarse until their turn approaches.
- INVEST defines a ready story: Independent, Negotiable, Valuable, Estimable, Small, and Testable; any story failing one letter is split or rewritten before it enters sprint planning.
- The story format is who/what/why: as a <role>, I want <goal>, so that <benefit>, plus explicit acceptance criteria that make validation mechanical rather than subjective.
- Kano plus ROI/risk prioritization orders the backlog: must-have expectations first, then performance features ranked by return, then delighters, with high-risk items pulled early to retire uncertainty.
- The sprint backlog holds the committed stories plus their tasks in hours: each task is sliced to 8 hours or less so remaining work is re-estimated daily and slippage shows within one day.
- The burndown chart tracks remaining hours against the ideal line: updated at the daily meeting, it exposes scope creep or stalled work immediately instead of at sprint end.
- Planning poker with the Fibonacci scale builds consensus estimates: simultaneous reveal defeats anchoring, outliers explain their reasoning, and re-voting converges without authority pressure.
- Definition of Ready is the entry gate (story clarified, sized, testable) and Definition of Done is the exit gate (coded, tested, reviewed, accepted); the increment is the sum of all done stories integrated into working software.

## 4. Quality in Agile (Qualidade U4)
- A demo every sprint makes quality visible: stakeholders judge working increments against Done, and rejected stories return to the backlog with explicit gaps instead of vague rework requests.
- TDD plus CI plus regression forms the safety net: one failing test, minimal code, refactor (Red-Green-Refactor), with the full suite running on every commit so regressions surface within minutes.
- Defect metrics steer the loop: defect density per story, escaped defects found after the sprint, and rework hours per sprint tell whether speed is being bought with hidden quality debt.
- Static reviews complement dynamic testing: backlog refinement checks story testability before coding, and sprint review checks user-visible behavior after coding, catching different defect classes.
- Done includes quality evidence: each accepted story ships with its passing tests and review record, so the increment audit trail connects every feature to the checks that proved it.
- Continuous improvement is measured: the retro picks quality experiments (stricter DoR, added test layer), and the next sprint metrics confirm whether defect counts actually moved.
