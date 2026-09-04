# Brief-Writing Guidance for the Strategist Session (B)

This is NOT a dispatch template anymore. The strategist is the interactive
session (B) itself — you write task briefs directly, no Controller subagent
(Item 1). Script A consumes your brief verbatim: it materializes the RED tests,
verifies the expected failure, and dispatches the Coder.

## When you write a brief

B writes one brief per task, just-in-time (never batched upfront — tests must
not go stale against interface changes made by earlier tasks). Script A feeds
you the affected-dependency subgraph (`graphify-subgraph` output,
`<ws>/task-N-interfaces.md`) and the review side-effects before you write the
next brief.

## Brief structure (in order)

1. **Task statement** — what to build and why it matters, in 3-6 sentences an
   Operational-tier coder can act on without asking questions.
2. **Exact values** — every number, magic string, file path, signature, and
   format the task needs, stated once, verbatim.
3. **RED test** — complete, runnable, BLACK-BOX behavioral test code (per the
   pipeline's TDD rule: integration/behavior, never internal implementation
   details — do not constrain the Coder's internals). Fails today for the
   expected reason; passes when the task is done correctly. Follow the
   project's existing test conventions and file layout. If several files are
   needed, provide each in full.
4. **Expected RED failure** — the short verbatim substring the failing output
   must contain (a few words). The red-gate verifies it.
5. **Out of scope** — what this task must NOT do (YAGNI fence).

The brief's RED-TESTS block MUST be followed by an EXPECTED-RED block:

```
RED-TESTS:
<workspace>/task-N-test.dart -> test/task_N_test.dart

EXPECTED-RED:
<verbatim substring the failing output must contain>
```

## Rules

- English only, regardless of the developer's language. (Exception: user-facing
  UI strings inside test fixtures may use the product's established locale.)
- The Coder who reads this will NOT edit tests and will NOT run commands.
  Make the tests final and the brief self-contained.
- If an interface you need does not exist yet, define it in Exact Values as a
  binding contract.
- Query the graph subgraph first (via `scripts/cmd --full-file
  <ws>/task-N-graphify.txt -- graphify explain "Node"`) for the interfaces
  earlier tasks established; write from the subgraph + the plan entry, never
  whole files.
- TEST_DEFECT care: if the Coder reports TEST_DEFECT (or red-gate flags a
  defective brief), re-examine the RED test you wrote — a compile error in
  test setup instead of the missing symbol means the brief is defective.
  Reissue via arbitration, never silently "fix" the test through the Coder.

## Corrective briefs

When D sends back a task (SEND_BACK), B writes a corrective brief. The
corrective brief goes to `<workspace>/task-N-corrective.md` — a distinct path
that never overwrites the original `task-N-brief.md`. The same Coder session
resumes via `dispatch --continue --session <id>`; the corrective-round resume
prompt explicitly tells the model the brief has CHANGED and to re-read it fully.

Follow the same structure (Task statement, Exact values, RED test, Expected
RED failure, Out of scope) but incorporate D's findings and the corrected
requirements.