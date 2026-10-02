# Agent Instructions and Autonomy Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` for inline execution, or the explicitly selected script-owned two-model pipeline. Do not launch implementation from this document without the user's execution selection. Steps use checkboxes for tracking.

**Goal:** Deliver adapted Superpowers instructions to every worker and let coders complete bounded RED/GREEN work without routine scope dispatches.

**Architecture:** A shared prompt preparation boundary binds instruction provenance to the enforced capabilities. Directory reservations and a structured scoped runner grant local implementation freedom while scripts retain budgets, gates, evidence, and integration.

**Tech Stack:** Existing Python standard-library modules, Bash launchers, PowerShell entry points, and Python unittest suites; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-01-agent-instructions-and-autonomy-design.md`

## Global constraints

- Scripts retain orchestration, permissions, evidence collection, authoritative verification, invocation budgets, integration, commits, and publication. Autonomy does not authorize changing acceptance criteria.
- Older plans without `working_areas` retain their exact-path authority.
- Installation remains restricted.
- Local test iterations do not consume extra external invocation reservations.
- No new dependencies, automatic upstream upgrades, unrestricted worker shell, recursive delegation, changed publication policy, or removal of independent review.
- All artifacts and prompts are English. Preserve existing unrelated local changes.

## Execution preparation

This is a planning artifact, not an executable pipeline plan. If script-owned execution is selected, translate these tasks into the current validated canonical plan schema before launching; do not depend on the proposed `working_areas` feature to implement itself. Use existing explicit file permissions for bootstrap tasks.

- [ ] Confirm checkout, current instructions, baseline commit, and overlapping local work; create/reuse an isolated implementation checkout through the native worktree tooling.
- [ ] Read the spec and trace each listed seam against the current branch before editing. Capture narrow baseline results; investigate any failure rather than accepting it without evidence.
- [ ] Run commands through `skills/two-model-sdd-pipeline/scripts/cmd --full-file <external-log-path> -- <command>`. On Windows use the repository-supported Bash entry point and canonical paths. Full logs remain outside candidate source changes.

In commands below, `S=skills/two-model-sdd-pipeline`, and `TESTS=$S/tests`; these abbreviations describe paths, not additional runtime configuration. Run Python tests with `python -m unittest discover -s <TESTS> -p '<pattern>' -v`, wrapped through `cmd`. Each RED must fail at the new behavioral assertion, not an import/setup error. Commit only scoped, verified task changes through the controller.

## Review focus

1. OpenCode's shell production path bypassing a Python-only fix: Task 2 captures public launcher traffic.
2. Windows case aliases, junctions, and nonexistent descendants bypassing directory bounds: Tasks 3–4 exercise canonical ownership and backend enforcement.
3. Resume retaining an old authority or unrecorded prompt prefix: Task 2 checks envelope identity and policy changes.
4. Corrected tests reusing stale RED after implementation: Task 5 binds each revision to captured snapshots and evidence.
5. Concurrent scheduler restart releasing a still-running owner's reservation: Task 3 tests atomic claims and recovery.

## Task 1: Audit and strengthen the adapted instruction cores

**Depends on:** None. **Spec:** §§3, 8.

**Files:** Modify `$S/prompts/{adaptation-map.json,upstream-lock.json,core-operator.md,core-reviewer.md,core-director.md}`, `$S/coder-prompt.md`, `$S/reviewer-prompt.md`, `$S/controller-brief-prompt.md`, and `$S/tests/test_r2_prompt_headers.py`. Create `$S/prompts/upstream-adaptation-audit.md` and `$S/tests/test_prompt_adaptation_contract.py`. Inspect `$S/codex/` and installed agent templates for duplicate active instructions before assigning edits.

**Interface:** Keep `prompt_headers.build(role, context, skills, policy) -> dict`. Extend adaptation records with destination section and adaptation kind; keep existing source identity fields compatible.

- [ ] Verify pinned upstream source bytes against the lock; use the exact recorded revision, not modified local equivalents. Record every discrepancy and resolve its identity before updating provenance.
- [ ] Add tests `test_operator_has_investigation_and_debugging_contract`, `test_all_adaptations_have_source_and_destination`, and `test_active_templates_do_not_promise_unlimited_retries`. Assert explicit workflow sections, mapped destinations, and absence of conflicting retry/test-freeze rules.
- [ ] Run `test_prompt_adaptation_contract.py`; confirm assertion failures describe missing or contradictory instructions.
- [ ] Update cores and adaptation records, including operator handling of review findings and test correction. Document substantive upstream guidance preserved, adapted, or omitted with reasons. Automated structural checks supplement a manual fidelity comparison.
- [ ] Run `test_prompt_adaptation_contract.py` and `test_r2_prompt_headers.py`; inspect the complete rendered role text and commit the instruction contract.

## Task 2: Deliver one recorded instruction package through every dispatch path

**Depends on:** Task 1. **Spec:** §4.

**Files:** Create `$S/scripts/prepare_prompt.py` and `$S/tests/test_prompt_delivery.py`. Modify `$S/scripts/{prompt_headers.py,skill_manifest.py,dispatch_contract.py,codex_dispatch.py,codex_launcher.py,dispatch-opencode,review_dispatch.py,director_prompt.py}` and existing dispatch tests. Inspect `red-gate`, `coder-gate`, and `task-run` callers; change callers where needed to supply complete context, not a parallel assembler.

**Interface:** `prepare_prompt.prepare(role: str, context: dict, skills: dict, policy: dict, output_dir: pathlib.Path) -> dict` returns `prompt_path`, `prompt_hash` (64 lowercase hex), `provenance_path`, and `instruction_envelope_hash`. The envelope records every submitted instruction channel and its digest. Normalize the builder's `sha256:` format explicitly at this boundary.

- [ ] Add a backend/role matrix for fresh and resumed dispatches. Fake executables capture actual stdin/argv/config payloads from the production launchers; assert adapted core, acceptance, capability text, domain skill content, and output contract are delivered once.
- [ ] Add failure cases for absent required context, source/skill conflict, overflow, altered prompt bytes, and changed resume policy. Assert no worker process starts on invalid preparation.
- [ ] Run `test_prompt_delivery.py` and classify the expected missing-delivery assertions.
- [ ] Implement shared preparation and wire it into Codex and the OpenCode shell path. Remove post-hash behavioral prefixes; retain separately recorded developer channels where required by the backend. Persist resume deltas and stable package identities.
- [ ] Run `test_prompt_delivery.py`, `test_r2_prompt_headers.py`, `test_r2_skill_manifest.py`, `test_codex_dispatch.py`, and `test_dispatch.py`; commit verified dispatch integration.

## Task 3: Define directory authority and atomic scheduling reservations

**Depends on:** None; integrate before Task 4. **Spec:** §§5–6.

**Files:** Create `$S/scripts/working_areas.py` and `$S/tests/test_working_areas.py`. Modify `$S/scripts/{plan_validation.py,wave-next,touches-overlap,scope_grants.py,task-run,integrate,worktree-release}` and `$S/tests/{test_wave_next.py,test_codex_plan_validation.py}`. Reuse `state_lock.py`; update any canonical schema owning task properties found during implementation investigation.

**Interfaces:** `working_areas.normalize(task: dict, repo_root: str) -> dict` returns `{mode: 'areas'|'legacy', roots: list[str], exact_paths: list[str]}`. `working_areas.overlap(left: dict, right: dict, repo_root: str) -> bool` defines scheduling overlap. `reserve(registry_path: str, owner: dict, scope: dict) -> dict` atomically returns granted/conflict and owner identity; `release(registry_path: str, owner: dict) -> None` requires matching ownership and verified lifecycle completion.

- [ ] Add tests asserting equal/nested roots conflict, sibling `src/a` and `src/ab` do not, legacy `src/a/x.py` conflicts with `src/a`, missing areas retain legacy mode, and explicit `.` reserves the repository.
- [ ] Add platform cases for traversal, absolute paths, case aliases, symlinks/junctions, and nonexistent descendants. Add a two-process reservation race and recovery test: exactly one overlapping claim succeeds; a live owner is never retired by timeout alone.
- [ ] Run `test_working_areas.py`; verify expected behavioral failures.
- [ ] Implement canonical normalization, validation, reservation persistence and scheduler overlap using one shared definition. Preserve dependency/shared-resource checks and family ownership through correction and integration.
- [ ] Run `test_working_areas.py`, `test_wave_next.py`, `test_codex_plan_validation.py`, and `test_plan_refresh_after_integration.py`; commit the authority/scheduling contract.

## Task 4: Enforce working areas and expose supported local capabilities

**Depends on:** Tasks 2–3. **Spec:** §§5, 7.

**Files:** Modify `$S/scripts/{codex_policy.py,opencode_policy.py,scoped_runner.py,scoped-run,codex_launcher.py,brief-scaffold}` and `$S/tests/{test_codex_role_policy.py,test_codex_scoped_runner.py}`. Create `$S/tests/test_worker_capabilities.py`.

**Interface:** Normalized policy embeds Task 3's scope plus protected paths and configured toolchains. Add `scoped_runner.resolve_capability(request: dict, policy: dict) -> dict` returning trusted `argv`, `cwd`, evidence destinations, and identity. Requests contain `mode`, `toolchain_id`, `paths`, and optional adapter-supported `selector`; no worker-supplied command string.

- [ ] Add parity tests: create unlisted source/test files and modify existing ordinary files inside an area; reject outside/protected/dependency writes and unapproved deletion/rename expansion. Confirm legacy exact-path behavior remains unchanged.
- [ ] Add runner tests for focused file/case selection, configured interpreter execution, unsupported selectors, arbitrary flags, shell syntax, dependency installation, and path escapes. Assert raw exit status/evidence survives `cmd` compression.
- [ ] Run `test_worker_capabilities.py` and the narrow new runner cases; classify RED at permission/capability assertions.
- [ ] Generate prompt capability descriptions from normalized enforced policy; adapt both backends. Execute supported requests through the trusted scoped runner and `cmd`. Keep the executing policy/runner bundle outside worker write authority, including when the target project is this repository.
- [ ] Run `test_worker_capabilities.py`, `test_codex_role_policy.py`, `test_codex_scoped_runner.py`, and `test_cmd_runner.py`; confirm supported backend policy mechanisms and document their limits; commit.

## Task 5: Preserve test evolution and keep routine failures inside one invocation

**Depends on:** Tasks 2, 4. **Spec:** §8.

**Files:** Modify `$S/scripts/{red_evidence.py,scoped_runner.py,coder-gate,red-gate,review-package,context_package.py,dispatch_budget.py,dispatch_retry.py}` as needed. Create `$S/tests/test_local_coder_loop.py`; extend `$S/tests/{test_red_form_check.py,test_r4_dispatch_budget.py}`.

**Interface:** Add an append-only script-owned test revision record: task/attempt identity, test content digest, prior revision digest, correction rationale, acceptance identity, RED evidence identity, source snapshot, and GREEN evidence identity. `red_evidence.validate_revision_chain(records: list[dict], identity: dict) -> None` rejects stale, missing, reordered, or conflicting records. Preserve existing evidence validation for legacy tasks.

- [ ] Add a deterministic worker fixture that investigates an assertion failure, performs multiple scoped checks, corrects its own test, and returns once. Assert external operator invocation count equals 1, while check count exceeds 1.
- [ ] Add evidence tests: corrected test needs fresh RED against the retained pre-implementation snapshot and fresh GREEN; previous evidence remains immutable; loader failures and snapshot/digest mismatch cannot pass. Existing tests cannot be mislabeled as newly coder-authored.
- [ ] Add budget tests showing local checks do not reserve dispatch slots, external retries do, default `[5, 3, 3]` remains, and process timeout cannot lead to concurrent old/new attempts.
- [ ] Run `test_local_coder_loop.py`; classify expected failures before implementing evidence lineage, normalized completion/blocker/limit reasons, and review-package inclusion of test evolution. Scripts validate lineage; reviewer judges semantic weakening.
- [ ] Run `test_local_coder_loop.py`, `test_red_form_check.py`, `test_r4_dispatch_budget.py`, and `test_dispatch_retry.py`; commit.

## Task 6: Verify complete integration and document migration

**Depends on:** Tasks 1–5. **Spec:** §9 and all cross-cutting requirements.

**Files:** Create `$S/tests/test_agent_autonomy_integration.py`. Modify `README.md`, `$S/SKILL.md`, and active role/launcher documentation found by a repository-wide stale-instruction search. Modify `run-gates`, `integrate`, or `review-package` only if integration tests expose diff filtering based on `touches`.

- [ ] Add end-to-end fake-backend tests for both production launch paths: disjoint tasks run concurrently, overlapping tasks serialize, an unlisted added file reaches authoritative gates and review, and all three roles receive recorded adapted instructions.
- [ ] Assert protected changes fail before acceptance, old plans retain authority, resume does not duplicate cores, and ordinary local fixes do not add operator/director dispatches. Cover correction-family reservation retention and release after integration.
- [ ] Run `test_agent_autonomy_integration.py`; investigate each failure through the actual call path and fix only in-scope causes.
- [ ] Document `working_areas`, compatibility, supported selectors, protected categories, test corrections, invocation versus local-loop limits, provenance updates, and the limits of backend application-level enforcement. Remove conflicting unlimited-retry, exhaustive-file-list, and blanket test-freeze statements from active documentation.
- [ ] Run the complete `$S/tests` unittest discovery suite through `cmd`, plus the repository's documented relevant shell checks and `doc-check` in its required workspace context. Investigate failures, rerun narrow checks, then the relevant broader verification. Record actual commands/results; do not claim real-model validation from fixtures.
- [ ] Review the complete branch against the spec, confirm no unrelated local changes were included, and commit the verified integration/documentation changes. Optional live backend smoke runs use the user's configured runtime; publication is a separate action.

## Self-review and handoff

Coverage: upstream fidelity → Task 1; production prompt delivery/provenance/resume → Task 2; compatibility/reservations/recovery → Task 3; backend authority/local commands → Task 4; test correction/local loop/budgets → Task 5; actual diff/gates/migration → Task 6. All five review-focus risks have owning tests.

This plan is ready for user review. Implementation has not started, no tests have been represented as passing, and no execution model/backend has been selected by this document.
