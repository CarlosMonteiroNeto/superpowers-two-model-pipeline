# Final Review Prompt Template (Controller, Strategic tier, stateless)

Dispatch once after all tasks complete. The Controller sees exactly two
curated artifacts - the whole-branch diff and the ledger - never the
branch's conversation history.

```
Subagent (general-purpose):
  description: "Final whole-branch review"
  model: [STRATEGIC TIER - REQUIRED]
  prompt: |
    You are the Controller performing the final branch review of a
    two-model pipeline. All tasks are implemented. Decide whether this
    branch is ready to merge, and if not, name the smallest set of fixes.

    ## Artifact 1: Whole-Branch Diff

    **Merge base:** [MERGE_BASE]  **Head:** [HEAD_SHA]
    Review package: [DIFF_FILE]

    This is every change on the branch: commit list, stat summary, full
    diff with context. Read it as a whole - coherence across tasks is your
    job here; per-task reviews already happened.

    ## Artifact 2: Ledger

    Full ledger: [LEDGER_FILE]

    It records every decision taken on this branch: gate configuration,
    escalations, keep/discard calls, review outcomes, deferred minors,
    arbitrations. Cross-check the diff against it:
    - Deferred minors: which must be fixed before merge? Triage explicitly.
    - Arbitrations and rulings: did the code actually land the way they
      decided?
    - Escalated tasks: does their final state look settled or fragile?

    ## Global Constraints

    [GLOBAL_CONSTRAINTS]

    ## Your Review

    1. Holistic quality: architecture coherent across tasks? Duplicated or
       conflicting logic between tasks? Naming consistent? Dead code left
       by discarded attempts?
    2. Constraint audit: every global constraint holds across the whole
       branch, not just within single tasks.
    3. Interface integrity: contracts established early still hold at head.
    4. Test story: do the branch's tests together cover the feature's
       acceptance criteria from the plan/spec?

    Read-only: run nothing that mutates state; re-run no test suites (the
    Orchestrator just validated them). Name any check you would delegate.

    ## Report

    Verdict first:
    - READY_TO_MERGE - with any must-fix-before-merge items listed (which
      routes to one targeted fix dispatch), or clean.
    - NEEDS_FIXES - findings list, each with file:line, severity, and the
      smallest fix. Mark each finding TASK_SCOPE (targeted dispatch can
      close it) or STRUCTURAL (the plan itself was wrong).
    Then: triaged deferred minors (fix-now / accept-with-reason), strengths,
    and anything the human partner must know before merging.
```

**Placeholders:**
- `[STRATEGIC TIER]` - model recorded at the gate
- `[MERGE_BASE]` / `[HEAD_SHA]` / `[DIFF_FILE]` - `scripts/review-package
  <workspace> MERGE_BASE HEAD`
- `[LEDGER_FILE]` - `<workspace>/ledger.jsonl`
- `[GLOBAL_CONSTRAINTS]` - verbatim from plan.json

**Orchestrator after the dispatch:** ledger `final_review`. TASK_SCOPE
findings -> targeted Strategic Coder dispatch(es) + fresh reviewer on the
fix diff only. STRUCTURAL -> reopen the plan; surface to the human partner.
