# Codex runtime reference

The root [README.md](../../../README.md) is the canonical operating guide.
This reference records the Codex-specific command and runtime contract without
creating a second installation manual.

## Entry points

From a POSIX shell:

```sh
skills/two-model-sdd-pipeline/scripts/run-codex-pipeline \
  docs/superpowers/plans/PLAN.json --config .superpowers/runtime.json
```

From PowerShell:

```powershell
& .\skills\two-model-sdd-pipeline\scripts\run-codex-pipeline.ps1 `
  -Plan docs/superpowers/plans/PLAN.json `
  -Config .superpowers/runtime.json
```

The runtime configuration must explicitly select `backend: codex`, confirmed
models and reasoning settings for the operator and reviewer, toolchains,
publication (`local` or `pull_request`), and concurrency. The director uses
the reviewer selection unless it has its own confirmed override. New launches
confirm these choices; resume reuses their immutable run manifest. For a
headless launch, record confirmation in the configuration and explicitly pass
`--confirm-hooks-trusted --confirm-policy-clean` after reviewing the packaged
hooks, Codex managed policy, and inherited instructions.

Every role's `model_reasoning_effort` is explicit in the confirmed runtime
configuration. Optional `--publication local|pull_request` and
`--max-parallel N` arguments must match that configuration; they cannot
silently override it.

The Codex launcher selects the Codex adapter before setup and fails closed if
Codex is unavailable. It never falls back to OpenCode. The legacy
`dispatch` command without a backend selector remains the explicit
compatibility path for existing OpenCode callers.

## Run lifecycle

The launcher validates the project plan, configuration, toolchains, installed
bundle and role policies before dispatch. Operator and reviewer calls are
separate sessions with normalized request/result schemas and candidate-bound
evidence. Director corrections are proposals applied by the canonical plan
writer. The closing verdict binds the candidate, plan, spec, ledger and final
verification; publication follows only after approval.

Resume uses the persisted run identity and explicit worker session IDs. Do not
reuse a session across task families or roles. To request cancellation, use
`run-control.py cancel --manifest MANIFEST --run-id RUN_ID`; only processes
whose recorded identities match are stopped. Interrupted state remains
recoverable.

With `publication: local`, completion remains in the local integration branch
and performs no push. With `publication: pull_request`, the authorized
workflow pushes the named branch and opens or reuses a pull request; it never
merges automatically. A publication failure remains resumable.

## Distribution and evidence

`scripts/package-codex-plugin.sh` produces the portal archive.
`scripts/sync-to-codex-plugin.sh` updates the Git-marketplace bundle; review
its dry run before publication. Both routes must carry the skill scripts,
schemas, prompts, hooks, role instructions, and this reference. Package and
fixture tests prove file relocation and contracts, not live service behavior.

Run offline acceptance with:

```sh
skills/two-model-sdd-pipeline/scripts/codex-acceptance --output .work/codex-acceptance
```

The command archives raw scenario logs, tool/platform versions, source commit,
working-tree status, and a source hash. Offline fixtures do not make a live
Codex CLI or OpenCode support claim; they are not a live support claim. To run
the explicit role/session probe, provide a confirmed Codex config with local
publication and confirm the hooks and managed policy:

```sh
skills/two-model-sdd-pipeline/scripts/codex-acceptance \
  --output .work/codex-acceptance \
  --live --config .superpowers/runtime.json \
  --confirm-hooks-trusted --confirm-policy-clean
```

Live mode sends separate role probes using the configured model and reasoning
effort, then resumes the operator with its explicit session ID. The probes do
not edit the disposable project, approve a real candidate, or publish. The
detailed platform evidence and remaining checks are in
[`docs/testing/codex-pipeline-support-matrix.md`](../../../docs/testing/codex-pipeline-support-matrix.md).

R3 is an integration milestone. Bounded 5/3/3 coder cycles, affected-test
selection, baseline waivers and the wired final gates remain R4 requirements
before unattended production use.
