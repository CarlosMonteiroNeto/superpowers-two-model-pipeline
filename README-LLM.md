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
exit code, and every LLM call is a stateless dispatch fed curated context.

The pipeline is **automatic**: a default OpenCode agent
(`~/.config/opencode/agent/flutter-pipeline.md`) makes every session run
`brainstorming` first and, for Flutter/Dart work, run `flutter-app-pipeline`
end to end.

## 2. Architecture (two layers)

- **`two-model-sdd-pipeline`** (generic engine): deterministic orchestration —
  a scripted Orchestrator dispatches stateless LLM calls (Controller, Coder,
  Strategic Coder, Code Reviewer) across git worktrees. State lives in the JSON
  plan, git history, and a script-maintained JSONL **ledger**, never in an LLM's
  memory.
- **`flutter-app-pipeline`** (Flutter layer, on top): adds package research with
  a corrected Quality Score, the deterministic Flutter scripts, and the
  **Graphify-before-LLM** ordering rule. It delegates the per-task implementation
  loop back to `two-model-sdd-pipeline`.

## 3. Environment and tools

| Tool | Role |
|---|---|
| OpenCode | Harness (CLI + agent runtime) |
| Superpowers (this fork) | Skills: brainstorming (grill-with-docs + Incremental Persistence), writing-plans, test-driven-development, two-model-sdd-pipeline, flutter-app-pipeline |
| Graphify (`graphifyy`) | On-device code knowledge graph; LLM queries structure instead of reading raw files |
| Tavily | Programmatic web search for solution research |
| pub.dev API | Package metadata, score, popularity, SDK constraints |
| GitHub REST | Commit recency, issue counts, dependents fallbacks |
| Git / Flutter / Dart | Deterministic mechanics (test, analyze, format, commit) |

## 4. Pipeline phases

1. **Phase 1 — Requirements (once, project-level).** `1a` commercial requirements
   via brainstorming + grill-with-docs; `1b` generic technical architecture.
   Resolved terms persist in `CONTEXT.md` + ADRs (architectural path only).
2. **Phase 2 — Research & Planning (per task).** `2a` search (Tavily + reference
   sources) and score candidates with `pkg-score`; `2b` select with the developer
   (as-is / modified / from-scratch); `2c` write technically complete tasks with
   `writing-plans` (no code downloaded; lockfile only). Pure planning.
3. **Phase 3 — TDD Implementation.** Delegated to `two-model-sdd-pipeline`
   (per-task loop). Flutter additions: `pub-sync` -> `red-gate` -> Coder ->
   `green-gate`; Graphify rebuild before any LLM read.
4. **Phase 4 — Project-Wide Review.** Revalidate with `green-gate --no-commit`,
   full code review, corrections re-enter Phase 3.

## 5. Roles and tiers

| Role | Tier | Responsibility |
|---|---|---|
| Orchestrator | none (deterministic) | worktrees, dispatch, tests, analysis, commits, ledger, merge; never implements/reviews itself |
| Controller | Strategic | design, plan.json, JIT task briefs with RED tests, arbitration, final review |
| Coder | Operational | bounded implementation against a RED test (max 2 rounds) |
| Strategic Coder | Strategic | escalation only; explicitly KEEP/DISCARD partial work |
| Code Reviewer | Strategic | fresh per task, read-only, one verdict: APPROVED / SEND_BACK / ESCALATE |

Always specify the model explicitly per tier on every dispatch; omitting it
silently inherits the expensive session model.

## 6. Deterministic scripts (no AI involvement)

| Script | Purpose | Verdict |
|---|---|---|
| `pkg-score PACKAGE` | Fetch pub.dev + GitHub, compute the corrected Quality Score | JSON + gate verdict (AUTO_APPROVE / DEVELOPER_DECISION / AUTO_REJECT) |
| `pub-sync [PACKAGE]` | `pub add`/`pub get` + lockfile; `pub upgrade --dry-run` conflict report | exit 0 resolved; exit 1 conflicts (`pub-sync-report.txt`) |
| `red-gate WORKSPACE TASK` | Materialize brief RED tests; verify expected failure | exit 0 RED verified; exit 1 defective brief; exit 2 usage |
| `green-gate [--no-commit] [-m MSG]` | Chain `flutter test` + `flutter analyze` + format + commit | exit 0 green (+ commit); 1 tests; 2 analyze; 3 format; `--no-commit` never commits |
| `graphify-regen [ROOT]` | Rebuild project graph | exit code of graphify |
| `graphify-package PACKAGE` | Build graph for a downloaded dependency | resolves dir from `.dart_tool/package_config.json` |

All scripts honor `FLUTTER_BIN`, `DART_BIN`, `GIT_BIN`, `GRAPHIFY_BIN` env
overrides. Tests live in `skills/flutter-app-pipeline/tests/`, run with
`run-tests.sh` (`python3 -m unittest discover`).

## 7. Ordering invariants (do not violate)

- **Graphify-before-LLM:** after any download (`pub-sync`) and after every
  task's changes, run `graphify-regen` (+ `graphify-package` for new
  dependencies) BEFORE any LLM reads the affected or downloaded files. Query the
  graph for structure/interfaces first; only then make targeted reads of the few
  files actually needed (the graph exposes structure, not method bodies).
- **Gates are exit codes:** never judge "did the test fail for the expected
  reason" or "are tests green" by reading output — run the gate script and read
  its exit code.
- **Stateless calls:** never resume a dispatched agent; re-feed its successor
  from files (brief, diff, ledger excerpt).
- **Ledger via script:** the ledger is appended through `ledger-append`, never
  free-handed as prose.
- **Workers never commit:** only the Orchestrator (or `green-gate`) commits.

## 8. Quality Score (0–100)

| Criterion | Weight | Scoring |
|---|---|---|
| Pub points | 30 | (points / 160) × 30 |
| Popularity | 15 | popularity% × 15 |
| Last commit recency | 20 | <3mo=20 / 3–6mo=12 / 6–12mo=5 / >12mo=0 |
| Flutter/Dart SDK compatibility | 15 | compatible=15 / needs override=5 / incompatible=0 |
| Dependents count | 10 | ≥50=10 / 10–49=6 / 1–9=3 / 0=0 |
| Open/closed issue ratio | 10 | <20% open=10 / 20–40%=5 / >40%=0 |

Corrections: **/160 not /140** (pub.dev max is 160); issue ratio is **PR-aware**
(`open_issues_count` includes PRs — use `search/issues?type=issue`); dependents
have no official endpoint (best-effort scrape or `pub_api_client`); no-GitHub
packages fall back to `latest.published`.

Gate: ≥70 auto-approve; 50–69 developer decision; <50 reject -> from-scratch.

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

## 11. Repository layout

```
README.txt                        <- this repo's human-facing readme
README-LLM.md                     <- this file (agent-facing)
skills/flutter-app-pipeline/SKILL.md
skills/flutter-app-pipeline/scripts/     <- deterministic scripts (bash + python3)
skills/flutter-app-pipeline/tests/       <- python unittest suite (run-tests.sh)
skills/two-model-sdd-pipeline/SKILL.md
skills/two-model-sdd-pipeline/scripts/   <- pipeline-workspace, ledger-append, review-package
```

## 12. How to work with this harness

1. New dev request -> invoke `brainstorming` before any code.
2. Flutter/Dart work -> run `flutter-app-pipeline`; on the two-tier gate default
   to YES and ask only for tier models + test/analyze commands (once per branch).
3. Per task: `pkg-score` candidates -> select with the developer -> `writing-plans`
   tasks -> `pub-sync` -> `red-gate` -> Coder rounds -> `green-gate` ->
   Graphify rebuild -> review. Repeat.
4. Non-Flutter work: standard superpowers flow (brainstorming + TDD), no Flutter
   layer.