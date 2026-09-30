# R4 Task 1 implementation report

Commit: `d527ab292d87e70e05c6321246d7761afb18d936` (`Implement R4 correction routing and dispatch budgets`).

## Scope and investigation

Implemented the approved Task 1 brief in the isolated `r4-task1-routing` worktree. The baseline had a director hop for every `SEND_BACK`, retry loops without a durable external operator budget, and separate generic and Flutter reviewer dispatch paths. The existing reviewer schema already required structured correction scope, paths, and contracts; the extension point was the script router and dispatch adapters.

The initial TDD RED command was `python -m unittest discover -s skills/two-model-sdd-pipeline/tests -p 'test_r4_*.py' -v`: nine tests ran and eight failed at the new assertions because `correction_policy.py`, `dispatch_budget.py`, and the Flutter shared review delegation were absent. This was the expected missing behavior, not an infrastructure failure.

## Changes

- Added `correction_policy.decide()` and wired `route-next` so a valid, in-scope `SEND_BACK` returns to the same operator; structural, uncertain, or expanded scope goes to the director; malformed metadata blocks. Added durable direct-fix intent/dispatched ledger boundaries for crash replay.
- Added `dispatch_budget.reserve()` with atomic, family-scoped, idempotent reservations. Defaults are `[5,3,3]`; a family cannot change its allowances after its first reservation. The Codex runtime manifest carries the configured limits. OpenCode reads `run-manifest.json`, an explicit `PIPELINE_CODER_CYCLE_LIMITS` launch setting, or the default. Confirmed pre-start transport failures release a reservation and increment a separate transport counter. Ambiguous post-start failures retain their charge. The director assesses each exhausted cycle; the third assessment pauses.
- Moved OpenCode reviewer dispatch and pending candidate handling to shared `review-dispatch`; generic and Flutter gates delegate to it. Codex normalization remains candidate bound. A reviewer transport failure leaves the same candidate pending and does not request new coding.
- Added valid no-op director arbitration assessments to the canonical plan transaction path, so an exhausted cycle can be assessed without fabricating a plan edit or empty commit.
- Documented semantic dispatch ownership in `docs/testing/r4-dispatch-inventory.md`.
- Updated stale Jev invariant tests to check the shared reviewer owner while retaining advisory-only boundaries.

## Verification

- R4 tests: 14 passed.
- `test_route_next.py`: 26 passed.
- `test_jev_all_sites_invariants.py` and `test_jev_director_routing_invariants.py`: 6 passed.
- `test_jev_director_task_run.py`: 2 passed.
- `test_dispatch_retry.py`: 12 passed.
- `test_codex_dispatch.py`: 13 passed.
- `test_codex_launcher.py`: 5 passed.
- `test_orchestrator.py`: 10 passed.
- Earlier focused runs: `test_codex_gate_results.py` 6, `test_codex_review_recovery.py` 6, `test_codex_plan_transactions.py` 9, `test_dispatch.py` 16 passed.
- `bash -n` on changed shell scripts and `git diff --check` passed.
- `test_coder_gate.py`: 24 passed after final edits.
- Flutter `test_gates.py`: 22 passed after final edits.

The complete generic and Flutter suites are reserved for the R4 closure in the parent workflow. All tests used fake providers or disposable repositories; no live model capability is claimed. No Two Model Pipeline launcher or orchestration script was used to conduct this implementation.

## Self-review notes

Codex post-start ambiguity needed special attention. The process can start before the process registry callback succeeds, so registry length cannot prove pre-start. The final adapter releases the budget only for `ProcessLaunchError` or failures before entering the dispatch call. All other entered-dispatch errors keep their reservation. A replay uses the same dispatch identity; a changed prompt timestamp creates a new identity.

The report and worktree are local. The parent workflow will integrate the commit and run final suites against the final combined source commit and runtime versions.

## Review fix round

Fix commit: `8dd314b1033b747489882bb0b1942e71d1d75a2f` (`Reconcile interrupted R4 dispatches before replay`). The worktree is clean after this commit.

The independent review found two critical lifecycle defects and three important routing/coverage defects. The direct correction route originally reused a prompt timestamp after an ambiguous crash; an external operator could start twice under one reservation. The OpenCode retry wrapper originally interpreted any raw exit code 5 as pre-start and could release a started worker's reservation. RED checks demonstrated both missing behaviors: the new raw-exit-5 test returned success after an unwanted retry, and the issued-grant test routed a plan-asserted grant directly to the coder.

The corrected retry path requires an adapter-owned marker in addition to exit 5; `dispatch-opencode` writes it only when the binary is missing before worker start and unsets the variable before launching the worker. Raw worker exit 5 remains ambiguous and charged. A direct correction records a candidate/prompt-bound intent before dispatch. If interrupted before the completion ledger entry, `route-next` emits `DIRECT_FIX_RECONCILE` and `task-run` blocks redispatch. `direct_fix_reconcile.py reconcile WORKSPACE TASK DISPOSITION.json` consumes a matching supervisor disposition and hashed recovered evidence, then appends the RED and dispatch boundaries once. The budget charge is retained. A mismatched attempt ID is rejected.

The correction policy ignores `task.scope_grants`. It only accepts paths/contracts from `scope_grants.py` issued records matching run, family, task, attempt, supervisor issuer, and grant ID. A CLI test exercises issuance, acceptance, and rejection after changing the attempt. Legacy reviewer dispatch creates an exclusive candidate/package claim before launch. A concurrent or crashed second call cannot dispatch again. `legacy_review_claim.py reconcile WORKSPACE TASK CANDIDATE DISPOSITION.json` consumes a matching supervisor disposition with hashed reviewer evidence, allowing idempotent completion without another reviewer call.

Added entry-point tests for a missing-session direct correction, an ambiguous direct-fix crash, supervisor recovery without redispatch, an ambiguous reviewer launch, and idempotent reviewer completion. The documentation now describes both reconciliation interfaces. Tests and source were changed directly as project files; no pipeline orchestration script was invoked for implementation.

Fix-round verification: `test_dispatch_retry.py` 13 passed; `test_route_next.py` 26 passed; `test_r4_*.py` 16 passed before the final reconciliation test additions; `test_jev_director_task_run.py` 4 passed before the final supervisor recovery addition; Flutter `test_gates.py` 22 passed; `test_codex_multitoolchain_integration.py` 3 passed; `bash -n` and `git diff --check` passed. The full coder-gate rerun was started after updating its pre-start fixture and must complete before handoff. Re-run the final focused suites after all edits and record their results below.

Final fix-round checks: `test_coder_gate.py` 24 passed; `test_r4_*.py` 16 passed, including issued-grant CLI and reviewer reconciliation; `test_codex_role_policy.py` 40 passed; Jev routing invariants 6 passed. The direct-fix reconciliation test rejects a mismatched attempt and accepts a matching supervisor disposition with hashed evidence; replay adds one dispatch boundary and route-next emits `CODER` without a fresh operator call. The normal-path entry-point test invokes the initial operator and then a direct in-scope correction, observing exactly two operator calls and no director call. The complete task-run file was rerun after this addition and must finish before commit.

Final task-run suite: 6 passed. `direct_fix_reconcile.py` now also verifies that the prompt hash and current candidate commit still match the recorded intent. The targeted reconciliation test passed after this hardening. Python compilation of the four changed/new modules passed. All changed shell scripts passed `bash -n`; `git diff --check` passed. The full generic and Flutter suites remain the parent R4 closure check.

## Review fix round 2

Fix commit: `a730709571b1df401ac8bfe3cf73dc26f0185b69` (`Authenticate R4 scope grants and preserve review state`). The worktree is clean after this commit.

The second review correctly found that the issued-grant record was forgeable: `scope_grants.reserve()` stamped `issuer=supervisor` from caller-controlled identity fields, and the correction router checked only those fields. A RED test called `reserve()` without supervisor capability and observed a grant; a second RED test showed legacy review removed `task-N-review-state.json`, so the subsequent grant-bound SEND_BACK route could not use it.

The grant record now carries an HMAC SHA-256 signature over path, run/family/task/attempt IDs, grant ID, issuer, and contracts. Issuance requires `PIPELINE_SCOPE_GRANT_KEY`, a controller-only hex key of at least 32 bytes. The router verifies that signature with the controller key and fails closed when it is unavailable or the record has been altered. Both OpenCode and Codex worker adapters strip the key before starting a model process. The key is never written to the registry. A worker can still write an unsigned registry entry, but that entry cannot authorize an expanded path. The test covers an unsigned forged record, successful supervisor issuance, missing key at routing, and a modified attempt. This capability must be supplied to controller scripts for both issuance and routing; absent capability means no scope extension.

The legacy review owner now preserves `task-N-review-state.json` after dispatch. Its candidate-bound claim still makes a repeated dispatch idempotent. The entry-point test runs `review-dispatch --legacy`, records `review_outcome=SEND_BACK`, issues a signed grant for the reviewed candidate, and invokes `route-next`; the final route is `DIRECT_FIX 2`. This directly covers the previously broken sequence.

Fix-round-2 focused results: R4 tests 17 passed; Codex dispatch 13 passed; scope multitoolchain integration 3 passed; `bash -n`, Python compilation, and `git diff --check` passed. One parallel Python compilation initially got Windows access denied while another test process wrote the same `__pycache__` target; a standalone rerun passed. Route-next, Flutter gate, and coder-gate reruns are in progress and must finish before the fix commit. The complete suites remain the parent closure check.

Final fix-round-2 verification: R4 tests 17 passed after adding wrong-key and OpenCode worker-environment checks; route-next 26 passed; Flutter gate 22 passed; coder-gate 24 passed. The end-to-end legacy reviewer test retains candidate state, records SEND_BACK, verifies a signed supervisor grant, and routes directly to the coder. The Codex worker environment removes the capability after runtime overrides are applied; the OpenCode test launches a fake worker and confirms the capability is absent. A missing or wrong capability leaves the grant untrusted and routes the expanded scope to the director.

## Review fix round 3

Fix commit: `ba1180a92ee8b57aa4fc1f1c27de999384ffb603` (`Advance review state before R4 direct correction gate`).

The fix records `status=correction_started` and the correction attempt ID atomically before operator dispatch. `coder-gate` trims Windows CRLF from parsed review state and bypasses the stale pending-review shortcut only for a correction already in progress. This lets a corrected candidate reach its own gate while preserving the original reviewed candidate identity for scope-grant validation.

Fresh verification on 2026-09-29:

- Direct task-run → coder-gate regression tests passed on both backends: OpenCode and Codex, 2 tests.
- The isolated `correction_started` test and both backend integration tests now assert a real test-gate invocation (`--tasks` or `--toolchains`); the integration tests also assert that the gate follows the correction dispatch. All 3 focused tests passed.
- R4 Task 1 tests (`test_r4_*.py`): 17 passed.
- The complete affected `test_coder_gate.py` file: 26 passed before adding the focused regression; the 3 focused tests passed after it was added.
- RED reproduced on pre-fix `a730709` with `python -m unittest discover -s skills/two-model-sdd-pipeline/tests -p test_coder_gate.py -k correction_started_candidate_reaches_gate_instead_of_old_codex_review -v`: it failed because the test gate was not called, and stderr said `CODER-GATE: candidate <sha> awaits normalized Codex review`. The disposable pre-fix checkout normalized only the two-field Python stdout to raw LF via `sys.stdout.buffer.write`; Windows CRLF otherwise caused an unrelated false negative in the old shell comparison. No production source was changed for this reproduction.
- No Two Model Pipeline launcher or orchestrator was used; checks were direct Superpowers SDD invocations against the project.

The two required Task 1 files, `test_r4_correction_routing.py` and `test_r4_dispatch_budget.py`, are tracked in commits `d527ab2` and `a730709`. The new direct gate regression test and this round-3 report are included in the local closure commit. The full generic and Flutter suites remain the parent R4 closure check.
