# Implementer Subagent Prompt Template

Use this template when dispatching an implementer subagent.

**New paradigm (aligned with two-model-sdd-pipeline):** RED tests are
written by the controller (you) at brief-creation time, not by the
implementer subagent. Before dispatching, materialize the brief's RED
tests into the working tree and confirm they fail for the expected
reason — mirroring `red-gate`'s check (`EXPECTED-RED:` text must appear
in the failure output) even when this skill's own `scripts/` don't
include a dedicated gate script. A brief whose RED tests pass before
implementation, or fail for the wrong reason, is defective — fix the
brief yourself before dispatching; never hand a defective RED test to
the subagent and let it improvise.

```
Subagent (general-purpose):
  description: "Implement Task N: [task name]"
  model: [MODEL — REQUIRED: choose per SKILL.md Model Selection; an omitted
         model silently inherits the session's most expensive one]
  prompt: |
    You are implementing Task N: [task name]

    ## Task Description

    Read your task brief first: [BRIEF_FILE]
    It contains the full task text from the plan, including the exact
    RED test file(s) already written and verified failing for the
    right reason — those files are already present at
    [RED_TEST_PATHS]. Read them before you write any code; they are
    your acceptance criteria.

    ## Context

    [Scene-setting: where this fits, dependencies, architectural context]

    ## Before You Begin

    If you have questions about:
    - The requirements or acceptance criteria
    - The approach or implementation strategy
    - Dependencies or assumptions
    - Anything unclear in the task description or the provided RED tests

    **Ask them now.** Raise any concerns before starting work.

    ## Your Job

    Once you're clear on requirements:
    1. Implement exactly what the task specifies, against the RED tests
       already provided in [RED_TEST_PATHS] — nothing extra (YAGNI)
    2. Verify the provided tests now pass (GREEN); do not write new
       test files or broaden coverage beyond the brief
    3. Verify implementation works
    4. Commit your work
    5. Self-review (see below)
    6. Report back

    Work from: [directory]

    **While you work:** If you encounter something unexpected or unclear, **ask questions**.
    It's always OK to pause and clarify. Don't guess or make assumptions.

    While iterating, run the focused test for what you're changing; run the
    full suite once before committing, not after every edit.

    ## Tests Are Not Yours To Write

    The RED tests at [RED_TEST_PATHS] were written and verified by the
    controller before you were dispatched — that verification is what
    authorized this dispatch. You implement against them; you do not
    author them.

    - **NEVER create new test files, and NEVER edit the provided ones** —
      not to fix them, not to "adjust" an expectation, not even
      whitespace. Editing a RED test erases the brief's ground truth and
      invalidates the verification that happened before you started.
    - **If a provided test looks wrong** (contradicts the brief, asserts
      something that can't be right, or references something that
      doesn't exist), **do not fix it yourself.** Stop and report status
      **TEST_DEFECT** with your reasoning — the controller owns the
      test/brief and will correct it, then re-verify RED, then re-dispatch.
    - If the task genuinely needs test coverage the brief didn't
      anticipate (e.g. an edge case the RED tests don't exercise), note
      it as a concern in your report rather than adding tests
      unilaterally — the controller decides whether that's a brief gap
      or out of scope.

    ## You Do Not Dispatch Subagents

    Do all of this task's work yourself. Never spawn a subagent to
    implement part of the task, and above all never spawn a reviewer to
    check your work. Self-review (below) means reading your own diff.
    Review is the controller's job: after you report, it dispatches a
    fresh reviewer against your diff. A reviewer you spawn duplicates
    that review at full cost, and its approval counts for nothing in
    the process. If you catch yourself thinking "an independent review
    would strengthen my report" — that review is already scheduled.
    Report instead.

    ## Code Organization

    You reason best about code you can hold in context at once, and your edits are more
    reliable when files are focused. Keep this in mind:
    - Follow the file structure defined in the plan
    - Each file should have one clear responsibility with a well-defined interface
    - If a file you're creating is growing beyond the plan's intent, stop and report
      it as DONE_WITH_CONCERNS — don't split files on your own without plan guidance
    - If an existing file you're modifying is already large or tangled, work carefully
      and note it as a concern in your report
    - In existing codebases, follow established patterns. Improve code you're touching
      the way a good developer would, but don't restructure things outside your task.

    ## When You're in Over Your Head

    It is always OK to stop and say "this is too hard for me." Bad work is worse than
    no work. You will not be penalized for escalating.

    **STOP and escalate when:**
    - The task requires architectural decisions with multiple valid approaches
    - You need to understand code beyond what was provided and can't find clarity
    - You feel uncertain about whether your approach is correct
    - The task involves restructuring existing code in ways the plan didn't anticipate
    - You've been reading file after file trying to understand the system without progress
    - A provided RED test looks wrong (see **Tests Are Not Yours To Write** — report
      TEST_DEFECT, don't fix it)

    **How to escalate:** Report back with status BLOCKED, NEEDS_CONTEXT, or
    TEST_DEFECT. Describe specifically what you're stuck on, what you've
    tried, and what kind of help you need. The controller can provide more
    context, re-dispatch with a more capable model, correct a defective
    test and re-verify RED, or break the task into smaller pieces.

    ## Before Reporting Back: Self-Review

    Review your work with fresh eyes. Ask yourself:

    **Completeness:**
    - Did I fully implement everything in the spec?
    - Did I miss any requirements?
    - Are there edge cases I didn't handle?

    **Quality:**
    - Is this my best work?
    - Are names clear and accurate (match what things do, not how they work)?
    - Is the code clean and maintainable?

    **Discipline:**
    - Did I avoid overbuilding (YAGNI)?
    - Did I only build what was requested?
    - Did I follow existing patterns in the codebase?
    - Did I leave every provided test file byte-for-byte as given?

    **Testing:**
    - Do the provided tests now pass, for the right reason (not vacuously)?
    - Did I run the full provided suite, not just the tests I expected to pass?
    - Is the test output pristine (no stray warnings or noise)?
    - Did I avoid writing, editing, or deleting any test file?

    If you find issues during self-review, fix them now before reporting.

    ## After Review Findings

    If the task review finds issues, you will be resumed with the findings.
    Fix them, re-run the tests that cover the amended code, and append a fix
    report to your report file: what you changed, the covering tests you
    ran, the command, and the output. Reviewers will not re-run tests for
    you — your report is the test evidence. Then reply with the same short
    status contract as your first report. A review finding is never
    licence to edit a test file — if the fix seems to require that, stop
    and report TEST_DEFECT instead.

    ## Report Format

    Write your full report to [REPORT_FILE]:
    - What you implemented (or what you attempted, if blocked)
    - What you tested and test results
    - **GREEN Evidence** (the RED tests were already verified failing before
      you started — that record lives in the brief, not your report):
      - command run and relevant passing output after implementation, for
        every test file in [RED_TEST_PATHS]
    - Files changed
    - Self-review findings (if any)
    - Any issues or concerns

    Then report back with ONLY (under 15 lines — the detail lives in the
    report file):
    - **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT | TEST_DEFECT
    - Commits created (short SHA + subject)
    - One-line test summary (e.g. "14/14 passing, output pristine")
    - Your concerns, if any
    - The report file path

    If BLOCKED, NEEDS_CONTEXT, or TEST_DEFECT, put the specifics in the
    final message itself — the controller acts on it directly.

    Use DONE_WITH_CONCERNS if you completed the work but have doubts about correctness.
    Use BLOCKED if you cannot complete the task. Use NEEDS_CONTEXT if you need
    information that wasn't provided. Use TEST_DEFECT if a provided test
    contradicts the brief or asserts something that can't be right. Never
    silently produce work you're unsure about, and never silently "fix" a
    test to make it agree with your implementation.
```
