# Shared pipeline transition with Codex and OpenCode adapters

Date: 2026-09-25
Status: Consolidated user-confirmed design; five active rounds; implementation not started.
Baseline: `596951fa0da14b0010998c29c2810bff4f2e8b02` on `main`.
Review: [complete stage audit](../reviews/2026-09-25-codex-pipeline-review.md).
Plan: [plan.json](../plans/2026-09-25-codex-pipeline/plan.json).

Roadmap: [cross-round design](../../../roadmap.md). The current plan covers
Round 1 only. Sections 1–14 retain the detailed runtime target; section 15
defines updated shared-backend scope, precedence and delivery boundaries.
The [confirmed decision record](2026-09-25-confirmed-pipeline-decisions.md)
supersedes earlier unconfirmed recommendations; R6 is deferred.

## 1. Objective and scope

Provide a complete Codex execution path for the existing pipeline. A script
starts, observes, resumes, and stops the operator, reviewer, and director.
The interactive strategist supplies an approved spec and complete plan; its
model does not dispatch workers, inspect routing decisions, or keep the run
alive. Semantic work remains with the appropriate worker. Mechanical routing,
gates, commits, plan transactions, and lifecycle remain with Script CEO.

Category Skeleton, derived from the user's request, in order:

1. Generic category: developer tooling.
2. Specific category: deterministic orchestration of Codex and OpenCode coding agents.
3. Original implementations: two configurable model tiers; script-controlled
   dispatch and routing; independent semantic review; task-family session
   retention; plan/ledger recovery; isolated parallel worktrees.

This covers every stage identified in the review, including the Flutter
specialization, Jev boundaries, packaging, and delivery. It fixes inherited
defects where they would invalidate the Codex contract. It does not implement
a new product UI, a knowledge graph, a cloud execution service, or silent model
upgrades. New dependencies may be added when compatibility and license checks
pass; conflicts or unknown checks require clarification.

The existing OpenCode entry path stays available as an explicitly selected
backend. The Codex entry path never falls back to OpenCode. Sharing validated
mechanics is preferred over maintaining a second copy of the state machine.

## 2. Execution interface decision

Use `codex exec --json` with a Python standard-library subprocess supervisor
behind the existing dispatch boundary. Use explicit-ID `codex exec resume`
for permitted continuation. The installed CLI, `0.156.1`, documents stdin
prompts, `--output-schema`, `--output-last-message`, model selection, explicit
sandbox configuration, JSONL events, and those output options on resume.

The TypeScript SDK and current Python SDK are viable script-driven alternatives.
Direct App Server also supports thread/start, thread/resume, turn/start,
turn/interrupt, and thread/archive. They are not required for the current
process-oriented engine. An adapter boundary allows a later SDK implementation
without changing routing or semantic schemas. Do not use the removed
`codex mcp-server` interface or model-coordinated Agents SDK examples as the
execution mechanism.

The workers are independent Codex agent sessions. The design does not claim
that they appear as native subagents of the initiating desktop task. No public
external API establishing that relationship was verified. Native collaboration
tools in this conversation are not shell functions. The supervisor must not
simulate a model tool call or edit the Codex database to create parent links.

Example command shape, constructed as an argv array, with prompt bytes on stdin:

```text
codex [per-invocation config overrides] exec --model MODEL --json
  --output-schema SCHEMA --output-last-message FINAL -
codex [per-invocation config overrides] exec resume SESSION_ID
  --model MODEL --json --output-schema SCHEMA --output-last-message FINAL -
```

Set subprocess `cwd` to the recorded task worktree for both commands. Set
`sandbox_mode`, `approval_policy="never"`, `model_reasoning_effort`, role
developer instructions, and `features.multi_agent=false` through verified
per-invocation configuration. Never use `--last`. Never concatenate the prompt
into a shell command. A fresh start's success requires a new thread identity;
resume requires the recorded identity to match. Model/effort changes are an
explicit new execution configuration, not an accidental fallback.

## 3. Global constraints

- GC01: Script CEO owns dispatch, scheduling, gates, authoritative state, commits, and publication; no coordinating LLM is introduced.
- GC02: The Codex path never executes OpenCode or silently changes runtime, model, reasoning effort, or role.
- GC03: Every role receives explicit model and reasoning settings; operator, reviewer, and director have separate identities and permissions.
- GC04: Plans, specs, prompts, ledger summaries, and implementation comments are English; product UI copy retains its established locale.
- GC05: Codex workers inherit no brainstorming transcript; all required task context comes from versioned artifacts and explicit packages.
- GC06: Operator-owned RED/GREEN and independent semantic review remain mandatory; mechanical green alone never approves a task or branch.
- GC07: Raw evidence determines gates; RTK only changes the model-visible rendering and never the command exit code.
- GC08: Unknown, malformed, stale, interrupted, or mismatched results never advance authoritative state.
- GC09: Resume is confined to a recorded task family and role; unrelated tasks and closing use fresh contexts.
- GC10: Parallel workers use distinct worktrees; shared plan writes, integration, and publication are serialized by scripts.
- GC11: Existing user changes, unrelated branches, Codex sessions, credentials, and installed plugin caches are preserved.
- GC12: Jev remains optional advisory inference; it cannot dispatch, select a tier, approve, route, or write the authoritative ledger.
- GC13: Each new run confirms local-only or push-and-PR publication and concurrency at launch; resume retains those choices and no automatic merge is allowed.
- GC14: Compatibility is claimed only for runtime/platform/toolchain combinations backed by the acceptance matrix.

## 4. Installation, bootstrap, and preflight

Ship the runtime, schemas, role prompts, hooks, and orientation reference under
`skills/two-model-sdd-pipeline/` so the package is relocatable. Add a Codex
reference under `skills/using-superpowers/references/` and an entry script
`skills/two-model-sdd-pipeline/scripts/run-codex-pipeline`. Provide a companion
PowerShell launcher selecting Git Bash explicitly. The launcher uses argument
arrays, runs without a visible auxiliary console, and preserves exit codes.

Package orientation must resolve its own bundle root, not the target project's
root or a hard-coded OpenCode path. Include the harness reference in both Git
marketplace and portal artifacts and test references after extraction.
The currently installed Git bundle already contains root orientation files;
retain that working path while fixing portal packaging. Do not create/update
files inside the installed plugin cache at runtime.

`pipeline-doctor --config FILE --project DIR --output REPORT` is a read-only
capability check. It reports resolved native executable paths and versions,
Bash/Python/toolchain prerequisites, Codex auth readiness without secrets,
required CLI options, role settings, instruction/skill roots, hook readiness,
filesystem/network prerequisites, and source bundle revision. It exits 0 when
ready, 2 for invalid local configuration, and 3 for unavailable capabilities.
It dispatches only read-only backend capability probes; a Codex alias may exist.
It never installs software, resets a checkout, changes global Codex config,
executes a model, or guesses that a missing capability is supported.

Start the implementation compatibility matrix at CLI `0.156.1`, Python 3.10+,
and Bash 4+. Capability probes are authoritative; the observed local Python
is 3.12.10 and Bash is 5.3.15. Windows with Git Bash and Linux are initial
acceptance targets. macOS needs a modern Bash; WSL is a separate execution and
authentication environment requiring its own acceptance evidence. Desktop,
standalone CLI, and SDK versions must not be assumed identical.

The runtime config is a JSON object with `version: 1`, `backend: "codex"` or `"opencode"`,
`roles`, `toolchains`, `max_parallel`, `publication`, `retention`, and
`dispatch_timeout_seconds`. Each role requires an explicit model, backend-specific
effort/variant settings, policy and a packaged instruction identifier. Codex maps
operator policy to workspace-write and reviewer/director to read-only; OpenCode
uses its own verified policy representation. Examples contain no selected product
models. Ask the user before implementation launch, offer saved values for
confirmation at each new run, and persist that selection. Director defaults to
the confirmed reviewer model unless explicitly overridden. Also confirm concurrency
and local-only versus push-and-PR delivery. Resume retains the manifest. Headless
runs require confirmed configuration. Never infer a model from this document or
the chat. Default coder cycle allowances are [5,3,3], and completed-run retention
is 30 days; both are configurable. No silent concurrency/publication default.

Use existing supported Codex authentication. A CLI login is not evidence of
TypeSafe, Tavily, GitHub, or pub.dev credentials. Managed policy remains
authoritative. An unavailable model or noninteractive permission requirement
returns an actionable setup failure, without spending operator retries.

Persist an immutable run manifest binding config hash, bundle hash, executable
version/path, role hashes, repository identity, canonical plan path, run ID,
initial base commit, target branch, and publication policy. Refuse mixed bundle
versions in one run. Code-under-development cannot replace the supervisor of
the run implementing it; use a pinned runtime outside worker edits.

Pass the absolute manifest path through `PIPELINE_RUNTIME_MANIFEST`. Dispatch
selects the backend only from that validated manifest, with no executable-name
guessing or fallback. Existing internal role aliases such as `two-model-coder`
and its language variants map to the operator plus language context;
`two-model-reviewer` maps to reviewer and `task-generator` to director. Reject
unknown aliases. These are pipeline identifiers, never Codex `--agent` flags.

## 5. Planning, research, and context packaging

The strategist writes a complete machine plan using existing task fields:
`id`, `title`, `summary`, `spec_refs`, `touches`, `depends_on`, `acceptance`.
Keep `expected_red` absent. Preserve `spec_doc`, `global_constraints`,
`interfaces`, `verification`, and other documented metadata.

Validate initial plans and revisions with one shared validator: unique
consecutive positive integer IDs; complete nonempty fields; known, acyclic
dependencies; canonical repository-relative paths; no traversal or case alias
collisions on Windows; valid spec files/anchors; and executable runner
descriptors. Do not silently discard unknown extension fields; distinguish
preserved non-authoritative metadata from unsupported runtime controls.

Retain current `touches` compatibility: authored implementation files belong
there; newly authored tests are listed in `verification.new_test_files`.
Scheduling must include those test paths and other declared shared write
resources. A real shared implementation edit cannot disappear from scope just
because `depends_on` also orders the tasks. Explicitly declared existing-test
updates are limited to reviewed requirement changes, never automatic test
weakening after a failure. Add this permission to validation/scope policy
instead of an unrestricted test exemption.

For each invocation, `build_context` includes the task, exact global constraints,
interfaces, verification contract, cited spec sections, role instructions,
toolchain descriptor, task-family identity, changed-brief notice on resume,
allowed roots, and evidence paths. Review gets the full task diff including
tests plus mechanical gate evidence. Director gets complete plan, affected
task, cited constraints, and findings/escalation; closing gets plan, spec,
consolidated diff, ledger, and parked minors. Oversized required input fails
explicitly or is split into named complete files; it is never silently cut.

Resolve pipeline skill references against the pinned bundle and project
references against the selected worktree. Honor project `AGENTS.md` and managed
rules, report conflicting worker instructions, and never assume the desktop
conversation's tool list or skill context reaches a headless session. Worker
mode executes an already-approved task and skips generic startup planning,
self-update, tier questions, and interactive execution-choice loops.

Audit all Flutter stages and move generally useful requirements/research/adoption
behavior into shared contracts; keep pub.dev/Flutter scoring details in adapters.
Automatically reuse templates when requirements/technical compatibility pass;
ask only about changes/conflicts requiring judgment. Allow new dependencies with
passing compatibility/license evidence; unknowns are exceptions. Existing manifest
and lockfile writes still require approved scope/resource ownership.
Research uses configured sources; unavailable Tavily is explicit. Existing Jev
fusion stays planning-only with explicit selection. `pub get` can download package
code; never describe it as lockfile-only. Preflight approved network/cache effects.

Select relevant installed skills first; use a persisted source registry for gaps.
Refresh on demand after 30 days and retain query-scoped top-100 GitHub discovery
metadata without using stars as trust. External skill installation requires user
approval. Pin selected source/revision/sections; use concise adapted upstream role
headers, not full indiscriminate prompt copies. Baseline requirements are profiles:
apply relevant defaults, present one summary, ask about ambiguity/exceptions.

## 6. Role permissions and command execution

Translate intent from the OpenCode role files into packaged Codex role prompts
and runtime policy. Do not import their YAML permission structure as TOML or
assume a Codex `--agent` option exists.

| Role | Allowed work | Enforced runtime behavior |
|---|---|---|
| Operator | Write scoped code/tests; invoke declared RED/test/analyze/format runners | workspace-write; no delegation; no git commands or publication; protected plan/ledger/runtime files; scoped command guard |
| Reviewer | Inspect complete evidence and named-risk code; return structured verdict | read-only; no test/analyze/format commands, edits, delegation, or publication |
| Director | Produce corrective/arbitration/closing judgments as structured proposals | read-only; no edits, shell commands, git, delegation, or authoritative state writes |

Use documented `PreToolUse` command hooks for the supported local tool paths,
including unified exec and apply_patch. Normalize the verified Windows and
POSIX tool-input shapes. Reject unrecognized mutating commands and chained
shell commands rather than recognizing only a safe-looking prefix. Do not
reopen arbitrary execution through `bash -c`, PowerShell expressions, Python
`-c`, or a generic `cmd -- COMMAND` grant. Disable unneeded MCP/hosted tools
using supported configuration and keep required policy stricter than any
inherited permissive setting. Hook trust/setup is completed explicitly before
runtime; do not bypass hook trust automatically.

Codex documents hook coverage gaps. Thus hooks plus instructions are workflow
guards, not a complete security sandbox against adversarial project code.
The OS sandbox and integrity checks remain necessary. Validate native Windows
sandbox behavior before claiming permission parity; if the required policy
cannot be enforced on a target, preflight blocks that target.

Record protected Git/plan/ledger state before a worker and compare after it;
any unexpected mutation blocks before gate/commit. Workers cannot make their
own outcome or ledger authoritative. Script-created output files are read as
untrusted data and checked against the supervisor's invocation identity.

`scoped-run WORKSPACE TASK red|test|analyze|format [TEST_PATH...]` resolves an
approved toolchain descriptor, writes full output/evidence, and delegates
rendering to `cmd`. Arbitrary commands and out-of-root test paths are invalid.
Runner commands are argv arrays, with environment and cwd stored separately;
no `eval`, shell-word splitting, or hard-coded home paths. Add a Python unittest
evidence adapter for this repository's real suites alongside existing supported
formats. Unsupported Node/Rust runner evidence must fail preflight until an
explicit tested adapter is supplied; merely having a coder variant is not
support. A missing RED adapter is infrastructure failure, not a coder fix loop.

## 7. Dispatch result and event contracts

Each dispatch owns a new directory under `attempts/<task-family>/<role>/<id>/`
containing `request.json`, `prompt.md`, `events.jsonl`, `stderr.log`,
`final.json`, and supervisor-authored `result.json`. Files are UTF-8. Keep
stdout JSONL separate from stderr. The compact digest is observational and
cannot alter the result. File-write/stream capture failure blocks publication
of a successful result.

Normalized `result.json` version 1 contains:

```text
version, backend, run_id, dispatch_id, task_id, task_family, role, episode_id,
repository_id, worktree, plan_revision, base_commit, candidate_commit,
requested_model, requested_effort, runtime_version, config_hash,
session_id, resumed_from, process_exit, terminal_status,
output_schema, output_hash, final_output, usage, error
```

`terminal_status` is one of `completed`, `failed`, `interrupted`, `incomplete`.
`usage` contains reported input/cached/output token counts or null values when
unavailable. Do not equate requested settings with verified effective settings;
record any runtime-reported settings separately. Do not claim cache savings
merely because a session was resumed.

Consume `thread.started`, `turn.started`, `item.*`, `turn.completed`,
`turn.failed`, and `error` according to the installed CLI contract. Progress,
reasoning, tool output, and interim agent messages cannot be semantic verdicts.
The current attempt's final-output file is the candidate response; require
clean process termination, a consistent successful terminal event, the expected
thread identity, and strict final schema validation before accepting it.
Unknown informational event types are logged; unknown terminal behavior is
not accepted as success. A recoverable error event followed by valid completion
is distinct from a terminal failure.

All semantic schemas require their declared keys and forbid extra fields:

- Operator: `status` in DONE/DONE_WITH_CONCERNS/BLOCKED/NEEDS_CONTEXT/TEST_DEFECT,
  `summary`, `changed_files`, `red_evidence`, and `concerns`.
- Reviewer: `verdict` in APPROVED/SEND_BACK/ESCALATE, `findings`, `minors`,
  `summary`. Findings carry severity/file/line/issue/fix. APPROVED cannot carry
  Critical/Important findings; parked minors must be Minor. SEND_BACK and
  ESCALATE require actionable findings.
- Director: `mode`, `decision`, `reason`, `source_plan_hash`, `target_task`,
  and `proposal`. Corrective proposals describe one complete task without
  allocating its authoritative ID; arbitration proposes permitted target-task
  field changes. Closing uses the separate schema below.
- Closing: `verdict` in APPROVED/REOPEN/BLOCKED, `summary`, `findings`,
  `parked_minors`, and `proposed_tasks`. APPROVED requires no unresolved
  blocking findings or proposed tasks.

The supervisor binds these semantic objects to identities from `request.json`;
the model does not get to certify its own candidate SHA or dispatch success.
JSON regex salvage is prohibited in the Codex consumer. Keep any legacy parser
behavior explicitly behind the OpenCode backend until separately migrated.

Dispatch exit codes: 0 completed with validated semantic output; 2 invalid
input; 3 unavailable runtime/auth/model/policy; 4 invalid/incomplete protocol
or semantic output; 5 confirmed transient failure before execution; 6 ambiguous
failure after execution may have begun; 130 interrupted; 124 deadline exceeded.
A valid SEND_BACK or TEST_DEFECT is exit 0 at the transport boundary and is
routed semantically by the caller. Exit zero does not mean task approval.

## 8. RED, GREEN, independent review, and routing

BRIEF and RED prepare fresh evidence tied to task, attempt, runner, command,
source snapshot, and exit code. The operator authors and runs RED, then
implements and checks GREEN. Script CEO validates evidence form and runs the
authoritative gates. Compilation/collection failure without an executed test
cannot count as RED. The reviewer remains the independent judge of test fit.

Codex `coder-gate` reads the normalized operator status. TEST_DEFECT routes to
arbitration. BLOCKED produces a diagnostic infrastructure/task block; it must
not be silently interpreted as DONE. Default external coder invocation allowances
are [5,3,3] for at most three cycles. At exhaustion of each cycle return to the
director; after the third assessment pause if unresolved. Pause earlier when no
resolution is possible. Maximum eleven coder invocations; internal RED/GREEN
iterations do not count separately. Persist budgets across restart, corrective
children and scope changes. Confirmed pre-start infrastructure/provider failures
are separate; ambiguous post-start work requires reconciliation, not blind replay.
R4 must enforce these policies before production adoption.

Green means required tests/analyzers/formatting succeeded, scope/protected state
are valid, and Script CEO committed successfully. Capture baseline failures before
changed-code verification; allow unaffected work and distinguish inherited failures
from regressions. A candidate with inherited failures is not reported as green;
final acceptance of remaining proven baseline failures requires an explicit waiver. Then dispatch the
independent reviewer. Reviewer transport failure preserves review-pending
state and retries only that review when permitted. Do not re-enter the coder
or recompute its baseline at a new HEAD. Persist task/attempt base and reviewed
candidate commit so recovery always reviews the intended complete diff.

The reviewer is fresh for a new task family. It may resume only its own session
for repeated review of that family, with a new complete package and candidate
identity. Operator and reviewer session IDs are never interchangeable.
APPROVED advances only after strict validation. In-scope SEND_BACK goes directly
to the same coder with evidence; structural/uncertain scope or viability changes
invoke the director. ESCALATE invokes arbitration. Re-enter BRIEF/RED after a valid
ruling without resetting the episode's [5,3,3] allowance.

Scope validation uses actual changed files, the approved plan, declared test
updates and supervisor-owned dynamic grants. Related new files may be granted
within approved task roots without a separate director hop; undeclared existing
files need a director scope proposal. Scripts atomically reserve ownership, check
protected paths and concurrent/future task conflicts before writes. Ambiguous
relatedness escalates; a worker assertion is not an unrestricted write grant. A generic exemption for all tracked JSON plans does not
authorize an operator to change the plan. No-op verification tasks require an
explicit plan contract and independent review; do not invent a RED failure or
silently produce an empty commit for an implementation task.

## 9. Canonical plan changes and parallel task ownership

The director proposes; scripts apply. `apply_director_proposal` validates
schema, target, source hash, allowed fields, spec constraints, and full DAG
under one canonical-plan transaction lock. Corrective IDs are allocated by
the script. Arbitration changes only the named incomplete task and approved
scope. A stale proposal is rejected and re-requested with current context;
an invalid proposal cannot produce `arbitrate_resolved`.

For a wave, directors in different workers never edit tracked plan copies.
Their proposals are submitted to the integration workspace's canonical plan
transaction. The same lock excludes integration while a plan transaction
stages/commits the canonical change and refreshes the snapshot. Workers receive
new derived snapshots at episode boundaries; their tracked plans remain
unchanged, preventing plan-file merge conflicts and duplicate IDs. A corrective
task continues in its parent task-family worktree, with all child IDs recorded
in that worktree's ownership manifest. It must not depend on its own unapproved
parent; valid predecessor requirements carry forward.

Journal the old/new plan hashes, proposal identity, assigned ID, commit, and
ledger event. Recovery reconciles a committed transaction whose event write
was interrupted without applying the proposal twice. Competing transactions
cannot drop a task. Reconciliation of a corrective's parents uses these
explicit family relationships and verified review results.

Run/worktree names include repository identity, canonical relative plan path
hash, and run ID. Suggested branch pattern is
`codex/pipeline/<plan-id>/<run-id>/task-<family-id>`; branch names are persisted,
never reconstructed from task numbers. A single integration writer owns a
branch at a time. A concurrent second run against that branch blocks with the
owner identity; separate integration branches can proceed independently.

Preserve plan-derived wave scheduling, per-worktree ledgers, sequential
integration, exact-tree test reuse, and bounded integration recovery. Copy all
resolved toolchain descriptors into children. Validate every affected
toolchain on integration and final verification. Normalize Windows path/case
identity without conflating distinct POSIX paths. An orphan branch without its
expected worktree is a repairable blocker, not an allocated worktree.

Export logs, semantic results, session manifests, and ledger shards to the
integration workspace before releasing a merged worktree. Verify export
integrity, the complete task family, clean worker state, stopped processes,
and branch-tip ancestry. Never force-remove uncommitted work or another run's
tree. Rebuild nonportable Flutter caches instead of assuming copied absolute
package paths are valid.

## 10. Resume, retry, interruption, and retention

Persist sessions under repository/run/task-family/role identities, with thread
ID, model/effort, config hash, worktree, and lifecycle state. Within-family
corrective tasks may continue the operator session after the script explicitly
binds the child task to that family. Director sessions are per episode;
closing is fresh. Missing or inconsistent session identity blocks resume.
An explicitly configured fresh recovery may reconstruct complete context and
record `context_reset`; it is never a silent fallback.

Retry at most three confirmed pre-execution transient failures using backoff
1 and 3 seconds. Invalid config/auth/model/policy and protocol-invalid outputs
are not automatically redispatched. If execution may have occurred, preserve
the session and inspect script-owned state before continuing; never replay a
fresh write task blindly. Retry evidence uses distinct attempt directories.

The runner owns a process registry with PID, start identity, run, task, role,
and process-group/job identity. Cancellation or deadline stops admissions,
signals owned process trees, waits for exit, records interruption, and keeps
worktrees/evidence. On Windows use a verified process-tree containment method
and hidden launch; on POSIX use owned process groups. PID reuse, orphan
processes, and locked files must be tested. Restart refuses a second active
owner and reconciles incomplete attempts before scheduling.

Retain completed worker sessions and diagnostic evidence for 30 days by default,
configurable. Protect active/unresolved runs. Cleanup only run-owned resources
through supported backend lifecycle operations. Do not call OpenCode cleanup for
Codex or edit provider SQLite rows. If deletion is unsupported, report that limit
and retain the provider-owned resource; do not fake successful cleanup. Preserve
minimal completion/approval records needed by downstream plans after raw evidence
expiry. Archiving is distinct from deletion and needs a tested adapter. Ephemeral mode is allowed only for genuinely one-shot
invocations where resume is deliberately unavailable; it is not the default
for task-family workers.

## 11. Final verification, closing, and publication

Record the initial comparison base and the selected target branch in the run
manifest; do not infer `origin/main` on each closing attempt. Run the mechanical
final gate on all tasks/toolchains and the candidate commit. Check complete
family integration, no live workers, no owned unreleased worktrees, valid
plan/snapshots, and branch-wide documentation requirements.
R4 task gates use affected tests including dependent consumers/contracts and
integration checks; unknown impact broadens up to full suites. Recompute impact
on merged trees. Closing runs all configured complete suites with evidence bound
to tree/environment/config/commands. New regressions block; unchanged baseline
failures may proceed only with explicit candidate/failure-bound user waiver.
Report such completion as waived, never green. A waiver does not alter raw results.

A fresh director returns the strict closing schema. APPROVED is valid only for
the supervisor-recorded candidate HEAD, plan hash, spec hash, and ledger
revision. REOPEN submits task proposals through the canonical transaction,
re-enters execution, and repeats final verification/closing afterward.
BLOCKED, malformed output, failure, or unexpected file mutation never records
successful `final_review` or publishes. A crash between acceptance and ledger
write is reconciled idempotently.

At each new run select `local` or `pull_request` (push and create PR); persist the
explicit choice with concurrency and models. Do not infer a default or ask the
same publication permission again at closing. No automatic merge. Legacy `push`
may remain an explicitly configured adapter operation, not a silent launch choice.
Push/PR operate on the recorded branch and remote; detached worktrees require
a named branch/handoff chosen outside the worker loop. No force push. PR
creation is idempotent by head/base and records failure accurately instead of
claiming full delivery after a failed command. The shell runner must not assume
access to desktop-only tools such as `create_thread` or `handoff_thread`.

## 12. Jev and resource boundaries

Keep existing scoring, thresholds, calibration bindings, timeouts, and the
Site 1-5 baseline fallbacks. Bind advisory provenance to run/task/episode and
the actual dispatched prompt hash. Run Site 3 only when routing requires a
director; it cannot suppress that call. In-scope direct corrections skip it. Site 4
cannot suppress a reviewer; Site 5 cannot edit a runtime plan. Do not claim
that the entire pipeline has zero additional LLM inference when Jev is active:
the no-intervention requirement applies to orchestration, while Jev is optional
semantic advice and the workers perform semantic work.

Only scripts requiring external-service credentials receive them. Do not copy
credentials into prompts, raw logs, runtime manifests, or bundles. Aggregate
reported usage without confusing API billing with ChatGPT account entitlement.
Emit compact progress without streaming full model reasoning into the caller.

## 13. Delivery and acceptance

Deliver source and extracted-package coverage. Required offline scenarios:
fresh/resume Codex argv and stdin; wrong session/model/config; stdout/stderr
separation; interim/failed/stale/malformed results; auth/quota failure; retry
after ambiguous mutation; paths with spaces and Unicode; protected file edits;
corrective/arbitration/closing decisions; concurrent director proposals;
two plans with the same basename; interrupted waves; retained evidence;
multi-toolchain gates; and rejected closing that cannot push.

Use deterministic fake CLI executables and disposable repositories for failure
injection. Live acceptance, once implementation is approved, runs a tiny real
Codex task through operator RED/GREEN, independent review, explicit-ID resume,
one corrective/arbitration path, a two-worker wave, and closing. Verify the
effective role configuration and sandbox behavior with those runs. No push or
PR is needed for the acceptance fixture. Document exact CLI/platform versions,
observed capabilities, skipped combinations, and failures.

All C01-C20 findings map across the active round plans, not only R1. Initial
implementation is bootstrapped through a normal approved Codex development
workflow because the new launcher does not exist yet. Do not run this migration
plan through today's `run-pipeline`: that would launch OpenCode. The JSON plan
is complete authoring output, not a claim that this checkout can execute its
future Codex backend now.

The current deliverable is the review, this spec, and the complete plan. No
runtime changes or live-model compatibility certification are included.

## 14. Sources and decision provenance

The linked review records local evidence, source locations, and official
documentation consulted on 2026-09-25. User-facing policy decisions were confirmed
individually and are preserved in the linked decision record. Technical interfaces
remain implementation design. CLI help confirms option availability, not authenticated execution,
Windows policy equivalence, or successful model access. Those are explicit
acceptance conditions rather than assumptions hidden in the design.

## 15. Shared-backend transition and Round 1 contract

The user expanded scope to one shared engine for Codex and OpenCode and accepted
the adapter/project-pin design. `roadmap.md` and the confirmed decision record
govern this revision. Earlier Codex details remain backend-specific requirements, not a
requirement to duplicate the state machine. This section supersedes conflicting
model examples, one-round sequencing and long-term testing/correction policies.

### Shared configuration and lifecycle

Backend is an explicit enum (`codex`, `opencode`). Each adapter implements its
own read-only capabilities, settings validation, permission policy, invocation,
resume, cancellation and result normalization. No model names are defaults.
User-confirmed selections bind backend, roles, supported effort/variant settings,
configuration hash and confirmation provenance. Missing confirmation is
`needs_configuration`; no worker starts. Initial runs use one backend throughout.

Round 1 ships configuration and capability contracts only. Existing runtime
consumers are not switched to unfinished adapters. Later R2 implements dispatch;
R3 integrates the state machine. Original task numbers in historical planning
material are superseded by the round mapping in the roadmap.

### Safe update contract

The sync command inspects/fetches and shows the diff, then automatically validates
and fast-forwards a clean strictly-behind installation. Offer --check-only for
inspection without application. Report unchanged/behind/updated/needs_user_merge/
error with SHAs, paths, action and errors. Exit 0 means successful inspection or
update, 1 needs user resolution, 2 invalid input, 3 operational failure.
Validate the candidate in isolation before changing the selected version.
Any failed inspection blocks changes. Ahead/divergent/dirty/unexpected detached/
mismatched-remote states preserve everything and request user resolution.
Never reset, clean, stash, rebase automatically or rewrite local commits.

Managed bundle installation stages and validates a new immutable version before
an atomic pointer switch; failure preserves the previous selection. A user-owned
checkout update is a distinct operation: failure after a successful fast-forward
must be reported accurately, never described as a rollback that did not occur.
Live runs and enrolled projects keep their existing version pins.

### Installation and documentation contract

`harness-project init --project DIR --bundle ID --backend NAME` writes a
versioned `.superpowers/harness.json` and a marked `AGENTS.md` entry. The binding
contains immutable bundle identity/hash, backend configuration reference and
policy references, using relocatable identifiers. Repeated enrollment is
idempotent and invoked automatically on first pipeline use. Existing user text
remains intact. Only the current project is enrolled. A missing existing pin is
an error, not a silent fallback. Before a new run offer newer validated bundle
changes and update the pin only if accepted; active runs retain their version.

The packaged bundle includes all runtime files, prompts, skills and canonical
documentation. Codex/OpenCode installation paths stay backend-specific. The
installation does not claim the new Codex execution path works before R3.

The user confirmed one canonical `README.md` for setup, usage, current architecture,
rules and glossary. Migrate useful current content and all orientation, packaging,
prompt, skill and doc-check consumers before deleting root `CONTEXT.md` and
`README-LLM.md` in R1. Keep historical detail in linked ADRs/specs. Later rounds
must not recreate retired documents or require duplicate README updates.
Approval of brainstorming scope permits writing both spec and plan without
another written-spec checkpoint. Material scope changes still need clarification.

### Shared semantic and transport contracts

Round 1 defines request/result schemas and strict validation without launching
workers. `pipeline_config.load_runtime(path)` returns validated configuration;
`codex_capabilities.inspect_runtime(config, project)` and the corresponding
OpenCode function return capability reports. `dispatch_contract.validate_request`
and `validate_result(value, request)` validate normalized identity, transport and
role payloads. `harness_install.resolve_bundle(project)` verifies the project pin.
Invalid inputs raise structured validation errors or the documented CLI exit.

Use section 7 semantic schemas, including NEEDS_CONTEXT and TEST_DEFECT. Review
findings additionally describe correction scope (`in_scope`, `structural`, or
`uncertain`), affected paths and contracts. R1 validates these values; R4 adds
direct correction routing. Unknown/stale/malformed output cannot approve a task.
Codex event names remain adapter-specific; OpenCode uses its own verified events.

### Deferred policy changes and acceptance

R2 pins/adapts upstream skill prompts and task skill manifests. R3 preserves
conservative verification while repairing recovery, integration and closing.
R4 introduces bounded external dispatch budgets, in-scope direct corrections
and affected-test selection plus explicit baseline waivers; full-suite closing
and uncertainty fallback remain mandatory. R5 audits every Flutter stage and
generalizes applicable capabilities, requirement profiles, catalog/research,
automatic compatible adoption/dependencies and reviewed template promotion.
Use private CarlosMonteiroNeto/code-templates; no remote is created in this
planning task. R6 is deferred with no executable tasks; compare alternatives to
Jev entry classification only in a future investigation.

The current four-task plan completely specifies R1 only. Acceptance requires
both backend configuration fixtures, malformed-result rejection, safe sync with
local commits, failed-update preservation, idempotent project binding, preserved
AGENTS content, complete packages and canonical orientation. R1 does not certify
live runtime/model support. R2–R5 have complete active plans linked from the roadmap,
authored at the user's request using the available context. Before execution,
verify their exact files/interfaces against accepted predecessor commits and
refresh any implementation drift. No tasks are silently expanded by a runtime
director.
