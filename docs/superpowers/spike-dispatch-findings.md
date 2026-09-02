# Spike Findings — Headless Subagent Dispatch via `opencode run`

- **Date:** 2026-09-02
- **Status:** Verified (linchpin for ADR-0001 / the script-autonomous design)

## Question

Can Script A dispatch the Coder and Reviewer subagents headlessly (no main-agent
`task` tool) so the interactive session stays out of the per-task hot path?

## Findings

### 1. `mode: subagent` agents are NOT targetable headlessly

`opencode run --agent two-model-coder --format json "..."` with the agent defined
as `mode: subagent` produced:

```
! agent "two-model-coder" is a subagent, not a primary agent. Falling back to default agent
```

The command exited 0 but ran the **default** agent, not the coder. Subagent-mode
agents cannot be launched by `opencode run --agent`.

### 2. `mode: all` makes an agent headlessly targetable

Changing `two-model-coder.md` from `mode: subagent` to `mode: all` removed the
fallback warning. The subsequent run executed the coder agent: it performed a
real `tool_use` (wrote a file — proving edit access) and finished with a `text`
event. `all` keeps task-tool/subagent usability while adding primary targeting.

### 3. JSON event stream shape

`--format json` emits one JSON object per line:
- `{"type":"step_start", ..., "sessionID":"ses_...", ...}`
- `{"type":"tool_use", ..., "part":{"type":"tool","tool":"write","state":{...}}, ...}`
- `{"type":"text", ..., "part":{"type":"text","text":"<agent reply>"}, ...}`
- `{"type":"step_finish", ..., "part":{"reason":"stop","tokens":{...}}, ...}`

`sessionID` is present on every event — the resume handle. Agent replies are in
`text` events (for D's JSON verdict: the reply line holds the verdict object).

### 4. Session resume preserves context

`opencode run --agent two-model-coder --continue --session <ID> --format json
"..."` reused the same `sessionID` and returned `RESUME_OK`. The `step_finish`
event showed `cache: {read: 8960}` — the stable prefix (system + brief) is
cache-billed on resume, confirming the ADR-0003 context-retention / ADR-0002
fix-round economics.

### 5. Confirmed command forms

```bash
# fresh dispatch
opencode run --agent <two-model-coder|two-model-reviewer> --format json \
  --file <prompt-file> "<prompt>"

# resume (fix / correction round)
opencode run --agent <NAME> --continue --session <ID> --format json \
  --file <prompt-file> "<prompt>"
```

## Consequences for the implementation plan

- Every dispatched agent must be `mode: all` (coder + reviewer).
- `dispatch` script must tee the JSON stream to a workspace log (observability)
  and extract `sessionID` from the first event for the resume handle.
- The reviewer agent (`two-model-reviewer`, `mode: all`) must be created (Task 10).
- Model check: `two-model-coder` = `opencode-go/mimo-v2.5`; reviewer/strategic =
  `opencode-go/deepseek-v4-flash`.

## Cost note

Three spike runs consumed ~28k tokens total (~$0.0016). The spike confirmed the
mechanism before any build work — the plan's riskiest assumption is retired.