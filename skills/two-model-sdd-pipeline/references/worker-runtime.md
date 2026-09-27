# Worker runtime compatibility

This guide describes the packaged task-worker adapters. It does not describe a
complete autonomous pipeline: the R3 plan driver is not wired yet. The Codex
and OpenCode workers consume the same strict request/result contracts while
using separate launch, event, session, policy, and cancellation behavior.

## Package contents and relocation

The rootless Codex package contains the whole `skills/` tree. The worker
runtime is self-contained under this skill; its schema paths are resolved
relative to the packaged scripts, not to the repository checkout. Relevant
entry points and contracts are:

- `../scripts/dispatch` selects a backend. `--backend codex` and
  `--backend opencode` are explicit selections. Existing calls without a
  selector retain the legacy OpenCode behavior for compatibility.
- `../scripts/dispatch-codex` accepts a strict normalized request file and a
  separate runtime envelope supplied through `CODEX_RUNTIME_JSON`.
- `../scripts/dispatch-opencode` preserves the legacy OpenCode CLI behavior.
- `../schemas/worker-request.schema.json` and
  `../schemas/worker-result.schema.json` define the shared external contract.
- `../codex/operator.md`, `../codex/reviewer.md`, and `../codex/director.md`
  define Codex role instructions. The matching `../opencode/` files are kept
  backend-specific.

Build a local delivery archive with `scripts/package-codex-plugin.sh`. That
script archives committed plugin content and restores required OpenAI skill
metadata from a supplied metadata directory or archive. `scripts/sync-to-codex-plugin.sh`
is a separate repository-sync workflow; it can push and open a PR, so inspect
its dry-run before any publication workflow. Neither package smoke tests nor
fake-runtime fixtures make a publication decision.

## Shared request and result

The normalized request is validated against the R1 contract and rejects extra
fields. Backend runtime configuration, capability reports, executable argv,
role instructions, and explicit recovery controls are passed separately; do
not add these values to the normalized request. The result binds run, task,
role, worktree, plan, model, effort, configuration, session, transport status,
and a strict role-specific output payload.

Codex uses `codex exec --json`, UTF-8 prompt input on stdin, a JSON Schema
output constraint, and a separate final-output file. Continuation is allowed
only as `codex exec resume SESSION_ID` after the recorded session identity
matches the task family, role, worktree, model, effort, and configuration.
There is no “last session” lookup. An explicitly selected fresh recovery
starts a new `exec` and records `context_reset`. Progress events do not count
as a semantic result; the adapter requires a successful terminal event,
matching thread identity, exit status zero, and valid final JSON.

OpenCode remains behind its own adapter and retains its legacy run/resume
flow. Unknown backend values, missing Codex capability, or malformed
requests fail closed. There is no provider fallback between adapters.

## Compatibility and evidence

| Backend and surface | Verified here | Unknown or not claimed |
|---|---|---|
| Codex adapter contract | Fake CLI and contract fixtures; request/result validation; fake fresh/resume, malformed and mismatched-session cases; source-level Windows process handling | Live Codex CLI version/model/auth behavior; provider permissions; native Windows process-tree behavior; Linux/macOS execution for this round |
| OpenCode adapter contract | Legacy CLI wrapper fixtures and cross-backend no-fallback checks | Live OpenCode model/auth/policy behavior; provider permissions; Linux/macOS execution for this round |
| Archive packaging | Disposable metadata fixture; archive extraction and required path checks | Marketplace installation and runtime behavior after installation |

Fixture success does not prove live provider permissions. Both backends'
live model, authentication, and policy behavior remain unverified until an
opt-in probe is run with a confirmed model and captured evidence. Automated
tests do not authorize real inference, publishing, or session deletion.

Codex process cancellation is restricted to a process whose PID and start
identity were recorded by this run. OpenCode cancellation reports unsupported
until its adapter has a verified owned-process cancellation API. Completed
Codex local evidence defaults to 30-day retention; active or unresolved runs
are preserved. Provider-side Codex session deletion is not implemented.
