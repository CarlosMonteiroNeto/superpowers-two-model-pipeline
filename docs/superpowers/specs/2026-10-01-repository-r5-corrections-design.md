# Repository and R5 Corrections Specification

Date: 2026-10-01. Status: implemented locally in the R5 worktree; F3 caller integration proof and F4 native Linux acceptance remain open. See the execution evidence in the companion plan.

## Purpose and reviewed state

Correct concrete failures found during a general repository review, including the unfinished R5 reuse work. Deliver this specification and its [implementation plan](../plans/2026-10-01-repository-r5-corrections.md); do not treat their creation as implementation, merge, or publication approval.

- Main checkout: `C:/Users/Carlos_Neto/superpowers-two-model-pipeline`, branch `main`, commit `817da04e7d92983bb33cecdc38115b4babeceb7a`.
- R5 checkout: `C:/Users/Carlos_Neto/.codex/worktrees/r5-reuse-foundation/superpowers-two-model-pipeline`, branch `codex/r5-reuse-foundation`, same HEAD. Its implementation is in tracked modifications and untracked files, not a committed branch diff. Review included those files.
- R5 changed/untracked `skills/` and `scripts/` inventory: 57 files, aggregate SHA-256 `e42ca15c561b184914f293a50b5a353619ccb0a49bee63c8b5999fd759a40117`. Computed over sorted relative paths, each followed by NUL and the binary SHA-256 of file bytes. This is a snapshot identifier, not a commit or release hash.
- `codex/jev-lock-race` was initially inspected as the newest branch, but the user clarified that R5 is the intended branch. Jev branch approval is outside this deliverable.
- Existing local documentation, plans, runtime artifacts, and R5 implementation were preserved. Source references below are relative to the applicable checkout and reflect this review snapshot.

Investigation covered gate selection/evidence/cache boundaries, Codex process/session call chains, the R5 catalog/recall/profile/research contracts, template staging/adoption/update code, dependency coordination, Flutter compatibility changes, associated tests and recent history. This is a risk-focused review, not a claim that every repository file or live provider integration was verified.

## Constraints

- Preserve user changes and the uncommitted R5 implementation; do not reset, clean, or switch an occupied checkout.
- Keep evidence validation, candidate binding, process ownership, and session identity checks intact.
- Keep baseline and closing verification on complete configured test suites.
- Preserve immutable asset history and adoption outcomes; do not solve recall failures by deleting historical assets.
- Keep corrections local; no remote publication, external skill installation, or live provider dispatch is part of this work.
- Use native development and focused regression tests; do not invoke the Two Model Pipeline runner to implement these corrections.
- Keep artifacts in English and communicate review results to the user in Portuguese.

## Findings

### F1 — P2: Git renames crash impact capture

**Location:** main `skills/two-model-sdd-pipeline/scripts/gate_evidence.py:486-488`, `capture_workspace_inputs`.

**Trigger and evidence:** In a disposable Git repository, commit `test_app.py`, run `git mv test_app.py test_renamed.py`, then capture task inputs. The actual capture raises `KeyError: 'path'`. A separate mock-based probe produced the same result.

**Cause:** Rename records contain `old_path` and `new_path`. The inventory comprehension accesses `item["path"]` for every non-deleted record before reaching the separate rename comprehension. Selector-level rename tests bypass this producer and therefore pass.

**Required behavior:** Handle each diff status explicitly. A rename contributes the existing destination to the current file inventory and preserves both endpoints in the change evidence. Deleted and renamed-away tests must never be executed as existing selectors. Rename-related uncertainty must expand to the full suite, not crash or omit verification.

**Acceptance:** Real Git fixtures cover source rename, test rename, rename with edits, deletion, and spaces in filenames. Capture succeeds, identities remain candidate-bound, and the executor never receives the nonexistent old test path.

### F2 — P1: Test-only edits produce a manifest rejected by the executor

**Locations:** main `gate_evidence.py:535-546`, `test_impact.py:preflight`, and `toolchain_gate.py:314-315` under `skills/two-model-sdd-pipeline/scripts/`.

**Trigger and evidence:** Modify only an existing `test_app.py` in a real Git fixture. Manifest creation returns `mode=affected` with `graph_provenance.complete=False`; `_impact_test_argv` then raises `GateContractError: impact manifest cannot prove a complete affected selection` before executing the test.

**Cause:** Preflight correctly decides that a direct test edit does not require graph extraction, but the consumer requires a complete graph for every affected selection. Producer and consumer disagree. This interrupts ordinary test-only and TDD work.

**Chosen correction:** When graph-free direct-test selection lacks a consumer-supported proof, preflight emits a full-suite decision with an explicit reason. Keep graph extraction skipped, execute the original full command, and retain the current strict validation for graph-dependent affected selections. This bounded fix avoids inventing a second proof protocol.

**Alternatives:** Adding a sealed direct-selection evidence type could retain narrower execution, but expands the manifest/validator contract and is deferred. Merely dropping the graph completeness check is rejected because it weakens production-change validation.

**Acceptance:** Added and modified tests execute successfully through `run-gates` without Graphify. Deleted/renamed tests use safe complete verification. Missing graphs for production changes still fall back, tampered manifests remain rejected, and baseline/closing always use the full command.

### F3 — P2: Codex operator correction callers cannot find saved sessions

**Locations:** main `dispatch-codex:122-145`, `coder-gate:487-520`, and `task-run:343-354,377-417` under `skills/two-model-sdd-pipeline/scripts/`.

**Evidence level:** Static call-chain verification. Both correction callers read `task-N-<agent>-session.txt`; `dispatch-opencode` writes this pointer but `dispatch-codex` does not. Codex saves its identity-bound JSON session separately. No live provider call was made.

**Impact:** Normal same-task corrections use fresh context despite an available completed operator session, losing useful context and adding avoidable token cost.

**Required behavior:** Publish the successful Codex operator session pointer atomically for the existing same-task callers, or connect them to the identity-bound store through an equivalent explicit resolver. The pointer is a locator, never authorization: `codex_dispatch` must still validate backend, run, task, family, role, worktree, model, effort, and configuration. A new corrective task with a different task ID must start fresh under the current identity contract; do not blindly forward its parent's pointer. Failures must not publish a usable successful-session pointer.

**Acceptance:** A fake runtime completes one operator dispatch, then a same-task correction demonstrably receives the exact stored session ID and resumes after identity validation. Changed identity is rejected. A new task does not resume its parent. No request relies on implicit latest-session behavior.

### F4 — P2: POSIX timeout termination waits for an unreaped child to disappear

**Locations:** main `skills/two-model-sdd-pipeline/scripts/codex_process.py:92-99,129-134`; related ownership calls in `run_control.py`.

**Evidence level:** Static platform-specific control-flow finding. Native Linux reproduction was not available on the Windows review host and is a mandatory first verification step for this correction.

**Cause and expected impact:** On timeout, `run_owned` invokes `stop_owned_processes` before `communicate` reaps the direct child. On Linux, a killed but unreaped child can retain its `/proc` start identity as a zombie. The stop routine requires that identity to disappear, raises `owned process did not terminate`, and prevents normal timeout output capture/classification. Interrupt and registration-failure cleanup share the ownership/reaping concern.

**Required behavior:** Preserve PID/start-identity validation and process-group termination, but distinguish terminating an owned process from reaping a direct child. Reap a direct child with a bounded wait before asserting final disappearance; do not try to reap unrelated or externally owned processes. Timeout retains captured output and reaches the dispatcher timeout classification (exit 124). Cancellation remains distinct from timeout.

**Acceptance:** A real Linux child emits stdout/stderr and sleeps past its timeout; output survives, timeout is recorded, and no child remains. Test cancellation, registration failure, descendant termination, and PID identity mismatch. Windows ownership tests remain passing. If Linux does not reproduce the proposed cause, record the contrary evidence and revise this finding before changing behavior.

### F5 — P2: Flutter recall fails after a legitimate asset identity update

**Locations:** R5 `skills/flutter-app-pipeline/scripts/template_catalog.py:154-155`, `template_recall.py:198-200`; shared asset identity in `skills/two-model-sdd-pipeline/scripts/asset_catalog.py:18,58-59`.

**Trigger and evidence:** Upsert `acme/app` with fresh AUTO_APPROVE evidence and SDK constraint `>=3.0`: recall is `HIT`. Upsert the same owner with SDK `>=3.2`: there are two immutable assets and one current template row, and recall becomes `SETUP_ERROR`. Reproduced against a temporary SQLite database using the R5 public adapter functions.

**Cause:** License/compatibility changes intentionally create another immutable asset ID. The legacy table points to the current ID, while generic recall returns eligible historical IDs as well. The wrapper treats an unbound historical asset as database corruption, aborting the entire query.

**Chosen correction:** Restrict Flutter adapter selection to current `templates.asset_id` bindings before ranking/limiting and converting results. Preserve historical assets and their outcomes for generic history. Distinguish an unselected historical row from a missing/corrupt current binding. Do not silently return stale compatibility or license evidence.

**Acceptance:** Compatibility and license updates retain history and old outcomes, return the current eligible template without setup errors, and preserve ordering/limits with multiple templates. A truly missing current asset remains a diagnosed setup error. Refresh rollback and reopen/migration behavior remain intact.

### F6 — P2: Requirement opt-outs can leave unresolved dependencies

**Location:** R5 `skills/two-model-sdd-pipeline/scripts/requirement_profiles.py:86-102`; packaged `profiles/flutter-forms.json`.

**Trigger and evidence:** Resolve packaged profiles for a Flutter form with `opt_outs.form-validation="handled upstream"`. The result retains `input-mask` with dependency `form-validation`, excludes that dependency, and returns no questions. This was reproduced directly using the packaged profiles.

**Cause:** The resolver records dependency IDs but never validates the selected dependency graph after applicability, conflict resolution, and opt-outs.

**Required behavior:** Do not silently reinstate an opted-out requirement. Exclude a dependent requirement from the actionable set when its dependency is unavailable, and emit a deterministic `unresolved_dependency` question containing its ID and missing dependency IDs. Propagate this to a fixed point. Cyclic dependencies produce a deterministic `dependency_cycle` question and exclude cycle members and downstream dependents. Preserve the user's reasoned exceptions.

**Acceptance:** Cover packaged form opt-out, dependency removed by conflicting overlays, inapplicable/missing dependency, transitive dependency, and cycle. Reordering profiles yields the same result. No retained requirement references an absent retained dependency.

### F7 — P2: Promotion overwrites a distributable file named release.json

**Location:** R5 `skills/two-model-sdd-pipeline/scripts/template_promotion.py:103-107`.

**Trigger and evidence:** Stage a valid request containing `files["release.json"]="original release payload"`. The API reports `staged` and returns that payload in `files`, but the physical file contains the generated internal manifest. Reproduced in a temporary local repository.

**Cause:** User payload and internal metadata occupy the same namespace, and metadata is written after payload files.

**Chosen correction:** Reserve the root `release.json` metadata path explicitly and reject colliding payloads before any writes with a stable blocked reason. Reject aliases and parent/child collisions as well; do not silently rename or drop user material. Existing noncolliding stage layout stays compatible.

**Acceptance:** Root metadata collision, `./release.json`, duplicate normalized paths, and `release.json/child` are rejected without a partial stage. Valid nested payload paths and Unicode paths preserve their bytes. Case-insensitive filesystem aliases cannot bypass the reservation.

### F8 — P2: Promotion idempotence trusts the manifest without checking payload bytes

**Location:** R5 `skills/two-model-sdd-pipeline/scripts/template_promotion.py:91-98` and the concurrent-target path at `109-114`.

**Trigger and evidence:** Stage a valid asset, edit the staged `README.md`, and repeat the identical request. The function returns `staged`, `idempotent=True`, while the file remains corrupted. Reproduced in a temporary repository.

**Cause:** Existing-target validation compares only serialized `release.json`; it never verifies the payload represented by that manifest.

**Required behavior:** Declare idempotent success only when metadata, exact distributable file inventory, and physical file bytes all match. Validate regular-file/path containment and reject symlink substitutions. If the target differs, return `overwrite_refused` and preserve the target for investigation. Apply the same check after concurrent publication races. Never repair or overwrite existing bytes implicitly.

**Acceptance:** Modified, missing, additional, and symlinked payloads refuse reuse without mutation; an identical target succeeds. A concurrent conflicting stage cannot replace the winner. Original and on-disk bytes must agree for every returned file.

## Review evidence and limits

| Checkout | Command (from checkout root) | Result |
|---|---|---|
| main | `python -B -m unittest discover -s skills/two-model-sdd-pipeline/tests -p 'test_r4_*.py'` | 130 passed |
| main | Same discovery directory, `-p test_codex_process_ownership.py -v` | 6 passed |
| main | Same discovery directory, `-p test_codex_resume_and_retry.py -v` | 7 passed |
| R5 worktree | Same discovery directory, `-p 'test_r5_*.py' -v` | 53 passed |
| R5 worktree | `python -B -m unittest discover -s skills/flutter-app-pipeline/tests -p 'test_template*.py' -v` | 39 passed |

These are 235 distinct existing tests, not the complete repository suite. Earlier focused selector/preflight tests are included in the R4 count. The initial selector CLI check could not create temporary files in the read-only sandbox; after the environment permitted writes, all six selector tests passed. That failure was environmental, not a repository defect.

The Flutter subset emitted socket `ResourceWarning`s. The test HTTP server's `stop()` calls `shutdown()` and joins its thread but omits `server_close()` (`tests/test_template_search.py:65-67` in the Flutter skill). Treat this as test-fixture cleanup, not product behavior or a failed assertion; include a small cleanup in final validation.

Additional disposable reproductions established F1, F2, F5, F6, F7, and F8. F3 is supported by the producer/consumer call chain; F4 needs Linux execution. Tests passing do not refute the uncovered cross-component cases. No live model, remote publication, production asset adoption, or real package installation was performed.

## Completion criteria

All eight findings map to explicit plan tasks. Required regression tests must first fail at the intended behavior, then pass after correction. Existing affected suites and the full shared/Flutter deterministic suites must pass, with any remaining failures investigated and reported by cause. F4 cannot be declared fixed from Windows-only mocks. Review the final combined R5 snapshot and the applied core fixes before proposing integration; do not describe this review's passing subsets as merge certification.
