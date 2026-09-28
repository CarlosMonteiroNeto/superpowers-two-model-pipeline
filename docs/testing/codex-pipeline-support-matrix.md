# Codex pipeline support matrix

Last exercised: 2026-09-27. This is an evidence record, not a compatibility
certification. R3 Codex integration acceptance is complete; OpenCode lifecycle
parity and broad platform certification remain unproven.

## Executed combinations

| Backend/runtime | Platform and versions | Evidence | Result and boundary |
|---|---|---|---|
| Codex adapter, offline fixtures | Windows 10.0.19045; Python 3.12.10; Git 2.55.0.windows.3; Codex CLI 0.156.1; OpenCode 1.18.32 detected | `.work/r3-codex-acceptance-final/codex-acceptance-20260927T234543Z-45807719/report.json` | 7 scenario groups passed, 213 test executions. Source SHA-256 `30c4bcad7860bd4bff9e2ea7ce346de807589ca3f06dad13f85d4d80cb562184`; run was on the pre-commit working tree. |
| Codex adapter, live two-task pipeline | Windows 10.0.19045; `gpt-6-luna`, reasoning `medium`; local-only disposable project | `C:\r3live-continued\.superpowers\two-model\ebbbce2823bbd1966b26\ledger.jsonl` and gate reports in the same run directory | Two tasks completed RED/GREEN, reviewer APPROVED, serialized integration and fresh director closing approval. Final candidate `4b1b92630b1d1d80af51f39a9bd0782b125fada5`; tests `2 passed`, analysis clean. Local-only; no push. The reviewer router's optional classifier lacked `TYPESAFE_API_KEY` and used standard review fallback. |
| Codex protected-path challenge | Disposable fixture; Codex CLI 0.156.1 | `.work/r3-protected-path-challenge/` | Integrity comparison detected `.pipeline-identity.json` deleted by a live Codex worker and blocked acceptance after dispatch (`integrity_ok=false`). This demonstrates detection and fail-closed closing, not write-time denial. Hook-trust prompts also marked modified hooks untrusted; they are not a write guard. |
| Extracted harness ZIP and TAR.GZ | Windows 10.0.19045; Python 3.12.10 | `.work/r3-extracted-package-final.log` | Both extracted packages contained 460 files, excluded `node_modules`, initialized Codex pinning, and reported doctor `ready` for director/operator/reviewer; orientation and doctor exited 0. Includes Unicode and spaces in project paths. |
| OpenCode Zen live run and requested UI review | Windows 10.0.19045; OpenCode 1.18.32; `opencode/muse-spark-1.3-contributor-free` | `.work/r3-opencode-live-short-run.log`, `.work/r3-open-codex-session.json`, `.work/r3-opencode-closing-result.json` | Two task phases reached RED/GREEN and APPROVED reviews, but unattended task-generator closing returned FreeTierError 403 outside OpenCode UI. The user-requested Muse Spark Free UI audit returned APPROVED at cost 0, with two parked minor findings (classifier key unavailable; headless closing unavailable). Full unattended OpenCode acceptance is not established. |
| Generic engine, full suite | Windows 10.0.19045; Python 3.12.10; Git 2.55.0.windows.3 | `.work/r3-generic-final.log` | 947 tests passed, 2 skipped, in 1613.560 seconds. |
| Generic engine, affected focused tests | Same | 2026-09-27 focused runs | 20 integration tests, 17 recovery/plan-refresh tests, 4 portal packaging tests (2 ZIP skips), 4 run-pipeline lifecycle tests, 2 serial/parallel wave tests, 3 JEV routing invariants, 1 structured Flutter gate regression, and 2 updated documentation assertions all passed. |
| Codex adapter, focused regressions | Windows 10.0.19045; Python 3.12.10 | `.work/r3-generic-final.log`, plus earlier focused invocations | Full Codex suite is included in the final generic run. The PowerShell wrapper probe regression and complete `test_foundation_doctor.py` (26 tests) passed after the fix. |
| Flutter pipeline | Windows 10.0.19045; Python 3.12.10 | `.work/r3-flutter-rerun.log` | 150 tests passed after the latest shared runner changes. |

## Remaining limitations

- Full unattended OpenCode parity is not supported by the observed Free-tier
  restriction: headless task-generator closing returned HTTP 403 outside the
  OpenCode UI. The UI review does not substitute for that lifecycle check.
- The protected-path test detected an after-dispatch mutation; it did not deny
  the write at the moment it occurred. Do not describe this as a write guard.
- Evidence reports were generated from the dirty pre-commit candidate. Rerun
  the offline acceptance harness against the committed source to bind its
  report to the published revision.
- ShellCheck is unavailable on this host. Seven affected Bash scripts passed
  `bash -n`; Flutter suite passed 150 tests.

## C01-C20 traceability

The rows below point to offline coverage or explicitly mark live evidence as
missing. Offline tests do not establish provider or OS sandbox behavior.

| Finding | Offline evidence area | Live status |
|---|---|---|
| C01 | `test_codex_skill_entry_contract`, `test_codex_acceptance_harness` | Entry/preflight exercised; plugin refresh is separately performed from `origin/main`. |
| C02 | `test_r2_packaged_workers`, `test_codex_skill_entry_contract` | ZIP and TAR.GZ extraction and initialization verified. |
| C03 | `test_codex_dispatch`, `test_codex_launcher` | Codex transport and structured results exercised for the three roles. |
| C04 | `test_codex_role_policy`, `test_codex_acceptance_harness` | Luna/medium observed for operator, reviewer, director and resumed operator. |
| C05 | `test_codex_scoped_runner`, `test_codex_worker_instructions`, `test_codex_dispatch` | Protected-path mutation was detected after dispatch and blocked at closing; write-time denial is not established. |
| C06 | `test_codex_dispatch`, `test_codex_closing_gate`, `test_codex_acceptance_harness` | Valid structured role output observed; malformed live response not injected. |
| C07 | `test_codex_gate_results`, `test_codex_flutter_gate_results`, Flutter test suite | No live provider failure injection. |
| C08 | `test_codex_closing_gate`, `test_codex_acceptance_harness` | Live Codex director approved closing after two task integrations; OpenCode headless close remains blocked by provider 403. |
| C09 | `test_codex_director_proposals`, `test_codex_plan_transactions` | No live concurrent proposal run. |
| C10 | `test_codex_run_identity`, `test_codex_worktree_lifecycle` | Two live tasks integrated serially and final closing was approved. |
| C11 | `test_codex_dispatch`, `test_codex_review_recovery`, `test_recovery_hardening_e2e` | Explicit operator resume observed; ambiguous interruption not injected live. |
| C12 | `test_codex_context_package`, `test_codex_worker_instructions` | Context packaging tested offline. |
| C13 | `test_codex_capabilities`, `test_foundation_doctor`, `test_r2_backend_contract_parity` | Local Codex preflight available; no live mixed-toolchain project. |
| C14 | `test_codex_launcher`, `test_codex_process`, `test_codex_capabilities` | Windows live Codex run and extracted ZIP/TAR.GZ package paths exercised. |
| C15 | `test_codex_worker_policy`, `test_codex_acceptance_harness`, `test_codex_dispatch` | Live task-family evidence was archived; retention beyond the observed run was not timed. |
| C16 | `test_codex_multitoolchain_integration`, generic integration tests | Offline mixed-toolchain coverage only. |
| C17 | `test_codex_skill_entry_contract`, `test_codex_worker_instructions` | No extra agent was spawned in the live probes. |
| C18 | Documentation/contract checks in `test_foundation_contracts`, `test_r2_backend_contract_parity` | Branch-wide doc gate not part of live probe. |
| C19 | `test_codex_worker_instructions`, `test_codex_role_policy`, `test_codex_acceptance_harness` | Live effective settings recorded; inherited-policy denial was not challenged. |
| C20 | `test_codex_acceptance_harness`, `test_codex_context_package`, runtime reference | Codex acceptance limits and OpenCode Free-tier limitation are recorded above; cross-backend parity remains open. |

## Compatibility statement

The evidence supports offline fixture coverage on the Windows/Python/Git
combination above, a live two-task Codex run with serialized integration and
closing, and extracted package initialization. It does not establish write-time
protection against a live worker, unattended OpenCode Free-tier closing, full
OpenCode lifecycle parity, or general platform certification.
