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
       implementation exists. State the expected reason as a short verbatim
       substring (a few words, not a paragraph) that the failing output
       must contain.
    5. **Out of scope** - what this task must NOT do (YAGNI fence).

    The brief's RED-TESTS block MUST be followed by an EXPECTED-RED block
    (the red-gate verifies the failure reason against it):

    ```
    RED-TESTS:
    <workspace>/task-N-test.dart -> test/task_N_test.dart

    EXPECTED-RED:
    <verbatim substring the failing output must contain>
    ```

    Rules:
    - English only, regardless of the developer's language. (Exception:
      user-facing UI strings inside test fixtures may use the product's
      established locale.)
    - The coder who reads this will NOT edit tests. Make the tests final:
      correct, conventional, complete.
    - If an interface you need does not exist yet, define it in the brief's
      Exact Values section as a binding contract.
    - **Query the project graph for structure and interfaces first.** When
      a Graphify graph exists (project root `graphify-out/graph.json` or
      the workspace's graph output), run the graphify query commands through
      the pipeline runner: `scripts/cmd --full-file
      <workspace>/task-N-graphify.txt -- graphify explain "Node"` /
      `scripts/cmd --full-file <workspace>/task-N-graphify.txt --
      graphify path "A" "B"` to discover the signatures and dependencies
      the task touches before writing the brief. Never read whole files to
      find a signature; read only the file(s) the graph points you to.
      **If no graph exists, or it is stale** (older than the last commit
      whose code you need), rebuild it first with `scripts/cmd --full-file
      <workspace>/task-N-graphify.txt -- graphify update <project_root>`
      (best-effort, no LLM API key for code) and then query. Graphify is a
      Controller-side optimization only - if it is unavailable, write the
      brief from the interfaces you are given and the files the plan names.

    Return ONLY the brief markdown, no preamble, no closing commentary.
```

**Placeholders:**
- `[STRATEGIC TIER]` - the model recorded at the gate
- `[THE TASK'S PLAN ENTRY VERBATIM]` - one element of `plan.json.tasks`

**Orchestrator after the dispatch:** save output verbatim to
`<workspace>/task-N-brief.md`; materialize the test files; run the suite;
confirm failure matches section 4. Mismatch = defective brief: ledger
`arbitration`, re-dispatch the Controller naming the defect.
