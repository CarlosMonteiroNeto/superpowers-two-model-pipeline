# R2.5 exit classification fix round

Implement Task 5's documented process exit classes. A confirmed executable-launch failure before child start must map to retryable exit 5; errors after child start, including capture/semantic failures, remain ambiguous and map to 6; usage/configuration errors map to 2/4 as specified; interruptions/timeouts retain 130/124 where applicable. Preserve OpenCode retry behavior.

Controller-owned RED test is `test_preexecution_launch_failure_uses_retryable_exit_five` in `test_codex_dispatch.py`; do not edit this test. The Codex retry wrapper tests in `test_dispatch_retry.py` verify code 5 retries and code 6 does not. Baseline is `ba44cc2`; raw RED is `task-5-fix3-red.txt` (7 Codex dispatch tests, 1 expected failure). Run both canonical and legacy dispatch suites, test-integrity against the baseline, and commit the candidate.
