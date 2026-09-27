# R2.5 review fix round

Correct the findings from the independent review of `ba1fd42`:

1. Enforce that requested model and effort agree with the role manifest, and apply the manifest effort exactly once.
2. Any session ID must enter the identity-checked resume path. Missing/mismatched identity blocks. Explicit fresh recovery starts `exec` fresh and records `context_reset`; it must not resume the old ID.
3. Persist lifecycle/session identity before continuation and preserve active/unresolved state on failures after provider start.
4. Expose active process ownership to the run controller so cancellation can terminate the owned tree while dispatch is running.
5. Include task ID in persisted identity so task-scoped cleanup can select its records.
6. Timeout cancellation must pass a verified process start identity. Implementer should add targeted coverage for fixes beyond the controller tests below.

Controller RED coverage is in `test_codex_resume_and_retry.py` and `test_codex_process_ownership.py`; do not modify either file. Baseline commit is `6281c4e`. The fresh canonical RED run had 83 tests with 3 expected failures (request model mismatch, unbound resume ID, and timeout cancellation ownership); raw output is `task-5-review-red-final.txt`. Preserve legacy OpenCode fixtures. Run all canonical and affected suites, test-integrity against this baseline, diff checks, and report any acceptance item that cannot be fully met.
