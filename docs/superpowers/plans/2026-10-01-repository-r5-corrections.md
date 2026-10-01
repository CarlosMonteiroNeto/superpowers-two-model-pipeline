# Repository and R5 Corrections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox syntax for tracking. Do not use the Two Model Pipeline runner to coordinate this work.

**Goal:** Correct the gate, Codex runtime, and R5 reuse failures established by the repository review, with regression evidence for each correction.

**Architecture:** Keep the existing deterministic pipeline and immutable asset contracts. Repair the producer/consumer boundaries that disagree: Git diff inventory, graph-free gate decisions, operator session locators, process termination/reaping, current Flutter bindings, requirement dependencies, and staged payload verification. Avoid a new orchestration layer or broad schema rewrite.

**Tech Stack:** Python 3, unittest, SQLite, Git, Bash entrypoints, JSON manifests; native Linux and Windows process tests.

**Spec:** [Repository and R5 Corrections Specification](../specs/2026-10-01-repository-r5-corrections-design.md).

**Status:** Implemented locally and reviewed, with F3 integration proof incomplete and F4 still open pending native Linux evidence. Work remains uncommitted in the existing R5 worktree. This Markdown document is a native execution plan, not input to `run-pipeline`.

## Global Constraints

- Preserve user changes and the uncommitted R5 implementation; do not reset, clean, or switch an occupied checkout.
- Keep evidence validation, candidate binding, process ownership, and session identity checks intact.
- Keep baseline and closing verification on complete configured test suites.
- Preserve immutable asset history and adoption outcomes; do not solve recall failures by deleting historical assets.
- Keep corrections local; no remote publication, external skill installation, or live provider dispatch is part of this work.
- Use native development and focused regression tests; do not invoke the Two Model Pipeline runner to implement these corrections.
- Keep artifacts in English and communicate review results to the user in Portuguese.

## Execution baseline and file ownership

The reviewed main commit is `817da04e7d92983bb33cecdc38115b4babeceb7a`. R5 has the same HEAD but substantial uncommitted implementation in its existing worktree. Tasks 1–4 can be implemented against main-derived code; Tasks 5–7 require that R5 working state. A fresh worktree from the R5 branch name alone does **not** contain that implementation.

At execution start, recheck both worktree statuses, compare the R5 source inventory with the spec, and coordinate any active R5 writer before editing. Reuse a suitable isolated checkout containing the actual R5 work, or explicitly preserve/copy the required snapshot into an implementation checkout. Never assume the branch ref contains untracked files. Do not commit unrelated preexisting changes. Each task's commit checkpoint is local and requires reviewing the exact staged diff.

File responsibilities remain: `gate_evidence.py` captures Git/workspace evidence; `test_impact.py` selects verification; `toolchain_gate.py` enforces execution contracts; dispatch/caller scripts bridge session IDs; `codex_process.py` owns process lifecycle; Flutter wrappers select current bindings; `requirement_profiles.py` resolves requirements; `template_promotion.py` owns local staging integrity.

## Review Focus

- Renamed-away tests and Windows paths must not become executable selectors — Task 1.
- Graph-free test edits must not weaken production-change or closing validation — Task 2.
- Parent-task session pointers must not cross a different task's identity boundary — Task 3.
- Historical catalog rows must neither break current recall nor lose adoption outcomes — Task 5.
- Path aliases, case collisions, and concurrent stage retries must preserve physical payload bytes — Task 7.

## Task 1: Normalize rename inventory at the Git boundary (F1)

**Files:** Modify `skills/two-model-sdd-pipeline/scripts/gate_evidence.py` and, if needed for renamed tests, `test_impact.py` in the same directory. Extend `skills/two-model-sdd-pipeline/tests/test_r4_impact_gate_wiring.py` and `test_r4_test_impact.py`.

**Interfaces:** Preserve `capture_workspace_inputs(workspace: str, selection: list[str], mode: str) -> dict`. Its `files` retains rename endpoints; `test_paths` contains current executable test files. Consumers continue using the existing manifest schema.

- [ ] Add `test_git_rename_capture_uses_existing_destination`: use a real temporary Git repository, commit `test_app.py`, run `git mv test_app.py test_renamed.py`, and capture task inputs through a valid plan/ledger fixture. Assert:

  ```python
  self.assertIn("test_renamed.py", captured["diff"]["test_paths"])
  self.assertNotIn("test_app.py", captured["diff"]["test_paths"])
  self.assertEqual("renamed", captured["files"][0]["status"])
  ```

- [ ] Add source rename, rename-with-edits, deletion, and space-containing filename variants. For the test rename, run the resulting selection through gate execution and assert the old path is never passed to the test process.
- [ ] Run `python -B -m unittest discover -s skills/two-model-sdd-pipeline/tests -p test_r4_impact_gate_wiring.py -v`. Confirm the new rename capture case fails with the current `KeyError: 'path'`; classify any unrelated failure before proceeding.
- [ ] Replace status-agnostic path access with explicit current-path handling. Preserve old/new endpoints for impact traversal. Broaden renamed-test verification when necessary rather than selecting absent source paths.
- [ ] Rerun that command and `python -B -m unittest discover -s skills/two-model-sdd-pipeline/tests -p test_r4_test_impact.py -v`; require zero failures.
- [ ] Review the scoped diff and create the local commit `fix(impact): handle Git renames in workspace capture`.

## Task 2: Make graph-free test edits executable (F2)

**Dependencies:** Task 1 for the rename acceptance case.

**Files:** Modify `skills/two-model-sdd-pipeline/scripts/test_impact.py`; adjust `gate_evidence.py` only if producer wiring requires it. Extend `tests/test_r4_impact_preflight.py`, `test_r4_graphify_gate_execution.py`, and `test_r4_impact_gate_wiring.py` under the shared skill.

**Interfaces:** Preserve `preflight(diff: dict, toolchains: list, policy: dict, phase: str) -> dict`. For unsupported graph-free direct selection, the relevant `toolchain_reasons` entry must be a full-suite reason; `requires_graph` remains false when no production selection needs it. Preserve the executor's complete-graph requirement for affected commands.

- [ ] Add `test_test_only_edit_runs_full_command_without_graph`: commit a passing test, modify only that test, invoke `run-gates` with the real plan/ledger fixture, and assert successful execution, the exact configured full argv, and no graph builder calls.

  ```python
  self.assertEqual(0, result.returncode, result.stdout + result.stderr)
  self.assertTrue(manifest["commands"][0]["full_suite"])
  self.assertEqual(full_argv, manifest["commands"][0]["argv"])
  graph_builder.assert_not_called()
  ```

- [ ] Cover added, modified, deleted, and renamed tests; a mixed toolchain case; production edits without graph evidence; and baseline/closing phases. Preserve existing tampering rejection assertions.
- [ ] Run `python -B -m unittest discover -s skills/two-model-sdd-pipeline/tests -p test_r4_graphify_gate_execution.py -v`. Verify the new test-only case fails because the current affected manifest is rejected, not because a fixture command is missing.
- [ ] Add the explicit full-suite preflight fallback for direct-test cases without a supported proof. Do not set `graph_provenance.complete=True` without extraction and do not remove executor validation.
- [ ] Rerun the three named test modules with unittest discovery; require zero failures, explicit executed-command evidence, and no added graph extraction for test-only work.
- [ ] Review and commit `fix(impact): execute graph-free test changes conservatively`.

## Task 3: Bridge Codex operator session persistence and correction callers (F3)

**Files:** Modify `skills/two-model-sdd-pipeline/scripts/dispatch-codex`, `task-run`, and `coder-gate` only where required; use `codex_sessions.py` for identity-bound storage. Extend `tests/test_codex_resume_and_retry.py` and `test_codex_dispatch.py` under the shared skill; add `tests/test_codex_operator_session_handoff.py` there for caller integration.

**Interfaces:** Successful operator CLI dispatch publishes `workspace/task-{task_id}-{agent}-session.txt` atomically with its completed session ID. That file is only a locator. Existing `codex_dispatch.run_dispatch(request, runtime)` validates every resumed identity and remains the authority. New corrective task IDs start fresh for Codex under the current contract.

- [ ] Add a fake-runtime CLI integration test `test_same_task_correction_resumes_persisted_operator`: first dispatch creates a known session ID, then exercise the real same-task correction caller and inspect the next recorded request/argv.

  ```python
  self.assertEqual("session-operator-1", pointer.read_text().strip())
  self.assertEqual("session-operator-1", resumed_session_id)
  self.assertEqual(first_identity, resumed_identity)
  ```

- [ ] Add failure/no-pointer, changed run/model/config/worktree, new corrective task ID, and missing-pointer cases. Assert mismatch rejection before process launch and fresh context for the new task; do not weaken identity matching to make a fixture pass.
- [ ] Run `python -B -m unittest discover -s skills/two-model-sdd-pipeline/tests -p test_codex_operator_session_handoff.py -v`; confirm RED at the missing pointer or missing resume, using no live provider.
- [ ] Publish the pointer only after successful verified dispatch and durable session storage. Keep same-task continuation explicit. Prevent `task-run` from forwarding a parent's Codex session to a newly numbered corrective task.
- [ ] Rerun the new test and the two existing modules; require zero failures and proof the fake runtime saw an explicit matching session ID.
- [ ] Review and commit `fix(codex): preserve operator sessions across same-task corrections`.

## Task 4: Reap direct children during bounded termination (F4)

**Files:** Modify `skills/two-model-sdd-pipeline/scripts/codex_process.py` and affected `run_control.py` callers. Extend `tests/test_codex_process_ownership.py` and add `tests/test_codex_process_timeout.py` under the shared skill.

**Interfaces:** Preserve `run_owned(argv, cwd, stdin_text="", timeout=None, env=None, on_start=None) -> dict` and its `timed_out`, `stdout`, `stderr` fields. Preserve `stop_owned_processes(records, grace_seconds)` for externally recorded ownership. Add a private direct-child cleanup helper accepting both the owned `Popen` and ownership identity, so waiting/reaping does not apply to arbitrary PIDs.

- [ ] On Linux, add `test_real_timeout_reaps_child_and_preserves_output`: launch `sys.executable -u -c` to print distinct stdout/stderr markers then sleep for 30 seconds, and use a 0.5-second capture timeout.

  ```python
  self.assertTrue(result["timed_out"])
  self.assertIn("TIMEOUT-STDOUT", result["stdout"])
  self.assertIn("TIMEOUT-STDERR", result["stderr"])
  self.assertIsNone(subject._start_identity(result["pid"]))
  ```

- [ ] Run `python -B -m unittest discover -s skills/two-model-sdd-pipeline/tests -p test_codex_process_timeout.py -v` on Linux. Confirm the proposed unreaped-child failure. If it does not reproduce, investigate and revise F4 before implementation; a skipped Windows run does not satisfy this checkpoint.
- [ ] Add cases for process descendants, interrupted execution, `on_start` registration failure, and an ownership identity mismatch. Assert no unrelated PID is signaled and cleanup has finite waits.
- [ ] Implement termination followed by bounded direct-child reaping and output collection, preserving process-group and ownership protections. Keep external cancellation able to stop recorded processes without treating them as children of the current process.
- [ ] Run the new module and ownership tests on Linux and Windows; add a dispatcher fake-runtime test asserting timeout exit 124 and retained diagnostics. Require zero failures, no surviving test child, and no generic post-start replacement of timeout classification.
- [ ] Review and commit `fix(codex): reap owned children before termination verification`.

## Task 5: Recall only current Flutter bindings without deleting history (F5)

**Files:** Modify R5 `skills/flutter-app-pipeline/scripts/template_recall.py` and, if needed for explicit ID filtering, `skills/two-model-sdd-pipeline/scripts/asset_recall.py`. Extend `skills/two-model-sdd-pipeline/tests/test_r5_flutter_catalog_compatibility.py` and `test_r5_generic_recall.py`; extend Flutter `tests/test_template_recall_foundation.py`.

**Interfaces:** Preserve Flutter `recall(...) -> (status, rows)`. If shared filtering is used, add optional `query.asset_ids: list[str]` to `asset_recall.query_connection(conn, query)` with strict nonempty-string element validation; an empty list selects no assets. Filter before ranking and `top_n`. Without this field, generic history queries retain their existing behavior.

- [ ] Add `test_identity_update_recalls_current_binding`: create a fresh temporary database, upsert an AUTO_APPROVE template with SDK `>=3.0`, record an outcome, then upsert the same owner with SDK `>=3.2` and new evidence hash.

  ```python
  self.assertEqual("HIT", status)
  self.assertEqual([current_asset_id], [row["asset_id"] for row in rows])
  self.assertEqual(2, asset_count)
  self.assertEqual("used_successfully", old_outcomes[0]["outcome"])
  ```

- [ ] Add license-change, multiple-owner/top-N, reopen/migration, and broken-current-binding cases. A stale historical row must not abort recall; a missing referenced current asset must return `SETUP_ERROR`.
- [ ] Run `python -B -m unittest discover -s skills/two-model-sdd-pipeline/tests -p test_r5_flutter_catalog_compatibility.py -v`; confirm RED at `SETUP_ERROR` after the second upsert.
- [ ] Resolve and validate current bindings before query/ranking, then select only those IDs. Preserve old assets/outcomes and the generic query's ability to inspect history. Keep compatibility/license/evidence validation intact.
- [ ] Run the three named modules and `test_r5_catalog_migration.py` / `test_r5_refresh_parity.py` using unittest discovery; require zero failures and no history deletion.
- [ ] Review and commit `fix(reuse): scope Flutter recall to current asset bindings`.

## Task 6: Resolve requirement dependencies after exclusions (F6)

**Files:** Modify R5 `skills/two-model-sdd-pipeline/scripts/requirement_profiles.py`. Extend `tests/test_r5_requirement_profiles.py` and `test_r5_planning_reuse.py` under the shared skill. Document question output in `references/reusable-asset-planning.md` there.

**Interfaces:** Preserve `resolve(context: dict, profiles: list) -> dict`. Add question objects `{"type":"unresolved_dependency","requirement_id":str,"dependencies":list[str]}` and `{"type":"dependency_cycle","requirement_ids":list[str]}`. Sort IDs deterministically; exclude unresolved/cyclic requirements from `requirements`; preserve existing exceptions.

- [ ] Add `test_packaged_form_opt_out_blocks_dependent_mask` using the packaged profiles and reason `handled upstream` for `form-validation`.

  ```python
  self.assertNotIn("input-mask", [r["id"] for r in result["requirements"]])
  self.assertIn({"type": "unresolved_dependency", "requirement_id": "input-mask",
                 "dependencies": ["form-validation"]}, result["questions"])
  self.assertEqual("handled upstream", result["exceptions"][0]["reason"])
  ```

- [ ] Cover a dependency removed by profile conflict/applicability, unknown IDs, transitive chains, cycles, and reversed profile order. Assert every retained dependency is retained and no opt-out is silently undone.
- [ ] Run `python -B -m unittest discover -s skills/two-model-sdd-pipeline/tests -p test_r5_requirement_profiles.py -v`; confirm RED on the currently retained mask and absent question.
- [ ] Validate the graph after applicability/conflicts/opt-outs; identify cycles and propagate unavailable dependencies until stable. Emit the specified question shapes and deterministic ordering.
- [ ] Run both named modules; require zero failures and unchanged outputs for valid dependency-free profiles.
- [ ] Review and commit `fix(profiles): report unresolved requirement dependencies`.

## Task 7: Protect staging metadata and verify actual payloads (F7, F8)

**Files:** Modify R5 `skills/two-model-sdd-pipeline/scripts/template_promotion.py`; extend `tests/test_r5_promotion.py`; document reserved metadata and refusal behavior in `references/template-repository.md` under the shared skill.

**Interfaces:** Preserve `stage(request: dict, catalog: dict) -> dict`. Reject root metadata collisions as `status=blocked` before filesystem mutation. Existing targets return idempotent success only after exact metadata/inventory/byte validation; any divergent target returns `status=overwrite_refused`. Reuse one private target-verification helper in both ordinary and concurrent-target paths.

- [ ] Add `test_release_metadata_collision_is_blocked_before_writes` with a caller `release.json` payload; assert blocked status and absence of a stage directory. Add normalized aliases, case variants, duplicate physical destinations, and `release.json/child` conflicts; define root reservation case-insensitively for portable behavior.
- [ ] Run `python -B -m unittest discover -s skills/two-model-sdd-pipeline/tests -p test_r5_promotion.py -v`; confirm the new collision test currently fails because staging succeeds and overwrites payload bytes.
- [ ] Validate raw and canonical path components before staging. Reject reserved/aliased/conflicting destinations; retain the existing layout for valid files and document the reservation.
- [ ] Add `test_idempotent_retry_refuses_modified_payload`: stage a valid request, change `README.md`, repeat it, and assert:

  ```python
  self.assertEqual("overwrite_refused", repeated["status"])
  self.assertEqual("locally changed", readme.read_text())
  ```

- [ ] Add deleted/extra-file, symlink, identical-target, and concurrent-winner cases. Assert returned payload matches physical bytes for valid stages and no refusal mutates the target. Use a platform-appropriate conditional skip only for unavailable symlink creation; require that case on Linux.
- [ ] Rerun the same command; classify RED at false idempotent success separately from the metadata collision correction.
- [ ] Verify exact metadata, relative regular-file inventory, containment, and UTF-8 payload bytes before reusing any target. Use the same verification after a concurrent target appears; distinguish that race from unrelated filesystem errors and do not overwrite the winner.
- [ ] Rerun promotion, template-repository, and ecosystem acceptance modules in the shared suite; require zero failures and verified payload equivalence.
- [ ] Review and commit `fix(reuse): preserve and verify promoted template payloads`.

## Task 8: Validate the combined snapshot and document outcomes

**Dependencies:** Tasks 1–7. No claim that F4 is complete without native Linux evidence.

**Files:** Update this plan and the spec with implementation/verification evidence; modify `skills/flutter-app-pipeline/tests/test_template_search.py` only for the observed test-server cleanup issue. Update README/runtime references only where the corrected public behavior changes their existing claims.

- [ ] Add `server_close()` to the test HTTP server shutdown lifecycle after thread shutdown/join, preserving cleanup if the fixture raises. Run the affected module with ResourceWarnings enabled and verify the observed unclosed-server warning is gone.
- [ ] Reinspect both source statuses and final diffs. Verify every F1–F8 acceptance row has a test, all R5 files are present in the chosen execution snapshot, and unrelated user work is excluded from commits.
- [ ] Run `python -B -m unittest discover -s skills/two-model-sdd-pipeline/tests -p 'test_*.py' -v` against the combined implementation. Investigate any failures before classifying them; require zero unexplained failures.
- [ ] Run `python -B -m unittest discover -s skills/flutter-app-pipeline/tests -p 'test_*.py' -v`. Require zero unexplained failures and preserved Flutter CLI behavior. These full-suite runs are implementation exit criteria; the review only ran the subsets recorded in the spec.
- [ ] Run the focused Linux lifecycle and symlink tests and the Windows ownership/CLI tests. Record counts, platform skips, duration, and exact source revision/snapshot. Do not substitute mocks for native termination evidence.
- [ ] Review the final branch as a whole, reconcile new findings, and record remaining limitations. Commit only reviewed correction/documentation files with `docs: record repository and R5 correction evidence` after checks pass.
- [ ] Deliver the final results and scoped diff to the user. No push, merge, deployment, or provider-based acceptance run is included.

## Coverage and order

| Finding | Implementation task | Main evidence boundary |
|---|---|---|
| F1 | 1 | Real Git diff to manifest inventory |
| F2 | 2 | Preflight to manifest to actual gate command |
| F3 | 3 | Successful fake dispatch to next correction invocation |
| F4 | 4 | Native process termination, reaping, and timeout classification |
| F5 | 5 | SQLite identity update to public Flutter recall |
| F6 | 6 | Packaged profiles and opt-outs to actionable requirements |
| F7 | 7 | Payload path validation before stage writes |
| F8 | 7 | Existing physical stage to idempotence verdict |

Recommended execution order is Tasks 1–2, then 5–7 to address active R5 work, then 3–4 and final validation. Tasks 3–7 are independent of the gate fix except for final combined verification. If a Linux runner is unavailable, complete the independent tasks but keep F4 explicitly open.

## Local execution evidence (2026-10-01)

- Worktree: `codex/r5-reuse-foundation`, based on `817da04`; no commit created. The existing uncommitted R5 implementation and other local work were preserved.
- F1/F2: rename capture and graph-free test full-suite fallback implemented with focused regressions; relevant R4 impact/gate tests passed as part of the shared suite.
- F3: operator session locator publication and new-corrective-task identity guard implemented. Focused dispatch/resume/corrective tests pass, but the plan's requested fake-runtime same-task caller integration test was not added; keep this acceptance partially open.
- Review correction: the first focused code review found that an untrusted agent name could traverse out of the workspace when constructing the session locator. Locator publication now accepts only the `two-model-coder` name and safe alphanumeric/underscore suffixes; the regression rejects path separators. `test_codex_dispatch.py` passed (15 tests) after this fix.
- F4: direct-child cleanup/reaping helper implemented and Windows timeout/ownership tests pass. Native Linux verification is unavailable on this host (WSL has no installed distribution); keep F4 open. Do not claim platform acceptance.
- F5–F8: current Flutter binding recall, dependency closure/questions, staged payload collision and physical-byte checks, plus HTTP fixture `server_close()` were implemented with focused regressions.
- Full shared suite: `python -B -m unittest discover -s skills/two-model-sdd-pipeline/tests -p 'test_*.py' -v` — 1,181 passed, 2 skipped, 0 failed (2,585.558 seconds).
- Full Flutter suite: `python -B -W error::ResourceWarning -m unittest discover -s skills/flutter-app-pipeline/tests -p 'test_*.py' -v` — 152 passed, 0 failed (111.383 seconds).
- `git diff --check` completed without whitespace errors; Git reported only line-ending conversion warnings.
- No commits, push, PR, or remote publication were performed. The scoped review is complete; commit checkpoints are intentionally not performed per the user's request to keep the R5 worktree uncommitted.
