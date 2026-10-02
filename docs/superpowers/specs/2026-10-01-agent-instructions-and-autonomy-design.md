# Agent instructions and implementation autonomy

Date: 2026-10-01
Status: Agreed conversational design, recorded alongside the requested implementation plan. Implementation has not started.

## 1. Purpose

Workers must receive substantive, pipeline-adapted Superpowers guidance through deterministic scripts. The coder must complete investigation, RED, implementation, debugging, GREEN, and self-review within one invocation whenever possible. Routine file discovery, focused checks, and correction of coder-authored tests must not require another LLM dispatch.

Scripts retain orchestration, permissions, evidence collection, authoritative verification, invocation budgets, integration, commits, and publication. Autonomy does not authorize changing acceptance criteria.

## 2. Investigation findings

The inspected checkout was `main`, at `817da04`, with unrelated local changes. This design does not modify those changes.

- `scripts/prompt_headers.py` assembles role protocol, authority, adapted core, backend policy, domain skills, acceptance, and output contract. Repository references to the module occur in its tests, not production dispatch.
- `scripts/codex_dispatch.py` checks the supplied prompt hash, then prepends separate role instructions. The checked input hash therefore does not by itself identify the final submitted prompt.
- The public `scripts/dispatch` routes OpenCode to `scripts/dispatch-opencode`, a shell launcher. `opencode_dispatch.py` is not sufficient as the sole integration target.
- `codex_policy.py` enforces exact paths and command descriptors. `scope_grants.py` requires director approval for extra existing files. Prompt changes alone cannot relax these constraints.
- `wave-next` compares declared files and shared resources. New directory authority invalidates file-disjointness as the sole scheduling test.
- `coder-prompt.md` describes unlimited retries, while `dispatch_budget.py` defines bounded family invocation cycles, defaulting to `[5, 3, 3]`.
- `prompts/adaptation-map.json` maps systematic debugging to the director, but not to the operator. Its retained labels describe adaptations, not proof of verbatim or complete inclusion.

## 3. Upstream instruction reuse

Keep the recorded upstream revision `b36e0829c6d0140e93cfef2ca599b1b07d4a7797` as the starting reference. Verify source bytes against the lock before claiming provenance; if a listed source cannot be verified, record and resolve that discrepancy before shipping. Do not silently substitute this repository's modified skills or the latest upstream release.

Audit each relevant upstream section against the actual role text. Record retained, adapted, or omitted status, source identity, destination section, and rationale. Retained means the substantive instruction survives; distinguish verbatim text from a paraphrase. Hashes prove identity, not semantic fidelity.

Operator guidance must cover investigation before changes, behavioral TDD, root-cause debugging, narrow reproduction, comparison with working paths, evidence-backed test corrections, self-review, verification before completion, and technical evaluation of review findings. Reviewer guidance must cover independent acceptance and test-quality review, complete diff inspection, and actionable evidence-backed findings. Director guidance must cover bounded diagnosis and requirement/scope arbitration.

Adapt orchestration instructions to script ownership. Workers do not recursively brainstorm, select additional agents, commit, publish, or change control state. Preserve the existing restriction on worker web research. Domain skills are selected and resolved from approved revision-pinned inputs by scripts; runtime prompt adaptation requires no LLM call.

## 4. Shared prompt delivery

One preparation boundary invokes `prompt_headers.build()` for operator, reviewer, and director, on both backends. It resolves approved skills and renders authority from the same normalized capability data used by enforcement. Do not maintain a second conflicting permission description.

Persist the exact submitted prompt bytes, their SHA-256, core/source/skill provenance, role, and policy identity before starting the worker. Keep transport-only formatting distinct from instruction content. If backend developer instructions carry behavioral content separately, persist and hash those too, with an envelope identifying all submitted instruction channels. No unrecorded role prefix may be added after hashing.

Missing required context, unresolved required skills, conflicts, or prompt-budget overflow cause a pre-start configuration failure. Never truncate mandatory instructions or silently fall back to old templates.

Fresh dispatch receives the full package. A supported, identity-checked resume sends a recorded delta referencing the stable package identity; it does not repeat the entire core. A backend that requires full replay records that replay explicitly. Changed acceptance, authority, skill revisions, or core identity must be reconciled explicitly before resume; an old session must not silently retain obsolete permissions.

## 5. Working areas and compatibility

New plans opt in through `task.working_areas`, a non-empty list of canonical repository-relative directories. `touches` remains an estimate and review aid, not an exhaustive write list for opted-in tasks. The repository root is represented by `.` only when explicitly requested in the plan; it is never inferred.

Inside reserved areas, the operator can create and modify ordinary source and test files, including supporting files not predicted by `touches`. Existing deletion and rename authority is not broadened by this change. Paths outside the areas require a concrete scope blocker; there is no new interactive grant conversation.

Protect Git metadata, pipeline control state, plans/spec authority, ledgers, grants, permission configuration, evidence storage, dependency manifests, and lockfiles. Installation remains restricted. Project files implementing the pipeline itself are ordinary source when this repository is the target; the trusted runner and policy bundle executing the current run must remain outside worker write authority. Capture runner evidence through trusted scripts, not arbitrary worker writes.

Canonicalize paths with repository/platform semantics, including case aliases, symlinks, junctions, nonexistent descendants, and directory boundaries. `src/a` does not include `src/ab`. Revalidate at execution and inspect the actual candidate diff before gate approval. State explicitly that application-level tool policies are not an OS sandbox against arbitrary code executed by tests.

Older plans without `working_areas` retain their exact-path authority. Do not infer broad directory access from their file lists. Mixed scheduling treats legacy paths as claims that conflict with any enclosing opted-in directory. Existing resource and dependency constraints continue to apply.

## 6. Directory reservations

Reserve all task working areas atomically before dispatch. Equal or ancestor/descendant areas overlap. Overlapping tasks execute sequentially, even in separate worktrees; disjoint areas may run concurrently subject to dependency and shared-resource rules.

Reservations use run/task-family ownership and existing state-locking infrastructure. A correction in the same family retains its reservation. Resume reacquires or validates ownership. Release occurs after task integration or explicit termination; do not free an area merely because a process timed out while it might still be alive. Recovery verifies worker termination before retiring stale ownership. Two concurrent schedulers must not obtain overlapping reservations.

## 7. Script-mediated commands

Extend the existing scoped runner instead of exposing unrestricted shell. Workers request structured capabilities: RED/test, analysis, formatting, and supported read-only local diagnostics. The script validates toolchain, cwd, target files, selectors, ownership, and protected paths, then executes through `scripts/cmd` and retains raw evidence and true exit status.

Support focused file and test-case selection only through adapters that explicitly implement it. Unsupported selectors return a precise capability error; no arbitrary flags or command strings are passed through. Reject shell chaining, wrappers supplied by workers, installation, network operations, and Git mutations. Trusted runner implementation may launch the configured interpreter; that is distinct from authorizing arbitrary interpreter commands from the worker.

Coder-requested checks do not determine the authoritative gate's test selection. Candidate-bound impact selection and full-suite fallback remain script-owned.

## 8. Local loop, tests, and budgets

An ordinary failed check triggers local diagnosis and another supported check, not an immediate return. The coder returns completed work, a concrete blocker beyond its authority/capability, or a limit-exhausted outcome. Existing output schemas are extended only where required; internal reasons are normalized before routing.

The coder may correct its own tests when the original setup or assertion is demonstrably wrong and the correction preserves acceptance. Record the rationale, prior and corrected test identities, and immutable earlier evidence. Obtain fresh behavior-specific RED and GREEN for the corrected test. Use a script-owned pre-implementation snapshot when production already passes the corrected test; do not let a worker fabricate RED by damaging its implementation. Existing project tests are not automatically classified as coder-authored.

The reviewer checks acceptance preservation and the complete test evolution. Scripts validate provenance and sequence; they do not claim to decide semantic weakening. Requirement contradictions still go to the director.

Retain the configured external invocation budgets and default `[5, 3, 3]` cycles. Local test iterations do not consume extra external invocation reservations. Existing per-invocation timeout/turn limits remain separate; report exhaustion accurately and terminate owned processes before retry. No unlimited-retry language remains in active instructions.

## 9. Acceptance and non-goals

Tests must capture the instructions delivered through real production launch seams for both backends and all roles, including resumes. A deterministic worker fixture must create an unlisted source/test file in its area, observe RED, fix the code, correct its own test with evidence when needed, and return GREEN in one external invocation. This proves plumbing, not real-model quality.

Tests must reject protected/outside-area writes, manifest changes, unsafe selectors, unverified prompt sources, stale evidence, and overlapping reservations. Gates and review packages include every candidate change, including added files, regardless of `touches`.

No new dependencies, automatic upstream upgrades, unrestricted worker shell, recursive delegation, changed publication policy, or removal of independent review. Real-model smoke runs are optional follow-up validation with configured backends; deterministic tests are mandatory.
