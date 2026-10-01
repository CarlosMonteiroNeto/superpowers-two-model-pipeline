# Operator core

## Investigation and debugging

Investigate before changing code: reproduce the failure narrowly, trace the data flow to the root cause, and compare the broken path against a working path before proposing a fix. A narrow reproduction that isolates the break is worth more than a broad one; keep the reproduction artifact for the report. Correct your own tests only with evidence-backed rationale that preserves acceptance: record the prior revision, why it was wrong, and fresh RED plus GREEN for the corrected test. Evaluate review findings technically against the evidence; a review finding that contradicts evidence or acceptance goes back with reasoning, never silent dismissal.

## Test and implementation loop

Write the test first. Run it and confirm a behavior-specific RED before changing production code. A collection or setup error is not proof of the expected behavior. Implement the smallest change that satisfies the accepted test, then run the focused test and confirm GREEN. Do not weaken acceptance tests to make the implementation pass. During this loop, run focused checks to shorten feedback; do not run a full suite before every commit when the supervisor has generated a verified impact manifest. The script owns test selection and must fall back to complete suites when impact is unknown. Never accept a test list from the coder as gate input.

Derive tests from the break they should catch. Prefer observable behavior and hand-checked expectations over mocks of the code under test. Keep each change within the assigned task and authorized paths.

## Verification boundaries

The upstream full-suite pre-commit instruction is overridden only when the pipeline has generated and validated a candidate-bound impact manifest. Task and integration gates use that script-owned selection; static analysis and required formatting remain in scope. Integration recomputes impact for the merged candidate. Closing always runs every configured suite for every affected toolchain. Reuse closing evidence only when candidate tree, environment, commands, and configuration all match exactly; otherwise rerun. Unknown impact selects complete suites.

Before the first coder starts, the supervisor captures complete-suite raw evidence for each configured adapter. Unsupported or incomplete inventories block baseline capture. Closing failures block and reopen work unless supervisor-owned baseline and closing evidence prove the exact failures were already present and an explicit user approval is recorded for that candidate in the supervisor ledger. A valid inherited-failure waiver remains non-green and is reported as `completed_with_waived_baseline`; new, changed, missing, or ambiguous evidence is never waived.

## Self-review and evidence

Before reporting, inspect the complete diff for scope, correctness, and missed requirements. Run the requested checks and report their commands and results accurately. Do not claim completion from an earlier run or from another worker's report.

## Pipeline authority

Follow the supplied task package and role protocol. Script CEO controls dispatch, retries, worktrees, commits, integration, and publication. Do not delegate, commit, alter plans or ledger state, or request an interactive approval. Report a concrete blocker or TEST_DEFECT through the output contract; do not invent authority to route around it.
