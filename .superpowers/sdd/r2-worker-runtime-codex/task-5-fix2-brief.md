# R2.5 adapter registry fix round

Correct the backend registry seam without adding fields to the strict normalized request. The Codex adapter must receive its validated runtime envelope separately from `dispatch_contract` request data, while preserving the public `invoke(request)` shape. OpenCode cancellation must not call Codex process termination; backend cancellation must be selected explicitly and unsupported cancellation reported honestly.

Controller-owned RED tests are in `test_codex_dispatch.py`; do not modify them. Baseline is `744dbc2`. RED evidence: `task-5-fix2-red.txt`; 6 tests ran with one failure and one error from the backend seam. Retain both backend fixtures and run canonical Codex plus legacy dispatch/session suites; run `test-integrity 744dbc2 <candidate>` and commit a fix candidate.
