# ADR-0009: `opencode run` briefs are passed positionally, never via `--file`

- **Status:** Accepted
- **Date:** 2026-09-15

## Context

`dispatch` launches tier agents headlessly with
`opencode run --agent <def> --format json`. The brief file must reach the agent
so it is auto-attached to the run. The dispatch spike
(`docs/superpowers/spike-dispatch-findings.md` §5) originally documented the
confirmed command form as
`opencode run --agent <NAME> --format json --file <prompt-file> "<prompt>"`.

That form is wrong for this opencode version: whenever `--file` is present,
opencode treats the **positional message** as a file path rather than a prompt,
which breaks every run. The implementation already works around it — `dispatch`
passes the brief as the positional argument and passes the framing prompt as a
second positional (`opencode run ... <prompt-file> "<prompt>"`), and its comment
explicitly says `--file` is deliberately NOT used. The spike document contradicted
the code, which is worse than no document: the next agent reading §5 would "fix"
`dispatch` back to `--file` and break the whole pipeline.

## Decision

- The brief is passed as the **first positional** argument to `opencode run`;
  the framing prompt (fresh vs corrective) is the second positional. `--file` is
  never used.
- The harness constraint is load-bearing: it is a property of the opencode
  version the pipeline targets, not a style choice, so it is recorded here rather
  than only in an inline comment.
- `spike-dispatch-findings.md` §5 is marked SUPERSEDED with a pointer to this
  ADR; a regression test
  (`test_dispatch.py::test_brief_is_passed_as_positional_not_file`) asserts no
  `--file` is ever passed.

## Consequences

- `dispatch` remains the only place that constructs the `opencode run` command;
  any change to the invocation must keep the brief positional and must not add
  `--file`.
- A future opencode version that fixes `--file` handling would make this ADR
  revisable — the constraint is version-scoped, and the spike/ADR pair is how the
  next contributor knows which version was assumed.
- The dispatch spike's cost note and any other command-form examples must not be
  copied verbatim into new code; §5 is the single superseded spot.

## Alternatives considered

- **Use `--file <prompt-file>` (the spike's original form):** rejected — this
  opencode version misparses the positional prompt as a path, breaking every run.
- **Pipe the brief on stdin:** rejected — `opencode run` does not auto-attach
  stdin as context the way it attaches a positional file, and it removes the
  "auto-attach" behavior the tier contract relies on.
- **Inline the whole brief in the prompt string:** rejected — the brief is a
  file by construction (`brief-scaffold`), and inlining it bloats and escapes
  the argument, defeating the cache-billed stable-prefix economics of ADR-0003.
