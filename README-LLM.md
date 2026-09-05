# superpowers-two-model-pipeline — LLM/Agent README

This file gives any LLM agent (or coding agent) a complete mental model of
this repository and the development harness it provides. Read it before doing
work. It describes the architecture, the tools, the pipeline phases, the
deterministic scripts, the ordering invariants, and the conventions. Where a
skill is named, invoke it; where a script is named, run it.

## 1. What this is

A fork of [`obra/superpowers`](https://github.com/obra/superpowers) (MIT)
turned into an AI-assisted, **two-tier** development pipeline for
Flutter/Dart apps. The design rule: **LLMs reason and scripts decide** —
mechanical steps are chained into deterministic scripts whose verdict is an
exit code, and LLM calls are **cache-aware** (within-task resume via
`--continue --session`; fresh dispatch when the task changes).

The pipeline is **automatic**: a default OpenCode agent
(`~/.config/opencode/agent/flutter-pipeline.md`) makes every session run
`brainstorming` first and, for Flutter/Dart work, run `flutter-app-pipeline`
end to end.

## 2. Architecture (script-autonomous, two layers)

- **`two-model-sdd-pipeline`** (generic engine): a deterministic **Script A**
  owns the per-task loop — gates, test/analyze decisions, subagent dispatch,
  routing, commits, and graph maintenance. The interactive session **B** is
  the strategist: it writes the plan and per-task briefs + RED tests and
  receives feedback only through script outputs. **C** (Coder, Operational,
  `two-model-coder`) is write-only — it never runs commands. **D** (Reviewer,
  Strategic, `two-model-reviewer`) reviews compiler-approved code and returns
  a structured JSON verdict. State lives in the JSON plan, git history, and a
  script-maintained JSONL **ledger**, never in an LLM's memory.
- **`flutter-app-pipeline`** (Flutter layer, on top): adds package research
  with a corrected Quality Score, the deterministic Flutter scripts, and the
  **RTK-compression + Graphify-before-LLM** ordering rules. It delegates the
  per-task implementation loop back to `two-model-sdd-pipeline`.

**Corollary — script-decided routing.** If a check can be performed by a
script, the script performs it *and* routes straight to the next step,
without waiting for an LLM to read the result and approve it. This applies
recursively: the choice of *which* deterministic check to run (which test
command, which gate script) is itself scripted whenever it's derivable from
the project (`resolve-toolchain` reading marker files, `orchestrator`
reading the ledger's `gate.lang` to pick a gate script) — never asked by
default. A human/LLM question is reserved for genuine ambiguity or missing
data (two ecosystem markers present, no marker at all), asked once, then
recorded so it is never asked again for that branch.

## 3. Environment and tools

| Tool | Role |
|---|---|
| OpenCode | Harness (CLI + agent runtime); `opencode run --agent` is the headless dispatch mechanism |
| Superpowers (this fork) | Skills: brainstorming (grill-with-docs + Incremental Persistence), writing-plans, test-driven-development, two-model-sdd-pipeline, flutter-app-pipeline |
| RTK (`rtk`) | CLI proxy that compresses command output before it reaches an LLM context window (60-90% token savings); also the "Token Killer" (`token-kill` script) |
| Graphify (`graphifyy`) | On-device code knowledge graph; Script A rebuilds it post-commit and extracts the affected-dependency subgraph for B/D |
| Tavily | Programmatic web search for solution research |
| pub.dev API | Package metadata, score, popularity, SDK constraints |
| GitHub REST | Commit recency, issue counts, dependents fallbacks |
| Git / Flutter / Dart | Deterministic mechanics (test, analyze, format, commit) |

## 4. Pipeline phases

1. **Phase 1 — Requirements (once, project-level).**    `1a` commercial requirements
   via brainstorming + grill-with-docs; this also produces the **Category
   Skeleton** — three fields (generic category, specific category, original
   implementations) that drive the template search and per-task dependency
   research downstream.
   `1b` generic technical architecture. Resolved terms persist in `CONTEXT.md`
   + ADRs (architectural path only).
2. **Phase 2 — Research & Planning (per task).** `2a` search (Tavily + reference
   sources) and score candidates with `pkg-score`; then, at project level, run
   `template-search` against the Category Skeleton's specific category (stars
   descending, 3-AUTO_APPROVE stop; fallback to generic ≥70 with the specific
   50–69 group). Score results with `template-score`. `2b` select with the
   developer (as-is / modified / from-scratch); `2c` clone the selected template
   + run `graphify-package` → gap analysis against the plan, then write
   technically complete tasks with `writing-plans` (no code downloaded; lockfile
   only). Pure planning.
3. **Phase 3 — TDD Implementation.** Delegated to `two-model-sdd-pipeline`
   (script-autonomous per-task loop). Flutter additions: `pub-sync` ->
   `red-gate` (dispatches C on RED verified, then chains straight into
   `coder-gate`, which owns every round after that: gate check -> PASS
   (`green-gate` commit + `graphify-update` + dispatch D) | FAIL-with-budget
   (fix prompt + redispatch C with `--continue`) | FAIL-at-4 or TEST_DEFECT
   (stop, `route-next` emits ARBITRATE) -> `route-next` (CORRECTIVE /
   ARBITRATE / NEXT / FINAL_REVIEW). `orchestrator`'s own CODER/REVIEW cases
   only fire on a resumed/interrupted session — the normal path never
   returns to B between rounds.
   Every LLM-invoked command runs through `scripts/cmd` (RTK compression).
4. **Phase 4 — Project-Wide Review.** Revalidate with `green-gate --no-commit`,
   full code review, corrections re-enter Phase 3.

## 5. Roles and tiers

| Role | Tier | Responsibility |
|---|---|---|
| Script A | none (deterministic) | gates, test/analyze decisions, dispatch C/D, routing, commits, graph, ledger; never implements/reviews itself |
| B (strategist session) | Strategic (human) | brainstorming, plan.json, per-task briefs + RED tests, corrective briefs, TEST_DEFECT arbitration, final review (fresh `/new` session) |
| C (Coder) | Operational (`two-model-coder`, `mode: all`) | write-only implementation against a RED test; never runs commands; max 4 attempts (round 1 + 3 fixes), resume within task |
| D (Code Reviewer) | Strategic (`two-model-reviewer`, `mode: all`) | JSON verdict (APPROVED / SEND_BACK / ESCALATE) on compiler-approved code; never runs test/analyze |
| Strategic Coder | REMOVED | escalation is B arbitration (`ARBITRATE`) |

Always dispatch via `scripts/dispatch`, which targets the named agent
definition explicitly; omitted model silently inherits the expensive session
model. Both tier agents are `mode: all` (spike-verified: subagent-mode agents
cannot be targeted headlessly by `opencode run --agent`).

## 6. Deterministic scripts (no AI involvement)

| Script | Purpose | Verdict |
|---|---|---|
| `cmd --full-file FILE -- CMD...` (two-model) | Generic command runner: runs any LLM-invoked command, saves the FULL output to FILE, prints the RTK-compressed view on stdout, returns the command's true exit code. `flutter test`/`flutter analyze` compress via `rtk test`/`rtk err` wrappers derived from the file (verdict from the raw run — wrappers mask child exit codes) | exit = command's exit code; 2 usage |
| `dispatch --agent NAME --task N [--continue SESSION] --prompt-file FILE --log LOG` (two-model) | Headless subagent launcher: `opencode run --agent <def> --format json`, tees the JSON event stream to LOG (observability), records the session id for resume. The brief is passed as a positional so opencode auto-attaches it (never `--file` — this opencode version misparses the message when `--file` is present). On `--continue` (corrective round) the prompt explicitly tells the resumed model the brief has CHANGED and to re-read it fully. Refuses (exit 3) when the targeted agent is not `mode: all` (fallback to the default agent would silently break the tiers) | exit = opencode's exit; 2 usage; 3 not a primary agent |
| `session-clean WS TASK\|all` (two-model) | Session hygiene: deletes the opencode sessions a completed task recorded (`task-N-*-session.txt`), so headless dispatches never pollute the interactive session history. Orchestrator runs it on `NEXT` (that task) and `FINAL_REVIEW` (all tasks) | exit 0 best-effort; 2 usage |
| `orchestrator WS TASK [TOTAL]` (two-model) | Thin per-task driver: runs `route-next`, executes the emitted action, prints `OUTCOME:` for B | exit 0 handoff; 1 inconsistent; 2 usage |
| `token-kill err\|src\|json FILE` (two-model) | RTK minification of LLM-facing payloads (error logs, source, JSON reports); lossless fallback to raw | exit 0 ok; 2 usage |
| `run-gates WS TEST ANALYZE` (two-model) | Generic green approval: full suite + analysis through `cmd` (language-agnostic mirror of green-gate) | exit 0 green; 1 tests failed; 2 analysis failed; 3 usage |
| `orient-llm [REPO]` | Brainstorming pre-flight: locate and print this repo's `README-LLM.md` so the agent is oriented on how to run the pipeline | exit 0 printed; 1 missing (gate — stop); 2 usage |
| `pkg-score PACKAGE` | Fetch pub.dev + GitHub, compute the corrected Quality Score | JSON + gate verdict (AUTO_APPROVE / DEVELOPER_DECISION / AUTO_REJECT) |
| `template-search CATEGORY` | Search GitHub for project templates in the given category (stars descending, 3-AUTO_APPROVE stop; fallback to generic ≥70 with the specific 50–69 group) | JSON list of candidates with scores |
| `template-score TEMPLATE` | Score a project template candidate (stars, recency, Flutter/Dart readiness, issue ratio, sustained interest, license, README) | JSON + gate verdict (same semantics as pkg-score) |
| `pub-sync [PACKAGE]` | `pub add`/`pub get` + lockfile; `pub upgrade --dry-run` conflict report | exit 0 resolved; exit 1 conflicts (`pub-sync-report.txt`) |
| `red-gate WORKSPACE TASK` | Materialize brief RED tests; verify the failure is the **expected reason** (brief's `EXPECTED-RED:` text must appear in the report). **On success dispatches C, then chains into `coder-gate`** — the whole per-task loop runs to completion (or budget-exhausted/TEST_DEFECT) in one call | exit = `coder-gate`'s exit; exit 1 defective brief (no dispatch); exit 2 usage |
| `red-gate WORKSPACE TASK [TEST_CMD]` (two-model, generic) | Language-agnostic mirror of the Flutter `red-gate` above, for non-Flutter branches: same materialize-and-verify-expected-reason logic, but the test command comes from the ledger's `gate.test_cmd` (written by `resolve-toolchain`) instead of a hardcoded `flutter test`. Same dispatch-C-then-`coder-gate` behavior | exit = `coder-gate`'s exit; exit 1 defective brief; exit 2 usage/no test_cmd |
| `coder-gate WORKSPACE TASK` (two-model) | Closes the gap that used to require B between rounds: after **every** Coder round (round 1 from `red-gate`, or a resume), runs the gate (`green-gate` for lang=flutter, `run-gates` otherwise), ledgers `coder_round`, and decides by exit code/log content alone — PASS → commit (generic engine) or `green-gate` already committed (Flutter) + `review-package` + dispatch D; FAIL and budget left → build the fix prompt (prior diff + gate report + brief, pure path interpolation) and redispatch C with `--continue`; FAIL at round 4 → stop, `route-next` will ARBITRATE; `TEST_DEFECT` seen in the round's log → ledger `escalated` and stop immediately, no more retries | exit 0 green+committed+D dispatched; 1 budget exhausted; 2 TEST_DEFECT escalated; 3 usage |
| `resolve-toolchain WORKSPACE [ROOT]` (two-model) | One-time-per-branch, no-LLM detection: inspects `ROOT` for a known ecosystem marker (`pubspec.yaml`, `Cargo.toml`, `go.mod`, `package.json`, `pyproject.toml`/`requirements.txt`) and resolves `TEST_CMD`/`ANALYZE_CMD`; on success chains directly into `ledger-append` (`gate` entry). This is what lets `orchestrator` pick the right `red-gate` and lets the generic `red-gate`/`run-gates` run without ever asking | exit 0 resolved + ledgered; exit 1 ambiguous (multiple markers — manual fallback); exit 2 usage/no marker (manual fallback) |
| `green-gate [--no-commit] [-m MSG] [-l LEDGER] [-w WS -t TASK -b BASE]` | Chain `flutter test` + `flutter analyze` + format + commit. On commit: `graphify-update` + review package + **dispatches D**. `--no-commit` never commits/never dispatches | exit 0 green (+commit +graphify +D); 1 tests; 2 analyze; 3 format |
| `graphify-update [ROOT]` | Rebuild project graph via `graphify update <root>` — post-commit only (ADR-0004) | exit code of graphify; 0 when disabled |
| `graphify-subgraph WS TASK` | Query the graph (`explain`) for the task's `touches` nodes; write `<ws>/task-N-interfaces.md` (capped) for B/D | exit 0 wrote; 2 usage/unknown task |
| `graphify-regen [ROOT]` | Rebuild project graph via `graphify update <root>` (real CLI form); Script-A-side, post-commit | exit code of graphify |
| `graphify-package PACKAGE` | Build graph for a downloaded dependency via `graphify update <pkg_dir>` (B feed from `pub-sync`) | resolves dir from `.dart_tool/package_config.json` |
| `route-next WORKSPACE TASK [TOTAL]` | Deterministic router: reads the ledger, emits the next action (BRIEF / RED / CODER N ROUND / REVIEW / CORRECTIVE / ARBITRATE / NEXT / FINAL_REVIEW) | exit 0 routed; 1 inconsistent; 2 usage |
| `red-integrity WORKSPACE TASK` | Byte-compare committed tests vs brief RED-TESTS | exit 0 intact; 1 tampered; 2 usage/missing |
| `review-package WORKSPACE BASE HEAD [OUTFILE] [TASK]` | Build a review bundle (commits + stat + diff). When `TASK` is given, inlines `task-TASK-brief.md` and `task-TASK-interfaces.md` (if present) ahead of the commit list so the Reviewer receives the brief + interfaces in the single `--prompt-file` package | exit 0 wrote; 2 usage |
| `keep-discard WORKSPACE TASK` | Escalation pre-gate: empty diff / out-of-scope files → DISCARD; else KEEP | exit 0 KEEP; 1 DISCARD; 2 usage |
| `interface-check WORKSPACE TASK BASE` | Diff touched a file another task consumes (plan.json) | exit 0 clean; 1 interface changed; 2 usage |
| `final-gate WORKSPACE TOTAL_TASKS` | Pre-holistic: all complete + no unresolved verdicts + no blocking parked + tests/analyze green | exit 0 ready; 1 blockers; 2 usage |
| `doc-check [REPO]` | Deterministic gate: pipeline files changed → READMEs must also change | exit 0 OK; 1 violation; 2 usage |
| `parse-review LOGFILE OUTFILE` (two-model) | Deterministic parser: reads the Reviewer's JSONL event log, extracts the structured verdict, writes it to a JSON file. Run after D's log lands | exit 0 verdict written; 1 no verdict / read error / write error; 2 usage |

All scripts honor `FLUTTER_BIN`, `DART_BIN`, `GIT_BIN`, `GRAPHIFY_BIN`, `RTK_BIN`,
`DISPATCH_BIN`, `OPENCODE_BIN` env overrides. `cmd` also respects `RTK_ENABLED=0`
(passthrough) and `RTK_BIN` (binary override); if RTK has no filter/wrapper for a
command it passes the full output through — nothing is lost. `pub-sync` keeps the
graphify-package chain (B feed, non-fatal; disable with `GRAPHIFY_ENABLED=0`);
`graphify-update` runs post-commit only; `red-gate`/`green-gate` dispatch C/D on
success but never read the graph. Tests live in
`skills/flutter-app-pipeline/tests/` (flutter scripts) and
`skills/two-model-sdd-pipeline/tests/` (router + cmd runner + dispatch + gates),
run with `run-tests.sh` (`python3 -m unittest discover`).

## 7. Ordering invariants (do not violate)

- **Commands are scripted and RTK-compressed:** every LLM-invoked command
  line (test runs, analysis, git ops, graphify queries) runs through
  `scripts/cmd` — the generic runner saves the FULL output to a workspace
  file and prints the RTK-compressed view on stdout. Raw command output
  never enters an LLM context window. Deterministic gates keep reading full
  files, so nothing a verdict depends on (red-gate `EXPECTED-RED`,
  escalation packages, `red-integrity` byte-compare) is ever compressed.
  `RTK_ENABLED=0` disables compression (passthrough); `RTK_BIN` overrides
  the binary. `flutter test`/`flutter analyze` use the `rtk test`/`rtk err`
  wrapper derivation from the full file — the verdict always comes from the
  raw run (RTK wrappers mask child exit codes, spike-verified).
- **Dispatch is script-owned (ADR-0001):** red-gate dispatches C on RED
  verified; green-gate dispatches D after commit; `orchestrator` executes
  route-next actions. The interactive session is never a link in the
  dispatch chain.
- **C is write-only (ADR-0002):** the Coder never runs test/analyze/git
  commands. Script A decides task tests → full suite → analyze by exit code
  and feeds failures back. Budget: round 1 + 3 fixes (4 attempts), then
  `ARBITRATE` to B.
- **D reviews compiler-approved code only (Item 2):** the Reviewer never
  runs or re-runs test/analyze; scope is design, architecture, spec
  compliance, interface discipline. Returns a structured JSON verdict.
- **Graphify is post-commit + subgraph-only (ADR-0004):** `graphify-update`
  rebuilds the graph only after an approved task's commit — never per Coder
  iteration. `graphify-subgraph` extracts the affected-dependency slice
  (`graphify explain`) into `<ws>/task-N-interfaces.md` for B's next brief
  and D's review. The graph exposes structure, not method bodies.
- **Gates are exit codes:** never judge "did the test fail for the expected
  reason" or "are tests green" by reading output — run the gate script and read
  its exit code. The red-gate additionally verifies the failure reason against
  the brief's `EXPECTED-RED:` text.
- **Routing is scripted:** after every review outcome (and every earlier
  ledgered transition) run `route-next` and execute its emitted action — the
  LLM never decides "APPROVED → next task" or "SEND_BACK → corrective" by
  reasoning. SEND_BACK → `CORRECTIVE` (B writes a corrective brief);
  ESCALATE / coder overflow → `ARBITRATE` (B validates the brief/test).
- **Cache-aware calls:** C and D retain their sessions WITHIN a task until D
  approves (fix/correction rounds resume via `--continue --session`; the
  provider cache-bills the stable prefix — system + plan + brief +
  interfaces); when the task changes, dispatch fresh. B holds the session
  for plan + briefs; the final review is a fresh `/new` session.
- **Review pre-gates are exit codes:** `red-integrity` byte-compares committed
  tests vs brief (no LLM judgment); `interface-check` detects cross-task
  interface touch via plan.json; `keep-discard` decides the mechanical fate
  of partial work; `final-gate` verifies all tasks complete, no unresolved
  verdicts, no blocking parked findings, and tests/analyze green before the
  holistic review.
- **Ledger via script:** the ledger is appended through `ledger-append`, never
  free-handed as prose.
- **Workers never commit:** only Script A (via `green-gate` or the
  orchestrator) commits.
- **Observability without pollution:** C/D progress is teed to workspace logs
  (`task-N-coder.log`, `task-N-reviewer.log`); the developer can tail them;
  headless sessions never pollute the main session's history.
- **No approval after decisions:** approval happens at the gate (once per
  branch) and at Phase 2a/2b selection; from Phase 2c onward the branch runs
  to completion without check-ins. The ledger is the state checkpoint —
  compaction-safe by construction (stateless dispatches + `route-next` resume
  from the ledger after any harness auto-compaction).

## 8. Quality Score (0–100)

### pkg-score (package evaluation)

| Criterion | Weight | Scoring |
|---|---|---|
| Pub points | 20 | (points / 160) × 20 |
| Popularity | 10 | popularity% × 10 |
| Last commit recency | 20 | <3mo=20 / 3–6mo=12 / 6–12mo=5 / >12mo=0 |
| Flutter/Dart SDK compatibility | 20 | compatible=20 / needs override=7 / incompatible=0 |
| Dependents count | 15 | ≥50=15 / 10–49=9 / 1–9=4 / 0=0 |
| Open/closed issue ratio | 15 | <20% open=15 / 20–40%=7 / >40%=0 |

Health signals (recency + SDK + issue ratio) sum to **55**.

Corrections: **/160 not /140** (pub.dev max is 160); issue ratio is **PR-aware**
(`open_issues_count` includes PRs — use `search/issues?type=issue`); dependents
have no official endpoint (best-effort scrape or `pub_api_client`); no-GitHub
packages fall back to `latest.published`.

Gate: ≥70 auto-approve; 50–69 developer decision; <50 reject -> from-scratch.

### template-score (project template evaluation)

| Criterion | Weight | Scoring |
|---|---|---|
| Stars | 30 | ≥1000=30 / 300–999=24 / 100–299=18 / 30–99=12 / 10–29=6 / <10=0 |
| Recency | 20 | <3mo=20 / 3–6mo=12 / 6–12mo=5 / >12mo=0 |
| Flutter/Dart readiness | 20 | current SDK + null-safe pubspec=20 / dated SDK=10 / not Flutter=0 |
| Open/closed issue ratio | 10 | <20% open=10 / 20–40%=5 / >40%=0 |
| Sustained interest (stars ÷ repo age) | 10 | ≥10/yr=10 / 1–10/yr=6 / <1/yr=2 |
| License | 5 | MIT/Apache/BSD=5 / other=3 / none=0 |
| README quality (setup + structure docs) | 5 | full setup docs=5 / partial=2 / none=0 |

Stars is the primary search sort key (used by `template-search` to order
candidates descending). Same gate semantics as pkg-score (≥70 auto-approve;
50–69 developer decision; <50 reject).

### Category Skeleton

The Category Skeleton is produced during Phase 1a and contains three fields:
the **generic category**, **specific category**, and **original implementations**.
These fields drive the `template-search` query (specific category first) and the
per-task dependency research in Phase 3.

## 9. GitHub authentication

GitHub REST: 60 req/h unauthenticated, 5000 req/h authenticated. Set a
fine-grained PAT (public read only) as `GITHUB_TOKEN` (env or CI secret). Never
hardcode or commit tokens. `pkg-score` reads the env var automatically.

## 10. Language policy

All responses and all internal artifacts are in **English** — task briefs, RED
tests, design docs, `CONTEXT.md`, ADRs, ledger summaries, review reports, commit
messages, code comments — regardless of the developer's language. The one
exception is the software's **UI** (user-facing strings, labels, copy), which
defaults to the developer's language (pt-br). Rationale: English-only context
artifacts reduce tokens per artifact and avoid context inflation.

## 11. Self-update and repository documentation

The pipeline keeps itself in sync with its GitHub repository:

- The OpenCode plugin loads from a vendored git checkout of the fork
  (`~/.config/opencode/vendor/superpowers`), decoupled from npm.
- The self-update scripts live in the fork's `scripts/` dir and auto-detect
  the checkout dir (or take it as the first argument): `check-superpowers`
  compares the local checkout SHA against `origin/main`
  (exit 0 up to date, exit 1 behind, exit 2 not installed).
- `sync-superpowers` fetches + resets to `origin/main`, then runs the pipeline
  test suite; exit 1 if the new copy fails its tests (refuses to reset over
  uncommitted changes).
- `install-superpowers` clones the fork fully when nothing is installed (exit 2
  = it refused to clobber a non-empty, non-repo path); it verifies with the
  pipeline test suite.
- At session start the agent runs `scripts/check-superpowers`; if behind it
  runs `scripts/sync-superpowers`, if not installed it runs
  `scripts/install-superpowers`, and in either case asks the developer to
  restart OpenCode (skills load at session start).
- **End-of-session:** if a session changed the pipeline itself (scripts,
  skills, invariants, phases), update `README.txt` and `README-LLM.md` to
  reflect the changes and include them in the push. Do not churn docs when
  behavior did not change. `scripts/doc-check` enforces this deterministically.

### Tier agents (reference OpenCode setup)

On the reference machine the tiers are fixed agent definitions (both
`mode: all` so `opencode run --agent` can target them headlessly):

| Tier | Agent | Model |
|---|---|---|
| Strategic (D, B-side judgment) | `two-model-reviewer`, `two-model-controller` | `opencode-go/deepseek-v4-flash` |
| Operational (C) | `two-model-coder` | `opencode-go/mimo-v2.5` |

No `variants` block is used; the model is selected by the agent definition.
The repo mirrors these definitions under `agent/` for versioning.

## 12. Repository layout

```
README.txt                        <- this repo's human-facing readme
README-LLM.md                     <- this file (agent-facing)
CONTEXT.md                        <- resolved glossary (architectural path)
agent/                            <- mirrored tier agent definitions (coder/reviewer/controller)
docs/superpowers/adr/             <- accepted architecture decisions
docs/superpowers/specs/           <- branch design specs
docs/superpowers/plans/           <- implementation plans
skills/flutter-app-pipeline/SKILL.md
skills/flutter-app-pipeline/scripts/     <- deterministic scripts (bash + python3)
skills/flutter-app-pipeline/tests/       <- python unittest suite (run-tests.sh)
skills/two-model-sdd-pipeline/SKILL.md
skills/two-model-sdd-pipeline/scripts/   <- pipeline-workspace, ledger-append, cmd, dispatch,
                                            orchestrator, token-kill, run-gates, review-package,
                                            route-next, doc-check, parse-review
```

## 13. How to work with this harness

1. New dev request -> invoke `brainstorming` before any code. Its pre-flight
   runs `scripts/orient-llm` deterministically, which prints this
   `README-LLM.md` as orientation before anything is classified or designed.
2. Flutter/Dart work -> run `flutter-app-pipeline`; on the two-tier gate default
   to YES. Tiers are pre-configured locally (`two-model-coder` /
   `two-model-reviewer` agents); ask only for the test/analyze commands, once per
   branch — and ask about tiers only when the local pipeline is not installed.
3. Per task: `pkg-score` candidates -> select with the developer -> `writing-plans`
   tasks -> `pub-sync` -> B writes the brief -> `red-gate` (expected-reason
   check; dispatches C) -> Script A gates (task tests -> full suite -> analyze;
   resume C up to 4 attempts) -> `green-gate` (commit + `graphify-update` +
   dispatch D) -> `red-integrity` (byte-compare) -> D JSON verdict ->
   `route-next` -> `orchestrator` hands `OUTCOME` to B. SEND_BACK →
   `CORRECTIVE` (B writes corrective brief to `task-N-corrective.md`,
   never overwriting `task-N-brief.md`; resume C via `--continue --session`
   with a corrective-round prompt that tells the model the brief has
   CHANGED and to re-read it fully); ESCALATE / overflow → `ARBITRATE` (B
   rules). After all tasks: `final-gate` then B's fresh `/new` holistic review.
   The router, not the LLM, decides every transition. All command lines go
   through `scripts/cmd`; Graphify is post-commit + subgraph-only.
4. Non-Flutter work: standard superpowers flow (brainstorming + TDD), no Flutter
   layer.