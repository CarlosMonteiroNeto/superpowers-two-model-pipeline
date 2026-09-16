# ADR-0016: The operador runs its own tests through a scoped runner

- **Status:** Accepted
- **Date:** 2026-09-16
- **Related:** ADR-0002 (write-only coder, superseded), ADR-0007 (coder-owned RED/GREEN loop), ADR-0005 (RTK wiring)

## Context

ADR-0007 gave the Agente operador its own RED/GREEN loop, which is why it must
run tests. Two costs came with it:

1. **The operador ran the FULL suite.** Nothing forbade it, and it is rational
   insurance against a gate FAIL round - but the brief only ever asked for the
   task's own tests, and `coder-gate` runs the authoritative full suite + analyze
   anyway. A full Flutter suite is minutes per task, paid twice for no verdict.
2. **Its test output entered its context raw.** The RTK-compression invariant
   ("every LLM-invoked command line runs through `scripts/cmd`") is enforced by
   the gate scripts calling `cmd`; the operador's own bash calls do not. Its
   allowlist (`"*": deny` + `flutter test*` etc.) also blocks `cmd`, because the
   command string starts with `cmd`. So the operador is structurally unable to
   take the compressed path, and every `flutter test` it runs lands
   uncompressed in its context window.

Handing the operador the generic `cmd` is not an option: `cmd -- COMMAND`
accepts ANY command after `--`, so a `"cmd*": allow` entry would silently grant
arbitrary execution - a far bigger hole than the token cost it closes.

## Decision

1. **A scoped runner, `skills/flutter-app-pipeline/scripts/rtk-run`.** It accepts
   exactly three modes and nothing else:
   - `red   <test-file...>` -> `flutter test --machine ARGS`, full output to
     `WS/task-N-red.txt` (the exact path `red-form-check` reads);
   - `test  <test-file...>` -> `flutter test ARGS`, full output to
     `WS/task-N-test.txt`;
   - `analyze [ARGS...]`    -> `flutter analyze ARGS`.

   It delegates to `cmd`, so the operador's context sees the RTK-compressed view
   while the full output stays on disk. Because the mode is a closed set, the
   bash allowlist can permit this one absolute path without granting arbitrary
   execution.

2. **The brief mandates it and forbids the full suite.** `brief-scaffold`'s RED
   order now names the absolute `rtk-run` path, tells the operador to run RED and
   GREEN through it, and states: *do not run the full test suite - `coder-gate`
   owns it*, with an explicit escape hatch for a change with cross-cutting
   impact.

3. **The operador agent definition documents both rules** (live definition and
   the repo mirror).

The direct `flutter test`/`flutter analyze` allowlist entries are deliberately
KEPT: they are the fallback that keeps a malformed brief from blocking the
operador. The brief rule, not the permission, is what removes the duplication.

## Consequences

- A task's operador no longer pays for the full suite; the authoritative suite
  runs once, in `coder-gate`.
- The operador's test output is compressed, so its context stops carrying raw
  runner output - the token cost ADR-0007 accepted arrives much reduced.
- The RED evidence path is produced by the runner itself, removing the
  hand-redirection the brief used to require.
- The scoped runner is Flutter-specific; another ecosystem needs its own
  (`pytest` already has an RTK pipe filter, so the same shape applies).
- Residual risk: an operador that ignores the brief can still call `flutter test`
  raw. That costs tokens, not correctness - the gate is unchanged.

## Alternatives considered

- **Allow the generic `cmd` in the operador's allowlist:** rejected - `cmd`'s
  `-- COMMAND` interface is arbitrary execution wearing a wrapper's name.
- **Hard-deny the direct `flutter test`/`analyze` commands** so only `rtk-run`
  works: rejected for now - a brief/scaffold defect would then BLOCK the
  operador instead of merely costing tokens. Revisit once the scoped runner has
  a track record.
- **Have the script own the operador's test execution (ADR-0002's shape):**
  already rejected by ADR-0007 - it broke greenfield RED proof and costs a
  round-trip per iteration.
