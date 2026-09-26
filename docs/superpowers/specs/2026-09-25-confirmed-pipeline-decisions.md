# Confirmed pipeline decisions

Date: 2026-09-25
Status: Consolidated after the user's decision-by-decision review. Authoring only;
runtime implementation and remote provisioning have not started.

This record supersedes conflicting recommendations in the earlier 28-task draft.
The temporary log preserved decisions during discussion; permanent documents were
updated together after all material choices were resolved. Interface names,
fixture choices and schema details are implementation design, not additional
claims of user approval. The top-100 discovery interpretation is query-scoped,
not a promise to audit all popular repositories now.

## Confirmed decisions

### 1. Shared architecture

One deterministic engine with Codex/OpenCode adapters and a version-pinned
project harness. Accepted when the user said “proceed” to that architecture.
This acceptance did not confirm every recommendation in the later roadmap.

### 2. Canonical documentation

User selected option 1: one canonical README.md for installation, operation,
current architecture and rules. Migrate useful content and consumers before
retiring root CONTEXT.md and README-LLM.md. Detailed history remains in linked
ADRs/specs.

### 3. Coder autonomy and independent review

User selected option 1: coder owns RED/GREEN without a separate RED approval;
independent review occurs per task. Straightforward review corrections return
directly to the coder; the director handles scope or architecture changes.
Script-run verification remains mandatory.

### 4. Repeated coder attempts

User selected option 1: use a configurable attempt limit. At the limit, the
director assesses the blocker; unresolved problems pause the run.
Latest confirmed policy: at most three coder/director cycles per unresolved task
episode. The first cycle allows five coder invocations (including initial
implementation); the second and third allow three invocations each. Return to
the director when a cycle exhausts its allowance without resolution. This is at
most eleven coder invocations. After the third exhausted cycle and its director
assessment, pause for the user; do not automatically start a fourth cycle.
Pause earlier if the director cannot resolve the blocker. Successful completion
ends the episode without consuming the remaining allowance.
The limits remain configurable per the earlier policy choice. Internal RED/GREEN
iterations within an invocation do not count separately. This supersedes both
the uniform five-attempt and uniform three-attempt interpretations.

### 5. Testing policy

User selected option 1 (repeated messages confirm the same choice): affected
tests per task, including dependent components and relevant integration checks;
broaden verification up to the full suite when impact is uncertain. Run the
complete suite at closing. Tests for directly touched files alone are insufficient.

### 6. Installed pipeline synchronization

User selected option 1: automatically update when the installation is clean
and strictly behind its configured upstream. Show the diff summary, validate
the candidate version, and preserve existing project version pins. Preserve
local changes and divergent history; ask the user to resolve them. No force
pull/reset or automatic resolution of divergence. This supersedes the draft
requirement for explicit --apply on every clean fast-forward update.

### 7. Model selection

User selected option 1: ask at each new implementation run, offering saved
choices. Confirm operator and reviewer models; the director uses the reviewer
model unless the user chooses otherwise. Resuming the same run reuses its
confirmed configuration without asking again. Never hard-code model identities
or silently inherit the interactive session's model.

### 8. Project harness initialization

User selected option 1: initialize automatically on first pipeline use in a
project. Add a small version-pinned project configuration and merge a managed
entry into AGENTS.md while preserving existing instructions. Initialization
must be idempotent and limited to the project in use; it does not scan or
modify unrelated projects. This supersedes the draft requirement to explicitly
enroll each existing project before first use.

### 9. Project harness upgrades

User selected option 1: when a newer validated harness version is available,
offer the upgrade before the project's next run and show the changes. Update
the project pin only if the user accepts. Active runs retain their original
version. Installation updates do not automatically change project pins.

### 10. Skill discovery and reusable source registry

User selected option 1: search installed skills first; search external sources
when relevant coverage is missing; ask before installing external skills.
User additionally requested defining and saving good skill sources so discovery
does not repeatedly start from scratch. Suggested discovery: GitHub's top 100
most-starred relevant skill repositories and awesome-skills-style catalogs.

Implementation interpretation of the user's discovery suggestion: rank relevant skill repositories,
not the top 100 repositories across all of GitHub. Stars aid discovery but do
not establish individual skill quality, compatibility or trust. Keep source
identity, category, last-check date, revision, review status and useful skill
metadata in a reusable registry.

User selected refresh option 1: refresh when the registry is needed and its last
refresh is at least 30 days old. Reuse cached results between refreshes; search
further when coverage is missing. This does not schedule background refreshes.

Initial sources found through web research (candidates, not approved installation
sources or a verified top-100 ranking):

- https://github.com/anthropics/skills — publisher-maintained skill collection.
- https://github.com/VoltAgent/awesome-agent-skills — discovery catalog linking
  official and community skills; evaluate the linked source separately.
- https://github.com/vercel-labs/skills — discovery/installation tooling.
- https://www.skills.sh/docs — documentation for the associated skill directory.

No skills were installed and no full top-100 inventory was collected during
brainstorming. Discovery breadth is query-scoped and must be reported honestly.

### 11. Baseline product requirements

User selected option 1: apply relevant defaults (for example form validation,
input masks, accessibility and loading/error states) and present one consolidated
summary during brainstorming. Ask only about ambiguous choices or exceptions;
do not require approval of every individual default or apply requirements silently.
Applicability remains tied to the project context; do not add unrelated features.

### 12. Reusable template storage

User selected option 1: store reusable templates in a separate private GitHub
repository, with versioned assets shared across projects independently of the
pipeline release lifecycle. User subsequently named the repository
CarlosMonteiroNeto/code-templates; visibility remains private. No remote
repository is created during this brainstorming review.

### 13. Reusable asset promotion

User selected option 1: after successful use in a project, propose reusable
assets and prepare the reusable version, tests, dependency constraints and
provenance for review. Publish to the shared template repository only after
the user's approval. Successful use nominates an asset; it does not authorize
automatic publication.

### 14. Defer brainstorming-entry classification

User removed the proposed Jev brainstorming-entry classifier from current
implementation scope. At the final consolidated update, place it at the end
of the roadmap as a possible future investigation, explicitly comparing other
options before choosing a solution. Do not retain R6 as an active implementation
round; mark its existing plan deferred/superseded rather than executable.
This decision concerns the proposed new entry classifier, not removal of existing
Jev Sites 1–5. No classifier/provider choice or activation policy is approved.

### 15. Adapt original Superpowers prompts

User selected option 1: preserve useful upstream guidance in concise role
headers, including TDD, self-review, review criteria and escalation. Replace
interactive coordination with script-controlled behavior. Do not paste complete
prompts indiscriminately or reduce upstream guidance to an untraceable rewrite.
Use the relevant source instructions as the basis for the adaptation.

### 16. Backend selection

User selected option 1: choose one backend per run. Either Codex or OpenCode
can execute the whole pipeline; operator, reviewer and director all use that
run's selected backend. Mixed-backend roles are outside current scope.

### 17. Publication policy

User selected option 1: at launch, ask whether the run should finish locally
or push and create a pull request after required final tests and independent
review pass. Persist that choice for the run; do not ask for the same permission
again at closing. No automatic merge. This replaces the draft's unconfirmed
local-only default with an explicit launch-time choice.

### 18. Concurrency

User selected option 3: ask for the concurrency limit at each new run's launch
and persist it in the run configuration. Do not silently apply the draft's
default of two workers. Parallel tasks use isolated worktrees; dependencies,
overlapping writes and shared resources constrain scheduling regardless of
the chosen limit. Resuming a run retains its recorded limit unless explicitly
reconfigured.

### 19. Generalize capabilities confined to Flutter

The user clarified that the concern is generally useful behavior running only
inside flutter-app-pipeline instead of the shared two-model pipeline; this is
not a request to expand supported programming languages.

User selected option 1: audit every Flutter stage and generalize applicable
capabilities. Record each disposition as shared, Flutter-specific, or requiring
adaptation. Preserve genuinely Flutter-specific commands and provider details.
Research, template discovery, reuse tracking, requirements and skill selection
are candidates to inspect, not an exhaustive or already-proven migration list.
Do not turn a second-ecosystem validation fixture into an unrequested language
support deliverable. The final plans must cover the full stage audit rather
than only the previously selected catalog/template components.

### 20. Template adoption

User selected option 2: automatically reuse a suitable template when
compatibility checks pass. Ask only when changes or conflicts require judgment.
This supersedes requiring a separate as-is/adapt/from-scratch choice for every
compatible candidate. Compatibility must cover approved requirements and the
project's technical constraints; a popularity/quality score alone is not proof
of compatibility. This adoption policy does not change the separate requirement
for user approval before publishing newly promoted reusable assets.

### 21. Session and diagnostic retention

User selected option 1: retain completed worker sessions and diagnostic evidence
for a configurable period so they remain available for debugging, then clean up
only resources owned by that run. Never remove unrelated sessions or evidence.
User subsequently selected a default retention period of 30 days after
completion, configurable. Active and unresolved runs remain protected from
automatic cleanup. Cleanup must respect each backend's supported lifecycle
capabilities; this choice does not authorize direct manipulation of provider
databases or removal of active-run resources.

### 22. Unplanned files and coder write scope

User selected option 1: allow related new files; require director approval
before modifying undeclared existing files. Scripts check protected paths and
parallel-task conflicts before granting access. Record newly granted paths as
owned resources so concurrent workers cannot acquire the same path. Do not
silently treat task touches as an unrestricted project-wide write grant.
This supersedes the draft's absolute restriction to originally declared files.

### 23. Dependencies discovered during implementation

User selected option 2: allow new dependencies when compatibility and license
checks pass; ask only about conflicts or exceptions. Do not require separate
user approval solely because a dependency was not listed during planning.
Record the dependency decision and resolved version in run evidence. This
does not override decision 22: changes to undeclared existing manifests or
lockfiles still require director-approved write scope and script-controlled
coordination of shared resources. Unknown compatibility or license status is
an exception, not an automatic pass.

### 24. Pre-existing test failures

User selected option 1: distinguish pre-existing baseline failures from new
regressions using recorded baseline evidence. Continue unaffected work and
report the baseline failures. If they remain at closing, require an explicit
user waiver before final completion; do not silently declare a green suite.
New regressions remain blockers. Do not automatically expand scope to repair
unrelated baseline defects. An unclassified failure is not presumed pre-existing.


## Decision-to-task coverage

| Decision | Requirement | Active task coverage |
|---|---|---|
| 1, 16 | Shared engine; one backend per run | R1.2–3, R2.4–6, R3.5–7 |
| 2 | One canonical README | R1.4; documentation tasks in each later round |
| 3, 15 | Coder RED/GREEN; independent review; adapted prompts | R2.3–4, R3.2, R4.1 |
| 4 | Three cycles, coder allowances 5/3/3 | R1.2, R3.3, R4.1, R4.5 |
| 5 | Affected tests and full closing suites | R4.2–4 |
| 6, 8, 9 | Safe auto-update; automatic enrollment; opt-in project upgrade | R1.1, R1.4, R3.5 |
| 7, 17, 18 | Launch-time models/publication/concurrency | R1.2, R3.5 |
| 10 | Installed-first skills; reusable registry; 30-day refresh | R2.2–3, R5.7 |
| 11 | Consolidated applicable baseline requirements | R5.4, R5.7 |
| 12, 13 | Private code-templates; approved promotion | R5.5 |
| 14 | Defer new Jev classifier | R6 disabled; roadmap future investigation |
| 19 | Audit every Flutter stage and generalize applicable behavior | R5.1–7 |
| 20, 23 | Automatic compatible adoption/dependencies | R5.6–7; R3.1, R3.3 for scope |
| 21 | 30-day completed-run retention | R1.2, R2.5, R3.1 |
| 22 | Related new files and director-approved existing-file changes | R2.4, R3.1, R3.3, R4.1 |
| 24 | Baseline evidence, continuation and explicit waiver | R4.3–4; R3.4 integration |

## Task-by-task reconciliation

### R1

- **R1.1 — Make harness synchronization non-destructive:** Replace reset-based synchronization with inspected fast-forward-only updates and explicit divergence reports.
- **R1.2 — Define shared runtime configuration and backend capability reports:** Add a backend-neutral manifest and model-selection handoff with read-only adapter capability probes.
- **R1.3 — Define shared invocation and semantic result schemas:** Specify normalized request/result contracts without implementing paid worker dispatch.
- **R1.4 — Install immutable harness versions and bind projects with canonical documentation:** Package a complete harness and add safe project initialization while consolidating duplicated documentation.
### R2

- **R2.1 — Build complete context packages and executable toolchain descriptors:** Make fresh workers self-sufficient by carrying global/task/spec/verification context and platform-correct scoped runner commands. Replace marker-only assumptions with executable toolchain contracts and support the repository's unittest evidence.
- **R2.2 — Build reusable skill-source discovery and refresh:** Persist vetted discovery sources and cached skill metadata so planning does not repeatedly search from scratch.
- **R2.3 — Resolve pinned task skills and adapted upstream prompt headers:** Preserve upstream role practices through versioned adaptation and deterministic prompt assembly.
- **R2.4 — Enforce separate Codex and OpenCode role policies:** Create packaged Codex role prompts and deterministic command/edit guards reflecting the operator, reviewer and director boundaries. Verify hook/tool coverage and sandbox prerequisites before permitting runtime dispatch.
- **R2.5 — Implement both backend adapters with shared session lifecycle:** Add the direct subprocess Codex backend, immutable attempt evidence, explicit-ID continuation and classified failures. Keep the public dispatch seam and retain OpenCode as an explicit separate backend.
- **R2.6 — Ship and verify worker runtime contracts for both backends:** Integrate runtime artifacts into both package routes and document capability evidence without claiming a complete pipeline.
### R3

- **R3.1 — Isolate runs, worktrees and shared state with durable ownership:** Introduce canonical run/plan identities, scoped worktree ownership, strict plan validation and evidence-preserving integration. Repair cross-plan collisions and mixed-toolchain gate propagation while retaining the current deterministic scheduler.
- **R3.2 — Wire normalized outcomes into RED, GREEN and independent review:** Adapt every generic and Flutter gate path to the new outcomes, with durable candidate identity and explicit review-pending recovery. Stop parsing OpenCode events on the Codex path and stop swallowing reviewer launch failures.
- **R3.3 — Apply director proposals through canonical script transactions:** Change Codex correction/arbitration from model edits into validated proposals applied by one canonical plan writer. Preserve task-family continuation and reconcile plan commits, ledger events and snapshots after interruption.
- **R3.4 — Require a candidate-bound closing verdict and branch-wide verification:** Create the closing coordinator and verification barrier. Final approval must explicitly cover the current plan, spec, ledger and Git candidate; rejection reopens work or blocks instead of allowing publication.
- **R3.5 — Connect the complete Codex launcher, cancellation and explicit publication:** Wire the shared pipeline state machine to the Codex configuration, direct worker backend, canonical plan writer, isolated waves and strict closing. Add durable run control and a Windows launcher without requiring an interactive model in the runtime loop.
- **R3.6 — Ship the Codex workflow through skills, documentation and both package paths:** Update the user and agent entry instructions for the complete Codex path, include all runtime references in distribution, and reconcile stale claims with the implemented behavior. Preserve explicit legacy OpenCode guidance.
- **R3.7 — Prove the complete adaptation with an acceptance harness and support matrix:** Provide deterministic end-to-end scenarios and opt-in live Codex acceptance so compatibility claims can be tied to actual role configuration, sandbox behavior, recovery and distribution. Record every audit finding's implementation and verification evidence.
### R4

- **R4.1 — Centralize correction routing and enforce dispatch budgets:** Remove unnecessary director hops while preserving independent semantic review and bounded recovery.
- **R4.2 — Build evidence-bound affected-test selection:** Compute tests from actual changes and dependency impact with conservative fallback.
- **R4.3 — Record baseline failures and explicit closing waivers:** Distinguish inherited failures from new regressions without silently relaxing completion.
- **R4.4 — Apply impact gates at task, integration and closing boundaries:** Wire selective verification without weakening final full-suite requirements.
- **R4.5 — Add dispatch-cost audits, documentation and acceptance:** Strengthen skill-scripter and quantify execution cost without claiming savings from call counts alone.
### R5

- **R5.1 — Audit every Flutter phase and assign shared capability ownership:** Create an exhaustive source-backed disposition matrix before moving implementation.
- **R5.2 — Extract generic catalog and adoption contracts from Flutter:** Preserve evidence and provenance while introducing ecosystem-neutral persistence.
- **R5.3 — Generalize deterministic recall and template refresh:** Move shared recall orchestration while keeping provider scoring and evidence adapters specific.
- **R5.4 — Introduce applicable baseline requirement profiles:** Make structural product requirements explicit during planning without adding irrelevant features.
- **R5.5 — Build safe template repository and promotion workflows:** Package reviewed reusable assets with explicit repository configuration and publication authority.
- **R5.6 — Generalize research, dependency preparation and compatible adoption:** Expose generally useful Flutter-only lifecycle behavior through shared contracts and preserve ecosystem-specific implementation.
- **R5.7 — Integrate reuse into planning and prove ecosystem compatibility:** Wire profiles, recall and promotion into skills and packaging without per-task inference overhead.
## Deferred scope

R6 has no executable tasks. Its three earlier tasks remain under
`deferred_task_reference` solely as historical input for a future comparison.
Existing Jev Sites 1–5 are not removed. The old twelve-task transition-backlog
also remains non-executable historical material.
