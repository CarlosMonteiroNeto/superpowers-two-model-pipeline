# R5 Generic Reuse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Follow the RED/GREEN/review cycle below; do not use the Two Model Pipeline runner or its orchestration scripts as the workflow.

**Goal:** Generalize reusable assets, applicable product requirement profiles, research, dependency preparation, and template adoption while preserving Flutter-specific behavior in adapters.

**Architecture:** Build ecosystem-neutral catalog, recall, requirement, repository, research, dependency, and adoption contracts in the shared skill. Keep registry scoring, Dart tooling, and Flutter UI behavior in Flutter adapters. Preserve existing Flutter command contracts through compatibility wrappers and use Python fixtures only to verify generic behavior, without claiming new ecosystem support.

**Tech Stack:** Python 3, `unittest`, JSON Schema, SQLite, shell entrypoints, Markdown skills and documentation, existing plugin packaging script.

**Spec:** [R5 round plan](2026-09-25-r5-reuse-foundation/plan.json), [transition design](../specs/2026-09-25-codex-pipeline-design.md), and [confirmed decisions](../specs/2026-09-25-confirmed-pipeline-decisions.md).

## Global Constraints

- R1–R4 are accepted; implementation baseline is `817da04e7d92983bb33cecdc38115b4babeceb7a`.
- Use the native Superpowers SDD workflow with RED/GREEN and focused review; never invoke the Two Model Pipeline runner, dispatcher, or orchestration scripts to coordinate implementation.
- Keep ecosystem-specific formulas and tooling in adapters. Generic fixtures do not claim production support for another ecosystem.
- Preserve evidence provenance, license/compatibility identity, local project changes, and existing public Flutter CLI behavior.
- Do not create or publish a remote repository, install external skills, automatically publish a template, or expose credentials/private project evidence.
- Changes remain local; no push or pull request is authorized.
- The requested Luna medium setting cannot be applied through the active session controls; do not claim it was used.

## Review Focus

- SQLite migration interruption or malformed prior state preserves the original database and backup — Task 2 migration rollback tests.
- Stale, malformed, or mismatched evidence cannot produce a recall/adoption hit — Tasks 2, 3, and 6 evidence identity tests.
- Unsafe paths, duplicate promotion, or local edits cannot overwrite project/template data — Task 5 repository and promotion tests.
- Concurrent dependency manifest claims cannot race past shared resource ownership — Task 6 dependency policy tests.
- Inapplicable or conflicting requirement profiles cannot silently add requirements — Task 4 applicability, opt-out, and conflict tests.

---

## Task 1: Audit Flutter stages and assign capability ownership — complete

**Files:** Create `docs/superpowers/reviews/flutter-stage-generalization.md`, `skills/two-model-sdd-pipeline/schemas/stage-capability.schema.json`, `skills/two-model-sdd-pipeline/stage-capabilities.json`, and `skills/two-model-sdd-pipeline/tests/test_r5_stage_inventory.py`.

**Interface:** The inventory records `stage/source/current_owner/disposition/target_owner/plan_task/evidence` for every Flutter phase 0–8, script, and caller. Dispositions are shared, Flutter-specific, or adaptation-required.

- [x] Write tests that require exhaustive source/caller coverage, valid schema references, an R5 task or accepted R1–R4 owner for every disposition, and no unsupported language-support claim.
- [x] Run `python -m unittest discover -s skills/two-model-sdd-pipeline/tests -p test_r5_stage_inventory.py -v`; confirm the expected failure while the inventory/schema/review are absent.
- [x] Read current Flutter skill and script entrypoints, then create the evidence-backed inventory and schema.
- [x] Rerun the focused test and validate the inventory covers every script in the Flutter pipeline directory.

## Task 2: Extract generic catalog and adoption contracts — complete

**Files:** Create shared `asset_catalog.py`, `asset-catalog`, `asset.schema.json`, and tests `test_r5_catalog_migration.py` / `test_r5_generic_catalog.py`; adapt Flutter `template_catalog.py`, `template-catalog`, and `template_evidence.py`.

**Interface:** `asset_catalog.upsert(database: str, evidence: dict) -> dict`; `asset_catalog.record_outcome(database: str, outcome: dict) -> dict`.

- [x] Add RED tests for ecosystem/name/version/source/license/evidence-hash/compatibility identity, derived metadata, separate adoption outcomes, transactional SQLite migration/backup rollback, and a Python fixture.
- [x] Run the focused tests and confirm failures at the absent shared API and missing migration behavior.
- [x] Implement generic persistence and adapt the Flutter wrappers without moving pub.dev scoring into the shared catalog.
- [x] Rerun focused tests and existing Flutter catalog/evidence/triage/recall/search checks; assert legacy CLI exit behavior and evidence invalidation remain intact.

## Task 3: Generalize deterministic recall and refresh — complete

**Files:** Create shared `asset_recall.py`, `asset-recall`, `asset-refresh`, and tests `test_r5_generic_recall.py` / `test_r5_refresh_parity.py`; adapt Flutter recall, refresh, embedding, suitability, and their command wrappers.

**Interface:** `asset_recall.query(database: str, query: dict) -> dict`; `asset_recall.refresh(database: str, evidence: dict) -> dict`.

- [x] Add RED coverage for freshness/compatibility filtering, dependency overlap, validated vector identity, valid MISS versus setup error, deterministic-only mode, and atomic refresh preservation on collection/validation failure.
- [x] Run focused tests and verify each fails at the intended missing generic behavior.
- [x] Implement deterministic shared recall; keep ecosystem evidence/scoring as adapters and preserve Jev Sites 1/2 boundaries.
- [x] Rerun focused tests plus existing Flutter recall, refresh, embedding, and suitability suites. Verify recall never downloads or adopts source.

## Task 4: Introduce applicable requirement profiles — complete

**Files:** Create `requirement_profiles.py`, `requirements-resolve`, `requirements-profile.schema.json`, `profiles/generic.json`, `profiles/user-interface.json`, `profiles/flutter-forms.json`, and `test_r5_requirement_profiles.py`.

**Interface:** `requirement_profiles.resolve(context: dict, profiles: list) -> dict` returning selected requirements, exceptions, and questions.

- [x] Add RED tests for deterministic generic-plus-overlay resolution, locale differences, non-UI applicability, opt-outs, conflicting overlays, absent client/server boundaries, and masks separated from validation.
- [x] Run the focused test and confirm the profile resolver/schema are missing.
- [x] Implement versioned profile identity, applicability, requirement IDs/checks/dependencies, explicit opt-out reasons, and conflict reporting.
- [x] Rerun focused tests and verify no auth/payment/analytics or country-specific rules are added without applicable product scope.

## Task 5: Build safe template repository and promotion workflows — complete

**Files:** Create `template_repository.py`, `template-repository`, `promote-template`, `template_promotion.py`, `template-release.schema.json`, `references/template-repository.md`, and tests `test_r5_template_repository.py` / `test_r5_promotion.py`.

**Interfaces:** `template_repository.preview_update(binding: dict, candidate: dict) -> dict`; `template_promotion.stage(request: dict, catalog: dict) -> dict`.

- [x] Add RED fixtures for immutable version binding, update previews/conflicts preserving local edits, safe staging exclusions, provenance/license/dependency verification, duplicate promotion idempotence, and overwrite refusal.
- [x] Run focused tests and confirm expected failures for missing repository and promotion contracts.
- [x] Implement path-safe local repository operations and staging manifests. Keep remote creation and publication out of automatic flows.
- [x] Rerun focused tests; verify fixtures use disposable local repositories and never publish.

## Task 6: Generalize research, dependency preparation, and adoption — complete

**Files:** Create `solution_research.py`, `solution-research`, `dependency_policy.py`, `dependency-prepare`, `template_adoption.py`, `template-adopt`, and tests `test_r5_shared_research.py`, `test_r5_dependency_policy.py`, `test_r5_template_adoption.py`; adapt the listed Flutter research, scoring, package-sync, and RTK entrypoints.

**Interfaces:** `solution_research.collect(request: dict, adapters: dict) -> dict`; `dependency_policy.evaluate(request: dict, evidence: dict) -> dict`; `template_adoption.prepare(request: dict, evidence: dict) -> dict`.

- [x] Add RED fixtures for evidence-backed alternatives/licenses/compatibility, automatic adoption only after technical checks, ambiguous/conflicting cases asking or blocking, approved manifest/lockfile grants, concurrent resource claims, and Flutter/Python behavior.
- [x] Run each focused test and confirm the shared contracts or adapter behavior is missing.
- [x] Implement shared research and policy orchestration while preserving pub.dev/GitHub scoring in Flutter adapters; coordinate existing manifest writes through the shared resource lock.
- [x] Rerun focused tests plus existing Flutter search/scoring/package-sync tests. Verify no extra dispatch is added for mechanical lookup and no secrets enter reports.

## Task 7: Integrate reuse into planning and packaging — complete

**Files:** Adapt `skills/brainstorming/SKILL.md`, `skills/writing-plans/SKILL.md`, both pipeline skills, `scripts/package-codex-plugin.sh`, and `README.md`; create archive reconciliation documentation and tests `test_r5_planning_reuse.py` / `test_r5_ecosystem_acceptance.py`.

- [x] Add RED fixtures for one Flutter planning flow and one Python flow, generic tooling without irrelevant UI profiles, installed-first skill discovery, consolidated applicable baseline summary, and external skill installation approval.
- [x] Run focused tests and confirm the planning/packaging flow does not resolve profiles or compatible assets as specified.
- [x] Integrate the documented reusable-asset flow and package generic plus ecosystem assets while retaining Flutter compatibility wrappers.
- [x] Rerun the focused tests, migration/adoption/update-conflict/provenance fixtures, complete shared suite, and complete Flutter suite. Record skips and limitations; do not report a clean closure if any new regression remains.

## Source of detailed acceptance

The companion [R5 plan JSON](2026-09-25-r5-reuse-foundation/plan.json) is authoritative for full acceptance statements, dependency ordering, schemas, and additional verification requirements. This Markdown plan supplies the normal SDD task sequence and RED/GREEN handoff; revise both artifacts together if source drift materially changes scope.
