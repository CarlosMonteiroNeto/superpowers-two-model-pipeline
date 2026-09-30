# R4 Task 4 review fix

## Investigation and cause

Review was against Task 4 commit `4bd765d`. `gate_evidence.create_workspace_manifest` accepted caller-selected toolchains without enforcing plan coverage and hashed only test command descriptors. `run-gates` ledgered the pre-run manifest without re-deriving candidate identity after commands. Closing also lacked a runtime connection between supervisor-owned baseline evidence, the current complete-suite result, and Task 3's waiver validator.

`run-pipeline` resolves toolchains before the first `task-run`, which provides the baseline hook. The toolchain runner already owns the configured command execution and can capture adapter-specific raw output. Reusing existing unittest/pytest/Flutter/Go output contracts supplies normalized inventory and failure signatures; unsupported or incomplete adapters fail closed for waiver eligibility. Earlier failures in `test_run_pipeline.py` were stale SEND_BACK fixtures: they omitted Task 3's structured `correction_scope`, `affected_paths`, and `affected_contracts`. Those fixtures now declare a structural correction; the serial-order assertion admits R4 evidence rows while retaining lifecycle order checks.

## TDD and implementation

For the four review findings, the new focused regressions were run against pre-fix code and failed at the intended behavior: partial toolchain selection was accepted, a candidate mutation still produced PASS, and analyze configuration changes retained the same config hash. (The waiver end-to-end tests were added alongside the supervisor-owned producer/consumer implementation.)

`run-gates` now validates selected toolchains against plan scope, includes test/analyze/format commands and gate-affecting toolchain configuration in identity, and re-derives candidate/impact identity after execution before recording PASS. Toolchain execution captures structured suite evidence only at baseline/closing boundaries. `run-pipeline` captures a pre-coder baseline under fixed supervisor workspace state. `final-gate` recomputes current evidence, compares it with baseline through `baseline_failures`, validates an explicit supervisor approval event against the candidate-bound ledger revision, and reports `completed_with_waived_baseline` as non-green. Exact closing evidence may be reused only when tree, environment, commands/configuration, toolchain set, and impact selection match; otherwise all affected configured suites rerun. Invalid/new/ambiguous failure evidence blocks completion and reopens work. Operator guidance describes focused task iteration and script-owned verification.

The test suite confirms a baseline -> inherited regression -> explicit approval -> waived completion path and rejects new or ambiguous failures. Baseline evidence is immutable and approval is validated before any ledger append that could change its bound revision. Completion status is stored separately from the approval ledger.

## Verification

- `python -m unittest discover -s skills/two-model-sdd-pipeline/tests -p 'test_r4_*.py' -v` — 65 passed.
- `python -m unittest discover -s skills/two-model-sdd-pipeline/tests -p 'test_coder_gate.py' -v` — 27 passed.
- `python -m unittest discover -s skills/two-model-sdd-pipeline/tests -p 'test_final_gate.py' -v` — 18 passed.
- `python -m unittest discover -s skills/two-model-sdd-pipeline/tests -p 'test_integrate.py' -v` — 20 passed.
- `python -m unittest test_run_pipeline -v` from `skills/two-model-sdd-pipeline/tests` — 20 passed.
- `bash -n skills/two-model-sdd-pipeline/scripts/{run-gates,integrate,final-gate,run-pipeline}` — passed.
- `python -m py_compile` on `gate_evidence.py`, `toolchain_gate.py`, `suite_evidence.py`, `closing_waiver.py`, and `closing_cache.py` — passed.
- `git diff --check` — passed (Git emitted only line-ending normalization notices for two test files).

## Limits and scope

Waiver evidence is supported only for adapters that produce a complete, stable inventory and raw failure detail. Unknown adapters, missing machine reports, interrupted commands, changed candidate/configuration, and ambiguous failure identity remain fail-closed and cannot be waived. This preserves completion correctness while limiting inherited-failure waiver availability to evidence the script can verify. Task 5/R5 was not started.
