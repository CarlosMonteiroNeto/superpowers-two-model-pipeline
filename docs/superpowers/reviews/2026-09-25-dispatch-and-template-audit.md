# Dispatch and template audit

Date: 2026-09-25. Source baseline: main at 596951fa, plus planning documents.
Read-only source inspection; archive content was not executed or installed.

## Dispatch sites: individual dispositions

Paths below are relative to `skills/two-model-sdd-pipeline/scripts/` unless stated.

| Site | Current purpose | Decision | Reason and destination |
|---|---|---|---|
| `red-gate:104` | Initial operator | Keep | Implementation is semantic; one session owns RED/GREEN and self-review |
| Flutter `scripts/red-gate` | Delegates generic red gate | Keep shim | Already shares ownership; not an extra model call |
| `coder-gate:382` | Resume operator after gate failure | Keep conditionally, bound | New actionable evidence warrants correction; never retry infrastructure failure as code failure |
| `coder-gate:386` | Fresh operator when session absent | Restrict | Require explicit recorded context-reset recovery; never silently lose task context |
| `coder-gate:325` | Reviewer after green/commit | Keep semantic call, centralize ownership | Independent acceptance/quality judgment cannot be replaced by green tests |
| Flutter `scripts/green-gate:147` | Reviewer after Flutter green | Remove duplicate ownership | Delegate to the same shared review dispatch boundary; preserve one review |
| `task-run:86`, called at `:270` | Director for every CORRECTIVE | Remove for validated in-scope findings | Send findings directly to operator; director only when acceptance/scope/interfaces/viability change or ambiguity remains |
| `task-run:293` | Resume operator for corrective task | Consolidate | Shared correction runner owns same-family resume and evidence lifecycle |
| `task-run:298` | Fresh corrective operator fallback | Restrict/consolidate | Explicit context-reset policy; no unconditional fresh retry |
| `task-run:86`, called at `:339` | Director arbitration | Keep and bound | Viability/scope disputes require judgment; recorded [5,3,3] coder-cycle budget; pause after third exhausted cycle or earlier unresolved ruling |
| `run-pipeline:191` | Branch closing director | Keep once per candidate | Cross-task semantic review; parse explicit verdict before finalization |
| `dispatch-retry:55` | Transport-level re-invocation | Keep only classified retry | Known pre-start transient failures only; ambiguous post-start outcomes require recovery |
| `dispatch` | OpenCode process launch and event capture | Replace with adapter delegation | Retain actual semantic work, normalize runtime-specific transport |
| `orchestrator` | Script routing to gates | Keep zero-model router | No new agent to interpret deterministic outcomes |
| `director-prompt` / Site 3 | Optional Jev guidance before director | Keep optional; only if director needed | Skipping a director must also skip its guidance request |
| `review-package` / Site 4 | Optional Jev reviewer guidance | Keep optional, measure | Does not approve or replace review; avoid adding another reviewer |
| Sites 1/2/5 catalog/recall/fusion | Optional planning inference | Keep outside task execution | Cache and budget explicitly; deterministic catalog work has no model call |
| New brainstorming site | Intent guidance | Removed from active scope; R6 non-executable | Future investigation must compare alternatives; no provider/activation policy selected |

No dispatch exists solely for independent RED approval in the inspected path.
The operator already declares expected failure; scripts check its form and the
reviewer independently assesses its meaning. Do not remove those distinct checks.

## Cost and loop audit requirements

Normal completed task targets one operator plus one reviewer invocation. Closing
adds one branch-level invocation. Count local worker model turns, transport
attempts, resumed corrections and Jev calls separately. Record actual usage where
the backend exposes it; unavailable usage is unknown, not zero.

Current coder retries are unbounded. R4 replaces them with configurable [5,3,3]
invocation allowances: director assessment after each exhausted cycle, at most
eleven coder invocations, then pause if unresolved. Internal RED/GREEN iterations
are not separate invocations. Preserve counts across crash recovery and corrective
child tasks; pause earlier if director cannot resolve the blocker. Router state must change on each correction/ruling; no loop may reuse
a stale verdict as new evidence. Reviewer transport failure leaves review pending.

The future skill-scripter audit must also inspect agent-internal delegation and
dynamic/backend call sites; grep alone cannot prove no hidden calls. Its required
output includes keep/remove/merge for each site and quality/cost acceptance.

## Attached archive: reconciliation

Archive: `1-flutter-template-graph.zip` (user attachment), design dated 2026-09-15.
It contains design/wiring docs, five script families and tests. It does not contain
Flutter form widgets, masks or a product starter application.

| Archive content | Current repository | Disposition |
|---|---|---|
| catalog/embedding/recall/refresh wrappers and Python modules | Corresponding script files exist and differ byte-for-byte | Compare contracts and migrate useful gaps; never overwrite current implementation |
| `promote-to-package`, `template_promote.py` | Absent in current Flutter scripts | Design a reviewed promotion workflow in R5; adapt, do not import blindly |
| Archive tests | Test files accompany the archive | Port relevant cases after contract comparison; archive claims of 27 passing tests were not rerun here |
| WIRING promotion after two adoptions vs design after one | Contradictory archive guidance | One adoption nominates; explicit quality/license/API review authorizes promotion |
| CLI examples/exit codes | Current evidence-aware catalog has evolved | Current contracts remain authoritative until an explicit migration lands |
| Embedding model and SDK assumptions | Optional capability | Pin/validate provider and vector identity; no mandatory embedding dependency for deterministic recall |
| Package scaffold with dependency TODO values | Not release-ready | Require real dependency constraints and verification before publishing |
| Graphify references | Earlier pipeline design | Do not reintroduce a mandatory knowledge-graph stage from stale documentation |

The present repository adds evidence hashes, derived-field invalidation, advisory
policy boundaries and vector provenance checks. Preserve these when generalizing.
Keep reusable source manifests in Git and mutable local catalog/index data outside
Git. Requirements profiles for forms and application behavior are new R5 work.

## Upstream source reconciliation

Read the current upstream implementer and TDD prompts as design references; pin a
specific upstream commit during R2 before vendoring. Preserve self-review and
meaningful observed RED. Adapt worker-owned commits to Script CEO and adapt
pre-commit full-suite language only when the verified impact policy ships.

- [Implementer prompt](https://raw.githubusercontent.com/obra/superpowers/main/skills/subagent-driven-development/implementer-prompt.md)
- [TDD skill](https://raw.githubusercontent.com/obra/superpowers/main/skills/test-driven-development/SKILL.md)

These mutable URLs establish research provenance, not runtime dependencies.

## Confirmed policy reconciliation

The [decision record](../specs/2026-09-25-confirmed-pipeline-decisions.md) supersedes
unconfirmed audit defaults. Retain independent task review, directly return in-scope
corrections, grant related new paths under script ownership, and use explicit
user waivers only for proven baseline failures. Template adoption is automatic
when compatibility passes; publishing a promoted asset still requires approval.
The full Flutter-stage audit/generalization is R5 scope, not new language support.
