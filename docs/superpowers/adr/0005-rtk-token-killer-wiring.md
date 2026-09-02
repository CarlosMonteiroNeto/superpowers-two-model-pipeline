# ADR-0005: RTK as the wired-in Token Killer for all LLM-facing output

- **Status:** Accepted
- **Date:** 2026-09-02

## Context

RTK (`rtk` 0.46.0) is installed and rich (`rtk test`, `rtk err`, `rtk diff`,
`rtk json`, `rtk read`, ...) but the pipeline barely uses it: `cmd` only maps
git/grep/rg/find/pytest/go-test to `rtk pipe` filters, so `flutter test` and
`flutter analyze` pass through uncompressed. The developer's architecture names
RTK the "Token Killer" with three jobs: minify error logs during the C loop,
strip comments/whitespace from source before sending it to C and D, and trim D's
report.

## Decision

- Extend `cmd`'s filter map: `flutter test` → `rtk test`, `flutter analyze` →
  `rtk err`, git diff → `rtk diff`, JSON parsing → `rtk json`.
- Add `token-kill` script: error-log minification, source minification (comments/
  whitespace) for payloads to C/D, and report trimming for D's JSON verdict.
- RTK remains deterministic and lossless-safe: full output always saved to
  workspace files; only LLM-facing stdout is compressed. `RTK_ENABLED=0` /
  `RTK_BIN` overrides preserved. Nothing a gate verdict depends on is ever
  compressed.

## Consequences

- Token cost on every LLM-facing command drops (the pipeline's cost goal).
- The developer can watch full C/D activity in workspace logs while the session
  sees only compressed views — observability without context pollution.
- Requires a spike to verify `rtk test`/`rtk err` behave on Windows for
  Flutter output shape.

## Alternatives considered

- **Leave `cmd` filters as-is:** rejected — the pipeline's main commands
  (flutter test/analyze) are exactly the ones RTK should compress.
- **Third-party minifier:** rejected — RTK is already installed and zero-dep.