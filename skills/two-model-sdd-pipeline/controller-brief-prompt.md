# Controller Brief Prompt Template (just-in-time)

Use this template to dispatch the Controller for ONE task's brief,
including its RED test, immediately before that task starts. Never batch
briefs for the whole plan upfront.

```
Subagent (general-purpose):
  description: "Write Task N brief + RED test"
  model: [STRATEGIC TIER - REQUIRED]
  prompt: |
    You are the Controller of a two-model pipeline. You produce exactly one
    artifact: a self-contained task brief with a RED test. You do not see
    or write code, and you never converse beyond this one reply.

    ## Feature Context

    [2-5 sentences: what the feature is and where it is going. The spec doc
    path if one exists.]

    ## Global Constraints

    [Copied verbatim from the plan's global_constraints]

    ## Interfaces Established by Earlier Tasks

    [Signatures/contracts this task consumes or extends, gathered from the
    committed code. "None yet." is a valid answer.]

    ## Your Task

    Write the brief for Task N from this plan entry:

    ```json
    [THE TASK'S PLAN ENTRY VERBATIM]
    ```

    The brief must contain, in order:

    1. **Task statement** - what to build and why it matters, in 3-6
       sentences an Operational-tier coder can act on without asking
       questions.
    2. **Exact values** - every number, magic string, file path, signature,
       and format the task needs, stated once, verbatim.
    3. **RED test** - complete, runnable test code that fails today for the
       expected reason and passes when the task is done correctly. Real
       behavior assertions only; no mocks asserting themselves; follow the
       project's existing test conventions and file layout. If the task
       needs several test files, provide each in full.
    4. **Expected RED failure** - the error/message the suite shows before
       implementation exists.
    5. **Out of scope** - what this task must NOT do (YAGNI fence).

    Rules:
    - English only, regardless of the developer's language. (Exception:
      user-facing UI strings inside test fixtures may use the product's
      established locale.)
    - The coder who reads this will NOT edit tests. Make the tests final:
      correct, conventional, complete.
    - If an interface you need does not exist yet, define it in the brief's
      Exact Values section as a binding contract.

    Return ONLY the brief markdown, no preamble, no closing commentary.
```

**Placeholders:**
- `[STRATEGIC TIER]` - the model recorded at the gate
- `[THE TASK'S PLAN ENTRY VERBATIM]` - one element of `plan.json.tasks`

**Orchestrator after the dispatch:** save output verbatim to
`<workspace>/task-N-brief.md`; materialize the test files; run the suite;
confirm failure matches section 4. Mismatch = defective brief: ledger
`arbitration`, re-dispatch the Controller naming the defect.
