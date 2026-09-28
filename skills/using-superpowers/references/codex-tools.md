# Codex subagents and scripted workers

Codex offers two distinct ways to delegate work. Keep their interfaces
separate.

## Model-directed Codex subagents

When the current Codex session exposes collaboration tools, use the actual
tool names and schemas shown in that session. Assign bounded tasks, pass only
the context each child needs, and wait for its result before integrating
dependent work. Tool availability and supported options come from the active
Codex host/session; do not infer them from an old version table or assume
another Codex surface exposes the same tools.

Codex multi-agent settings and tool behavior can change. For current setup,
consult the [Codex configuration reference](https://developers.openai.com/codex/config-reference/)
and the [multi-agent guide](https://developers.openai.com/api/docs/guides/agents-api/multi-agent/).
The hosted Agents API multi-agent feature is an API orchestration contract;
its request fields are not automatically Codex CLI flags or desktop tool
arguments.

## Script-launched worker sessions

The packaged pipeline adapters launch separate command-line workers. The
Codex adapter validates the shared request and a separate runtime envelope,
then invokes `codex exec --json` with explicit model, reasoning effort,
developer instructions, JSON Schema output, and UTF-8 prompt text on stdin.
It records stdout events and stderr separately and validates the final output
against the role schema.

Continuation uses an explicit, recorded session ID:

```text
codex exec resume SESSION_ID --json --output-schema SCHEMA.json --output-last-message FINAL.json -
```

Use this only when the stored task-family, role, worktree, model, effort, and
configuration identity matches. Never use a “last session” shortcut or pass a
session ID without identity-checked resume. When recovery explicitly selects a
fresh context, start `codex exec` without the old ID and record the context
reset. See the [Codex CLI command reference](https://learn.chatgpt.com/docs/developer-commands)
and the packaged [worker runtime guide](../../two-model-sdd-pipeline/references/worker-runtime.md).

OpenCode uses its own adapter and session semantics. Backend selection is
explicit for new calls; invalid or unavailable Codex configuration never
falls back to OpenCode. Fake CLI fixtures verify argument construction and
contract handling, but do not prove live provider permission behavior.

The plan-driven Codex pipeline is wired through the packaged
`run-codex-pipeline` launcher and the shared deterministic orchestrator. Use
the Codex acceptance matrix for the exact live and offline evidence boundary;
launching one worker alone is not evidence that the full pipeline passed.
