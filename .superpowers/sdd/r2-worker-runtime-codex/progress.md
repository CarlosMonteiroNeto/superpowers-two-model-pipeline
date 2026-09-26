# SDD ledger — plan: .superpowers/sdd/plans/r2-worker-runtime-codex.md

## Execution context
- User requested implementation of R2 and R3 and clarified that both must be built on R1.
- Worktree: `.worktrees/r2-r3-sdd`; branch: `codex/r2-r3-sdd`.
- R1 base: `58810ac42b959b02529c73837e32ed7a8f757c79`.
- Direct user request authorizes implementation despite historical `implementation_authorized=false` metadata in the planning JSON; that field records the prior planning state.
- All development agents: `gpt-6-luna`, reasoning `max`.
- Scope: R2 only in this plan, local commits only; no publication or external side effects.
- Baseline: `python3 -m unittest discover -s skills/two-model-sdd-pipeline/tests -p 'test_foundation_*.py' -v` — 242 tests, 2 skipped, passed. Evidence: `.superpowers/sdd/r2-r3-sdd/baseline-foundation.txt`.

## Plan and execution decisions
- Canonical requirements remain `docs/superpowers/plans/2026-09-25-r2-worker-runtime/plan.json` and linked Codex design/confirmed-decision specs. This Markdown file is an execution mirror because the upstream Superpowers `task-brief` extracts Markdown `### Task N` sections; the pipeline runner will not be used.
- Source drift is checked against current R1 code before each task; canonical JSON remains authoritative for scope, interfaces, files, tests, and acceptance.
- Tasks execute sequentially. Within each task, controller-authored RED tests are committed before implementation dispatch; implementers do not edit those tests. Each task receives a separate implementation and review agent, then test-integrity and review-package checks.
- R2.6 and R3.6 share `README.md`, `scripts/package-codex-plugin.sh`, and `scripts/sync-to-codex-plugin.sh`; R3 waits for R2 completion, preventing concurrent edits.

## Dependency and interface scan
| Task | Depends on | Key outputs consumed downstream |
|---|---|---|
| 1 | — | Codex context package, scoped runner, toolchain evidence |
| 2 | — | Skill source registry and refresh |
| 3 | 1, 2 | Pinned skill manifest and adapted prompt headers |
| 4 | 1, 3 | Codex/OpenCode role policy and worker instructions |
| 5 | 1, 3, 4 | Backend adapters, session lifecycle, process ownership |
| 6 | 1–5 | Packaged workers and backend contract parity |

Exact task touch sets were checked against the canonical plans: no intra-R2 path collision requiring a sequencing change beyond the declared dependency order.

## Task status
- Task 1: approved (independent re-review accepted at `7f82848`)
- Task 2: active
- Task 3: pending
- Task 4: pending
- Task 5: pending
- Task 6: pending

Task 1 — RED phase
- Controller-authored RED tests are committed at `94819d80e6fbe668b40a5944032653c1f0804f6f`; implementation BASE is this commit.
- Exact RED command: `python3 -m unittest discover -s skills/two-model-sdd-pipeline/tests -p 'test_codex_*.py' -v`.
- Result: 13 tests executed, 13 failures, 0 errors. Evidence is `.superpowers/sdd/r2-worker-runtime-codex/task-1-red.txt`.
- Behavior-specific findings: R1 brief still hard-codes the Flutter RTK runner; `resolve-toolchain` guesses `npm test` and `npx eslint` for an empty package manifest and records the guess; `red-form-check` rejects valid unittest evidence as unsupported. Required R2.1 modules and `scoped-run` are also absent, so their interface assertions fail normally rather than as test collection errors.
- Test files are controller-owned and must remain byte-identical during implementation: `skills/two-model-sdd-pipeline/tests/test_codex_context_package.py`, `skills/two-model-sdd-pipeline/tests/test_codex_scoped_runner.py`, `skills/two-model-sdd-pipeline/tests/test_codex_toolchain_evidence.py`.

Task 1 — RED contract correction before dispatch
- Review found the original path-traversal test incorrectly prohibited echoing the rejected path in a diagnostic. It now checks that the runner identifies mode/argument/path rejection without constraining whether the diagnostic includes that path.
- Re-ran the exact RED command after the correction: 13 tests, 13 failures, 0 errors. Updated evidence: `.superpowers/sdd/r2-worker-runtime-codex/task-1-red.txt`.
- New implementation BASE: `8abf5c207c42e332d6da669fccbb4f5ef9ba867d`; both RED test commits are before this BASE.

Task 1 — regression RED extensions
- Scope review found R1 regression tests hard-coded the Flutter `rtk-run` and the first/last/language-based multi-toolchain selection. Updated the existing tests in a controller-authored commit to pin the R2.1 backend-neutral runner, explicit task identity, fail-closed unknown identity, and no guessed npm/eslint fallback.
- New regression REDs: `test_brief_scaffold.py` — 1 failing test (the non-Flutter brief still points at Flutter); `test_toolchain_wiring.py` — 10 failures and 2 passes (resolver still guesses Node commands, task identity is ignored, and missing/unknown IDs fall back to the last record). Logs: `.superpowers/sdd/r2-worker-runtime-codex/task-1-existing-brief-red.txt` and `task-1-existing-toolchain-red.txt`.
- The required R2.1 suite still runs 13 tests with 13 expected failures and no collection errors. The exact task-ID resolver contract is also covered when two Python toolchains share a language.
- New implementation BASE: `8faeda0fa94d19de87c00541b338eed069e876b1`.
- All controller-owned RED/regression tests are immutable to the implementer: `test_codex_context_package.py`, `test_codex_scoped_runner.py`, `test_codex_toolchain_evidence.py`, `test_brief_scaffold.py`, and `test_toolchain_wiring.py` under `skills/two-model-sdd-pipeline/tests/`.

Task 1 — GREEN audit follow-up (controller-owned RED)
- Smoke and first named suites were GREEN, but self-review of the unittest parser found a case where `unittest.loader._FailedTest` (import/collection failure) could be treated as an executed failing test.
- Added `test_unittest_import_collection_error_is_not_an_executed_test` to `test_codex_toolchain_evidence.py` and ran it before implementation: 1 test, 1 assertion failure because `_FailedTest` appeared in `executed_tests`. Raw output: `.superpowers/sdd/r2-worker-runtime-codex/task-1-red-collection.txt`.
- Test-only commit/new implementation BASE: `2edb566ed0f15fbda890f9a2da232aa046df5be7`. Implementer was told to change only production parser/validator and rerun the named suite. Task 1 remains pending review and independent verification.

Task 1 — independent review findings and second RED cycle
- Reviewer rejected `7e4f043` after verifying these integration gaps: command summaries are JSON argv strings that existing gates truncate/split incorrectly; `task-lang` now returns toolchain IDs but some callers use that as a language; `red-form-check` legacy fallback can approve unbound unittest evidence/collection failures; and `resolve_cli` raises `KeyError` when analyzer is absent.
- `agent/two-model-coder.md` does not allow the new scoped runner, but role-policy ownership is R2.4. This finding is explicitly deferred to Task 4; no policy file is edited in Task 1.
- Controller-authored tests were expanded and committed before the correction: `ffb74b4bbd5486645efca78cf03e6327dca62365`. RED evidence is in `task-1-red-callers.txt`, `task-1-red-evidence-followup.txt`, and `task-1-red-toolchain-followup.txt`. The runner success contract now persistently verifies cwd, env, output capture, exit status, and attempt-bound unittest evidence.
- Follow-up implementer must not edit tests. Task 1 remains pending until follow-up tests/regressions pass and the independent review approves the integrated result.

Task 1 — integrated correction and closure review
- Added controller-owned closing/integration coverage in commits `b5852c4` and `a77deab`; implementation test BASE is `a77deab`. Recorded pre-correction REDs for `final-gate` and multi-toolchain `integrate` in `task-1-red-final-closing.txt` and `task-1-red-integrate-gates.txt`.
- Corrective implementation commit: `c6ecc77` (`fix(r2.1): integrate scoped toolchain contracts`). It adds `task-toolchain` and `toolchain_gate.py`; restores `task-lang` as language resolution through the exact task-selected descriptor; removes command extraction/splitting from coder, final, and integration gates; executes descriptor argv/cwd/env through `cmd`; records analyzer absence; preserves the single unstructured legacy gate path; and rejects unavailable descriptors.
- The corrective compatibility work also changes existing consumers outside the original Task 1 file list: `coder-gate`, `red-gate`, `orchestrator`, `run-gates`, `final-gate`, and `integrate`. These paths were required to satisfy Task 1's exact toolchain/argv acceptance with the R1 callers. Role policy remains deferred to Task 4.
- GREEN results on the candidate: required `test_codex_*.py` 18/18; `test_r2_task1_pipeline_compatibility.py` 5/5; `test_brief_scaffold.py` 13/13; `test_toolchain_wiring.py` 13/13; `test_red_form_check.py` 11/11; `test_cmd_runner.py` 14/14; `test_coder_gate.py` 22/22; `test_orchestrator.py` 10/10; `test_final_gate.py` 18/18; `test_integrate.py` 18/18; `test_integrate_dirty_guard.py` 9/9; `test_run_pipeline.py` 17/17; and `py_compile` on changed R2.1 Python modules. The configured regression checks distinguish absent Go runtime as unavailable; no live Flutter/pytest/Go provider execution is claimed.
- `test-integrity a77deab c6ecc77` reports all seven controller-owned RED files unchanged. Review package: `review-a77deab..c6ecc77.diff`.
- Current Task 1 status: candidate committed and GREEN, independent follow-up review pending. Do not begin Task 2 until the review accepts or any review findings receive another RED/GREEN cycle.

Task 1 — second independent review and closure cycle
- The follow-up reviewer rejected `c6ecc77` with five findings: unbound RED fallback, unavailable descriptor revalidation, integration fallback from missing exact identity to structured Flutter, duplicate same-ID records from Python marker pairs, and legacy `run-gates` modes accepting structured/unmatched caller commands.
- Controller-owned RED tests were committed in `2ad3975` before corrective production code. They reproduced the unbound evidence, unavailable descriptor execution, duplicate records, integration bypass, caller-command execution, and two-argument `--toolchains` misrouting. RED counts: 2 in toolchain evidence, 1 in scoped runner, 1 in toolchain wiring, 1 in integration, and 3 in run-gates. Existing adapter fixtures were converted to attempt-bound envelopes in that test commit.
- Existing legacy integration fixtures initially omitted task IDs from their plans. Corrected them to model pre-R2 plans with task IDs but no toolchain IDs and a single unstructured gate (`c3e6a45`, `04d86e9`). The structured Flutter missing-ID regression remains fail-closed.
- Tightened existing coder-gate fixtures to write attempt-bound Go JSON evidence (`8f99e26`). The first broad coder-gate run was terminated after its temporary test workspace showed repeated retries against raw legacy evidence; the five affected cases then passed, and the complete coder-gate suite passed 22/22.
- Corrective production commit: `ee83ef4` (`fix(r2.1): enforce evidence and toolchain identity`). `red-form-check` now requires the current attempt manifest and matching adapter; unavailable toolchains stay unavailable in scoped-run; `resolve-toolchain --all` deduplicates IDs; integration permits fallback only for a verified single unstructured legacy gate; run-gates requires exact IDs for structured descriptors and rejects unmatched commands. The two-argument wrapper now preserves explicit `--toolchains` / `--tasks` modes.
- Verification passed: foundation baseline 242 tests (2 skipped); Codex/context 21; scoped-run 6; red-form-check 11; toolchain wiring 14; run-gates/cmd 17; coder-gate 22; orchestrator 10; final-gate 18; integrate 19; dirty guard 9; run-pipeline 17; compatibility 5; brief scaffold 13; Python and Bash syntax checks. The two dirty-guard tests affected by the legacy-plan fixture change were rerun individually, then all 9 passed.
- Test integrity: `test-integrity 8f99e26 ee83ef4` reports all nine controller-owned test files unchanged. Review package: `.superpowers/sdd/r2-worker-runtime-codex/review-c6ecc77..ee83ef4.diff`.
- Current Task 1 status: corrective commit is GREEN and awaiting independent re-review. Do not begin Task 2 until acceptance or another RED/GREEN cycle.

Task 1 — third independent review and closure cycle
- Re-review of `ee83ef4` confirmed the five earlier findings were closed, then found two remaining issues: Python descriptors with the `unittest` RED adapter were rejected, and structured Flutter toolchains bypassed their selected descriptors in coder/integration gates.
- Controller RED for Python/unittest was added in `7ca80ba`; after the test failed, `red-form-check` allowed the Python/unittest adapter pair. The Codex/context suite passed 21/21 and `test_red_form_check.py` passed 11/11.
- Controller REDs for descriptor routing were committed in `2510bf8` and `1f99909`. Both failed before the fix because the selected test/analyze commands did not execute. `7c8e4d5` routes exact structured Flutter toolchains through `run-gates`, preserves Flutter formatting and coder commit behavior, and retains the Flutter gate only for unstructured legacy plans. The fix passed `test_coder_gate.py` 23/23, `test_integrate.py` 20/20, and `test_integrate_dirty_guard.py` 9/9; Codex/context 21/21 and toolchain wiring 14/14 also passed.
- A subsequent review found that the attempt manifest's `adapter` field was not compared to the evidence envelope. The controller RED in `1ccbae5` reproduced acceptance of a pytest envelope for a unittest attempt. `5983e18` added `adapter` to the required evidence identity and attempt-manifest comparison. GREEN: `test_coder_gate.py` 23/23, `test_codex_*.py` 22/22, and `test_red_form_check.py` 11/11; Python compilation and Bash syntax checks passed.
- Test integrity: `test-integrity 1ccbae5 5983e18` reports the three affected controller-owned test files unchanged during implementation. Re-review package: `.superpowers/sdd/r2-worker-runtime-codex/review-ee83ef4..5983e18.diff`.
- Current Task 1 status: implementation and named regressions are GREEN; independent re-review is pending. Do not begin Task 2 until approval or another finding receives a RED/GREEN cycle.

Task 1 — fourth independent review and closure cycle
- Re-review of `ee83ef4..5983e18` confirmed the earlier issues were closed and found two more P2 issues: structured Flutter skipped its configured `format` command, and an inherited `flutter_green_gate=1` could suppress structured coder commit/reviewer dispatch.
- Controller REDs were added and committed at `f0ea1d3`; both failed before implementation. The formatter did not run, and the inherited variable caused a passing coder gate to exit without a commit.
- `02e1804` adds exact-ID `run-gates --format` execution for structured toolchains and resets the legacy-gate state at the start of every coder attempt. Unstructured Flutter retains the existing Dart formatter and Flutter gate path.
- GREEN verification: `test_coder_gate.py` 24/24; `test_integrate.py` 20/20; `test_toolchain_wiring.py` 14/14. The structured formatter and inherited-environment regressions pass. Bash syntax, Python compilation, `git diff --check`, and `test-integrity f0ea1d3 02e1804` passed.
- Re-review package: `.superpowers/sdd/r2-worker-runtime-codex/review-ee83ef4..02e1804.diff`. Review guidance fell back to standard guidance because `TYPESAFE_API_KEY` is unavailable; the package itself was generated completely.
- Current Task 1 status: implementation and named regressions are GREEN; independent re-review is pending. Do not begin Task 2 until approval or another finding receives a RED/GREEN cycle.

Task 1 — fifth independent review and closure cycle
- Re-review of `02e1804` found a P2 mixed-task legacy fallback: selecting a plan task without an explicit `toolchain_id` could run one legacy gate even when another selected task was structured.
- Added the controller-owned regression at `ac4968b`; it failed before the fix because `run-gates --tasks 1 2` returned success and wrote the legacy-gate marker for a mixed selection.
- `3961c65` restricts fallback to selections where every selected plan task exists exactly once and has no explicit toolchain ID. Missing/corrupt plans, missing/duplicate task IDs, or any structured task fail closed; the absent-plan legacy fallback remains compatible.
- GREEN: focused mixed-selection test passed; complete `test_toolchain_wiring.py` passed 15/15; `py_compile` and `git diff --check` passed. `test-integrity ac4968b 3961c65` confirms the controller-owned test file is unchanged.
- Re-review package: `.superpowers/sdd/r2-worker-runtime-codex/review-02e1804..3961c65.diff`; optional review guidance fell back to standard review because the classifier circuit is open.
- Current Task 1 status: GREEN; independent re-review found a malformed identity follow-up; another RED/GREEN cycle follows.

Task 1 — sixth independent review and closure cycle
- Re-review found a P2 edge case where a non-string `toolchain_id` (for example, `42`) was treated like a legacy task and could run the sole unstructured gate.
- Controller-owned RED test was committed in `06a8333` and failed before implementation because the legacy marker was written and `run-gates` returned success.
- `7f82848` allows legacy fallback only when each selected task's ID field is absent, null, or an empty string; any present malformed/non-string value or nonempty string fails closed.
- GREEN: focused malformed-identity test passed; complete `test_toolchain_wiring.py` passed 16/16; Python compilation, diff check, and `test-integrity 06a8333 7f82848` passed.
- Re-review package: `.superpowers/sdd/r2-worker-runtime-codex/review-02e1804..7f82848.diff`; optional guidance used standard review because the classifier circuit is open.
- Current Task 1 status: GREEN; independent re-review pending. Do not begin Task 2 until approval or any new finding receives a RED/GREEN cycle.

Task 1 — closure
- Independent re-review of `02e1804..7f82848` approved the mixed-selection fallback fix, malformed identity rejection, and legacy compatibility; no actionable regressions found.
- Task 1 is approved. Task 2 begins on the same R1-based branch at `7f82848`.

Task 2 — discovery design handoff
- Canonical acceptance and interface were read from `plan.json` and the task brief. Search installed skills first, consult the persisted query/source registry for gaps, and query external GitHub sources only when cached coverage is missing or expired.
- Seeded publisher/catalog entries are candidates only. Registry refresh stores provenance/revision/check status and never executes or trusts linked skill code. External installation remains a user-approved action for a later consumer.
- The GitHub REST repository-search path is query-scoped, sorted by stars, capped at 100 relevant repositories, and records its exact query and scope; no global exhaustive ranking claim is made.
- Controller-owned RED tests will be committed before the two implementation modules and command wrappers.

Task 2 — RED and implementation cycle
- Controller-owned tests were committed before the implementation in `2232351`; a follow-up test covers recommendation checks in `4ef8998`, and the fixtures now reject unsimulated network access in `0bc7bb3`.
- Behavior-specific RED in `9c156b3`: a fresh registry held a relevant skill, but `discover` still called GitHub. The test failed because the external request occurred instead of returning the registered skill.
- The implementation adds `skill_sources.py`, refresh/search CLIs, the JSON Schema, and decision-record seed candidates. It stores query scope and timestamps, reads installed skills then registered metadata, searches only remaining topic gaps, and preserves stale results on network/rate-limit failure.
- Named GREEN: `python3 -m unittest discover -s skills/two-model-sdd-pipeline/tests -p 'test_r2_skill_*.py' -v` — 11 tests passed. CLI help and installed-first smoke passed without network; Python compilation, seed/schema JSON parsing, and `git diff --check` passed.
- The first full suite stopped at a legacy R1 end-to-end fixture that lacked R2.1 attempt identity; its fixture migration was committed in `5b9838f` and `943f052`, and the focused recovery and coder-commit suites passed. A later full-suite run against `802bd8a` was intentionally interrupted after independent review found additional issues; it is not a passing result.

Task 2 — third independent-review correction cycle
- Independent review of `802bd8a` found four P2 defects: catalog links could downgrade an existing source and replace its inventory; selected-only refresh could mark unselected sources fresh; case-folded skill-path keys could mix distinct Git paths; and source-level license refresh could erase a per-skill `null` or override.
- Added controller-owned tests for these four behaviors in `test_r2_skill_source_refresh.py` before changing implementation. RED evidence: `.superpowers/sdd/r2-worker-runtime-codex/task-2-review-round3-red.txt` — 12 tests ran and exactly the four new tests failed with the expected value mismatches.
- A focused gap check then exposed that the prior test did not prove `_refresh_if_due` ignores a fresh global timestamp when a source itself is expired. Added a separate controller-owned test and observed its RED (`old-revision` returned instead of `fresh-revision`); evidence is `.superpowers/sdd/r2-worker-runtime-codex/task-2-review-round3-refresh-red.txt`.
- Implementation is committed separately after the REDs. Catalog link merges now preserve source category, metadata, inventory, and decisions; path identities are case-sensitive; explicit unknown or distinct per-skill licenses survive refresh; and partial refreshes remain stale without moving the registry-wide refresh time. `_refresh_if_due` also checks individual source timestamps and incomplete status before trusting the global timestamp.
- GREEN: `python3 -m unittest discover -s skills/two-model-sdd-pipeline/tests -p 'test_r2_*.py' -v` — 28 tests passed. Evidence: `.superpowers/sdd/r2-worker-runtime-codex/task-2-review-round3-green.txt`. Python compilation and `git diff --check` passed. Test-integrity and independent re-review are pending; do not advance Task 3 until approval.

Task 2 — fourth independent-review correction cycle
- Re-review approved the prior four fixes but found one remaining catalog-link edge case: when a link points at an already registered skill without supplying license metadata, merge could replace the existing skill license with `null`.
- Added `test_catalog_link_without_license_preserves_registered_skill_license` and observed the intended RED (`None` returned instead of the registered MIT license). Evidence: `.superpowers/sdd/r2-worker-runtime-codex/task-2-review-round4-red.txt`.
- This latest finding remains open until its GREEN test and independent re-review; Task 3 remains blocked on Task 2 approval.
