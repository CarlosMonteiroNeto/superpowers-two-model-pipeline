# Shared Pipeline Roadmap

Date: 2026-09-25
Status: Consolidated confirmed design; implementation has not started.

## 1. Purpose and authority

Build one deterministic pipeline with Codex/OpenCode adapters, installed per agent
and pinned per project. One backend serves every role within a run. Scripts own
orchestration; workers perform semantic implementation and independent review.
Communication and planning artifacts are English.

The [confirmed decision record](docs/superpowers/specs/2026-09-25-confirmed-pipeline-decisions.md) preserves all 24 decisions and
maps them to tasks. It supersedes conflicting draft recommendations. The
[transition spec](docs/superpowers/specs/2026-09-25-codex-pipeline-design.md)
defines contracts. Do not treat implementation detail as a new user requirement.

All active rounds have complete plans authored now, not deferred planning work.
Before execution check predecessor acceptance and source/interface drift. No
runtime director silently expands this roadmap. The authoring task does not
create a remote repository, publish assets or start implementation.

## 2. Decisions

### D01 — One engine, two adapters

Share scheduling, ledger, task schemas, verification, context and closing.
Adapters own runtime settings, permissions, events, launch/resume/cancel and
session lifecycle. Select one backend per run; no mixed roles or silent fallback.
Separate engines and a Codex-only rewrite were rejected to avoid duplicated policy.

### D02 — One canonical README.md (user confirmed)

README.md owns installation, operation, architecture, current rules and glossary.
Migrate useful content and active consumers before retiring root CONTEXT.md and
README-LLM.md in R1. Link detailed ADRs/specs instead of duplicating them.
README.txt may remain only as a format compatibility entry without authored rules.
Later rounds never recreate the retired documents.

### D03 — Safe synchronization and project pinning

Automatically update a clean installation strictly behind its configured upstream,
after showing a diff summary and validating the candidate. Equal is a no-op;
dirty, divergent, ahead, unexpected detached state or mismatched remote preserves
all work and requires user resolution. No reset, force-pull, clean, stash or
automatic divergence merge. Inspection failures block mutation.
Managed bundles switch atomically only after validation; preserve usable versions
and active runs. Installation updates never silently change project pins.

### D04 — One brainstorming authorization boundary

Resolve material choices through questions and alternatives. After scope approval,
write spec and plan without another written-spec checkpoint. Ask again only for
material new scope or unresolved ambiguity. Keep decisions persisted during
discussion and consolidate permanent artifacts after the agreed review.

### D05 — Model selection before implementation

At each new run confirm backend and operator/reviewer models, offering saved
choices; director uses reviewer model unless overridden. No hard-coded model.
Also ask local-only versus push-and-PR publication and concurrency. Persist all
choices; resume does not ask again. Headless launch requires confirmed configuration.
No automatic merge or repeated closing permission request for already authorized
publication. Baseline-failure waivers remain a separate explicit decision.

### D06 — Installed harness with a small project binding

Initialize automatically on first pipeline use, only in that project:
.superpowers/harness.json plus an idempotent managed AGENTS.md entry preserving
user instructions. Resolve an immutable installed bundle, not a copied full engine.
Before a later new run offer newer validated versions with a diff; update the pin
only on acceptance. Active runs keep their original bundle.

### D07 — Reuse upstream prompts through an explicit adaptation layer

Use concise relevant role headers derived from pinned upstream guidance, retaining
TDD, self-review, review criteria and escalation. Replace worker coordination,
commits and delegation with script protocols. Record provenance, hashes and
intentional deviations. Do not paste all skills or silently truncate required rules.
Adapt upstream full-suite language only when the affected-test policy is proven.

### D08 — Coder autonomy without self-approval of delivery

Coder owns RED/GREEN and self-review; no separate RED approval dispatch.
Independent semantic review occurs for every task. Straightforward corrections
return directly to coder; director handles structural scope/architecture changes.
Related new files receive script-controlled path grants; undeclared existing-file
edits need director approval. Lock ownership and reject protected or conflicting
paths before granting access. Do not weaken tests to manufacture green evidence.

### D09 — Dispatch only at semantic boundaries

Default coder invocation allowances per unresolved task episode are **[5,3,3]**.
After each exhausted cycle return to director; after the third assessment pause
if unresolved, or pause earlier if director cannot resolve it. Maximum eleven
coder invocations. Internal RED/GREEN turns are not separate attempts. Preserve
budgets across crashes and corrective child tasks; scope changes do not reset them.
Known pre-start transport failures are accounted separately; reconcile ambiguous
post-start work instead of blindly replaying it.
skill-scripter inventories every call site and its reason, cost, duplicate owner,
budget and termination. Measure tokens/latency/quality, not call counts alone.
Jev Site 3 is consulted only when a director is actually required.

### D10 — Affected tests per task, complete suite at closing

Select tests from actual changes, dependent consumers/contracts and integration
impact. Include renames/deletions and relevant configuration. Unknown/stale impact
or missing coverage broadens verification up to the full suite; no match is not
success. Integration recomputes impact for the merged candidate.
Run complete configured suites at closing. Identical tree/environment/commands
may reuse valid evidence; changes invalidate it. New regressions block completion.
Record pre-existing failures from baseline evidence, continue unaffected work,
and report them. Remaining baseline failures require an explicit candidate-bound
user waiver at closing; waived completion is never reported as green.
Keep conservative gates until R4 is accepted; supersede historical retry/testing
ADRs explicitly when the new policy lands.

### D11 — Generic capabilities, ecosystem adapters

Audit every Flutter phase and script, recording shared, Flutter-specific or
adaptation-required disposition. Generalize applicable behavior across requirements,
research, templates, dependency preparation and delivery, not only catalog code.
Already-shared gates remain shared. pub.dev scoring and Flutter/Dart/UI specifics
remain adapters. This is not a new language-support project; generic fixtures
validate abstractions without claiming production support for new ecosystems.

### D12 — Skill discovery per task

Search installed skills first; search external sources for missing coverage.
Persist a source registry with identities, categories, revisions, review status
and check timestamps. Seed publisher repositories and awesome-style catalogs;
query up to 100 most-starred relevant skill repositories with recorded scope,
deduplication and freshness. Stars aid discovery, not trust or compatibility.
Refresh on demand after 30 days; reuse cache between refreshes and search further
for missing coverage. No background schedule. Preserve stale data with explicit
status if refresh fails. Ask before external skill installation.
Planning selects relevant skills; scripts resolve/pin them without another paid
selector per task. Full top-100 collection is future implementation, not completed
research claimed by these documents.

### D13 — Baseline requirements are profiles, not unconditional features

Apply relevant defaults and show one consolidated brainstorming summary. Ask only
about ambiguity/exceptions. Profiles cover normalization/masks, validation,
accessibility, loading/empty/error states, duplicate submits, safe retries,
locale/date/currency and secret-safe logging where applicable. Masks do not replace
validation; do not add irrelevant country-specific or product functionality.

### D14 — Versioned reusable-template repository

Use the separate **private CarlosMonteiroNeto/code-templates** repository.
Store reviewed source, profiles, packages, manifests, provenance, license notices,
compatibility and tests in versioned releases. Keep mutable SQLite/vector caches,
credentials and private project evidence outside Git.
Automatically reuse a suitable template when requirements and technical
compatibility pass; ask for changes/conflicts needing judgment. Quality score
alone is insufficient. Compatible, license-approved new dependencies may be
added without another user approval, while undeclared existing manifests and
lockfiles retain director scope and write-lock controls.
Successful project use nominates an asset for promotion. Prepare reusable source,
tests, dependencies and provenance, then publish only after user approval.
Do not import the ZIP over newer code or release dependency TODO scaffolds.

### D16 — Retention and evidence

Retain completed sessions and evidence for 30 days by default, configurable.
Protect active/unresolved runs. Cleanup only run-owned resources using supported
backend lifecycle operations; never edit provider databases. Unsupported remote
cleanup is reported rather than faked. Export evidence before releasing worktrees.

## 3. Implementation rounds

| Round | Ordered deliverable | Depends on | Exit evidence |
|---|---|---|---|
| R1 | Safe updates; shared config/contracts; installation and documentation | Reviewed baseline | Non-destructive update fixtures; preserved instructions/pins; honest capability reports |
| R2 | Context; source registry; adapted prompts; role guards; adapters; packaged workers | R1 | Both backend fixtures; retention/policy checks; opt-in live evidence |
| R3 | Identity/scope grants; gates; director transactions; closing; launch choices; distribution/acceptance | R2 | Serial/parallel recovery and strict closing; integration milestone |
| R4 | Direct corrections and 5/3/3 budgets; impact selection; baseline waivers; wired gates; cost audit | R3 | Confirmed operational policies enforced; required final suites |
| R5 | Full Flutter audit; generic catalog/recall/profiles; template repository; shared research/adoption/dependencies; planning integration | R4 | Every stage disposition implemented or specialized; compatibility and migration evidence |

R3 is an integration milestone, not permission to adopt unbounded retries in
production. R4 must pass before unattended production use of the redesigned flow.
Every round includes documentation, packaging and regression work. Implementation
uses a pinned supervisor outside worker edits. Existing runtime remains unchanged
during planning.

### Complete machine plans

| Round | Plan | Active tasks |
|---|---|---:|
| R1 | [Round 1: safe shared harness foundation](docs/superpowers/plans/2026-09-25-codex-pipeline/plan.json) | 4 |
| R2 | [Worker runtime, prompts and backend adapters](docs/superpowers/plans/2026-09-25-r2-worker-runtime/plan.json) | 6 |
| R3 | [Shared pipeline integration and acceptance](docs/superpowers/plans/2026-09-25-r3-pipeline-integration/plan.json) | 7 |
| R4 | [Bounded dispatch and affected verification](docs/superpowers/plans/2026-09-25-r4-execution-efficiency/plan.json) | 5 |
| R5 | [Generic reuse, requirement profiles and templates](docs/superpowers/plans/2026-09-25-r5-reuse-foundation/plan.json) | 7 |

**29 active tasks across five rounds.** The old R6 plan has zero active tasks and
three historical task references; it is explicitly non-executable.
The original twelve-task transition-backlog remains non-executable historical input.
Task IDs are local to a round; prerequisite acceptance orders shared file edits
between rounds. Source drift checks refine interfaces, not reopen confirmed choices.

## 4. Review evidence and traceability

- [Confirmed decisions and task coverage](docs/superpowers/specs/2026-09-25-confirmed-pipeline-decisions.md)
- [Original C01–C20 compatibility review](docs/superpowers/reviews/2026-09-25-codex-pipeline-review.md)
- [Dispatch and archive reconciliation](docs/superpowers/reviews/2026-09-25-dispatch-and-template-audit.md)

The ZIP contains recall/catalog/promotion tooling, not form widgets. Current
catalog code differs from it and includes newer provenance controls. R5 must
preserve those controls. Audit all actual call sites again after R3 changes.
No new code/tests/runtime workers or remote repository were executed/created
during this authoring task.

## 5. Possible future investigation

### D15 — Jev at brainstorming entry

**Deferred at the user's request.** Investigate whether entry classification adds
value and compare alternatives before selecting a solution: existing interactive
classification, deterministic hints, Jev or another classifier. No provider or
activation policy is approved. The [old R6 plan](docs/superpowers/plans/2026-09-25-r6-brainstorming-advisory/plan.json)
is reference-only and must not run. This deferral does not remove existing Jev
Sites 1–5.
