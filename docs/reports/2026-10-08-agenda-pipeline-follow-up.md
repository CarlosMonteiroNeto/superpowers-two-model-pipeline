# Agenda session pipeline follow-up

## Permanent fixes

- The standard SDD `task-brief` now accepts JSON plans as well as Markdown plans. It preserves the exact selected task and every plan-wide contract, rejects missing/duplicate IDs, and does not invent Markdown task headings. This supports the explicitly authorized native SDD adaptation used by agenda-redesign.
- Structured suite capture now hashes the actual resolved legacy gate descriptor. Previously legacy lookup succeeded, then command hashing raised `KeyError` because it indexed a separate map keyed only by `toolchain_id`.
- Baseline and closing gates now fail with status 3 when structured inventory/evidence capture fails. Passing command exit codes alone cannot produce a PASS record after an evidence traceback. Task/integration behavior is unchanged.

## Existing supported paths retained

- Current OpenCode policy already authorizes exact request-owned `runner_commands`; the scoped runner validates workspace/task and rejects arbitrary trailing commands. No unrestricted shell allowlist was added for the historical scoped-run gap.
- Current impact selection does not force full suites merely because a test file changes. Dependency/build/test configuration, shared infrastructure, generated contracts and unknown impact remain conservative full-suite fallbacks; closing intentionally verifies complete affected suites.
- Toolchain resolution already accepts explicit runtime manifests (`--runtime` / `PIPELINE_RUNTIME_MANIFEST`). Plan-specific analyzer flags must be bound there, rather than silently relaxing analyzer failures globally.
- The packaged Codex entrypoint already binds explicit role models/reasoning through confirmed configuration. Native in-session adaptation is an explicitly authorized SDD workflow; runtime authentication failures do not authorize a silent backend/model switch.

## Verification

The new legacy regression reproduced `KeyError: 'python'` at command hashing before the fix. Targeted tests cover resolved legacy command hashes, exact JSON contract preservation, ambiguous task rejection, and rejecting a closing command that produces no complete suite inventory. Existing impact gate wiring and Markdown workspace extraction are checked alongside these changes. No live model dispatch or credentials are required.

The legacy regression (1 test), JSON/helper and shell-entrypoint regressions (3 tests), and existing impact gate wiring (12 tests) pass. The pre-existing `test-sdd-workspace.sh` has four Windows path-comparison failures: Git returns `C:/...` while Bash `pwd` returns `/c/...`; the extraction/workspace operations themselves succeed. This environment mismatch is unrelated to JSON extraction and is not treated as product success evidence.

Unrelated reuse-foundation plan edits and local attachment/work directories are preserved.

Independent final verification also passed the existing closing-suite checks (6 tests), for 22 passing targeted tests. Code review found no blocking issues.
