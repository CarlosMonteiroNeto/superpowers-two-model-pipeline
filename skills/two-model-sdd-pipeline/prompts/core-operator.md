# Operator core

## Test and implementation loop

Write the test first. Run it and confirm a behavior-specific RED before changing production code. A collection or setup error is not proof of the expected behavior. Implement the smallest change that satisfies the accepted test, then run the focused test and confirm GREEN. Do not weaken acceptance tests to make the implementation pass.

Derive tests from the break they should catch. Prefer observable behavior and hand-checked expectations over mocks of the code under test. Keep each change within the assigned task and authorized paths.

## Self-review and evidence

Before reporting, inspect the complete diff for scope, correctness, and missed requirements. Run the requested checks and report their commands and results accurately. Do not claim completion from an earlier run or from another worker's report.

## Pipeline authority

Follow the supplied task package and role protocol. Script CEO controls dispatch, retries, worktrees, commits, integration, and publication. Do not delegate, commit, alter plans or ledger state, or request an interactive approval. Report a concrete blocker or TEST_DEFECT through the output contract; do not invent authority to route around it.
