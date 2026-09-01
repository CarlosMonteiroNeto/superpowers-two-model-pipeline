---
name: flutter-app-pipeline
description: Flutter/Dart specialization layered on top of two-model-sdd-pipeline. Adds package research with the corrected pub.dev/GitHub Quality Score, deterministic Flutter scripts (pub-sync, red-gate, green-gate, graphify-regen/package), the RTK-compression invariant (every command runs through scripts/cmd), and the Graphify-before-LLM ordering rule (Controller-side, lazy). Use when building a Flutter/Dart app with the two-tier pipeline opted in.
---

# Flutter App Pipeline (layered on two-model-sdd-pipeline)

## 0. Relationship to two-model-sdd-pipeline

This is the Flutter/Dart specialization. It does **not** replace the generic engine; it layers on it. Read `two-model-sdd-pipeline` first — the gate (opt-in, tier models, test/analyze commands), worktree, ledger, the `scripts/cmd` command runner (RTK compression), and the Controller/Coder/Strategic Coder/Reviewer roles all come from there. This skill adds the Flutter phases and the deterministic script set below, and overrides the Phase 2/3 details.

## 1. Phase 1 — Requirements (once, project-level)

### 1a. Commercial requirements verification
- Brainstorming with the developer + grill-with-docs.
- Output: business/functional requirements only.

### 1b. Generic technical architecture requirements
- Architecture requirements at a generic level (patterns, constraints, non-functional needs).
- Not tied to specific packages or templates — those resolve per task in Phase 2.

Persist resolved terms/decisions per the fork's Incremental Persistence (`CONTEXT.md` glossary + ADRs, architectural path only). The spec doc stays branch-specific.

## 2. Phase 2 — Research & Planning (per task)

### 2a. Solution research
- Search for templates/packages/APIs matching the task: Tavily + reference sources (pub.dev, Flutter Gems, GitHub awesome-flutter/awesome-selfhosted/public-apis).
- Score every candidate with `scripts/pkg-score` (corrected formula, below).
- Findings presented to the developer before proceeding.

### 2b. Solution selection
- Brainstorming with the developer + grill-with-docs.
- Per component: use as-is, use with modification, or build from scratch.

### 2c. Task documentation
- Produced with `writing-plans` (the standard superpowers pattern): each task is technically complete — touched files, interfaces, acceptance criteria, dependencies, and verification.
- No code is downloaded or implemented here. Only a version-conflict check + lockfile update (`scripts/pub-sync`) for what was decided.
- Output feeds the Controller's `plan.json` for the two-model loop.

Phase 2 is pure planning and documentation. Nothing is implemented yet.

### Quality Score (0–100), per candidate package

| Criterion | Weight | Scoring |
|---|---|---|
| Pub points (pub.dev) | 30 | (points / 160) × 30 |
| Popularity (pub.dev) | 15 | popularity% × 15 |
| Last commit recency | 20 | <3mo=20 / 3–6mo=12 / 6–12mo=5 / >12mo=0 |
| Flutter/Dart SDK compatibility | 15 | compatible=15 / needs override=5 / incompatible=0 |
| Dependents count (pub.dev) | 10 | ≥50=10 / 10–49=6 / 1–9=3 / 0=0 |
| Open/closed issue ratio | 10 | <20% open=10 / 20–40%=5 / >40%=0 |

Corrections vs the original draft:
- **/160, not /140** — pub.dev `grantedPoints` max is 160; `/140` let a perfect package exceed 100 and loosened the gate.
- **Issue ratio is PR-aware** — GitHub `open_issues_count` counts issues + PRs; `pkg-score` queries `search/issues?type=issue` for clean counts.
- **Dependents via the pub.dev page** — no official endpoint; the HTML scrape is best-effort and falls back to 0 (the orchestrator may substitute `pub_api_client` when precision matters).
- **Last-commit fallback** — packages without a GitHub repo use `latest.published` from the pub.dev API instead of commit recency.

Gate logic (reported by `pkg-score` as the verdict):
- Score ≥ 70 → auto-approved (`AUTO_APPROVE`)
- Score 50–69 → included in the 2a comparison table for the developer's decision in 2b (`DEVELOPER_DECISION`)
- Score < 50 → auto-rejected, defaults to from-scratch in 2b (`AUTO_REJECT`)

## 3. Phase 3 — TDD Implementation (two-model loop)

Delegate to `two-model-sdd-pipeline`. The gate records `flutter test` as the test command and `flutter analyze` as the analysis command.

Flutter-specific additions to the per-task loop:

1. **Download & resolve — `scripts/pub-sync`** (deterministic, no LLM). Download what Phase 2 decided, update the lockfile, report version conflicts from `pub upgrade --dry-run` to a file.
2. **RED gate — `scripts/red-gate`** (deterministic, no LLM judgment). Materializes the brief's RED tests and verifies the expected failure **for the expected reason**: the brief's `EXPECTED-RED:` block holds a verbatim substring the failing output must contain. Exit code is the verdict; a RED test that passes before implementation, or that fails for the wrong reason (e.g. a compile error in test setup instead of the missing symbol), means the brief is defective → back to the Controller.
3. **Coder rounds** — as in two-model (Operational tier; escalation after 2 rounds).
4. **Green gate — `scripts/green-gate`** (deterministic, no LLM judgment). Chains the full suite + `flutter analyze` + format check + commit in one script. Green → commits and ledger-appends; not green → writes a failure report, exit ≠ 0, no commit. Failing analysis is a finding for review, never a silent fix.
5. **RTK compression invariant — every command line runs through `scripts/cmd`.** The two-model engine's generic runner (`skills/two-model-sdd-pipeline/scripts/cmd`) wraps every LLM-invoked command (`flutter test`, `flutter analyze`, git ops, graphify queries): it saves the FULL output to a workspace file and prints the RTK-compressed view on stdout. Gates keep reading full files — nothing a verdict depends on is ever compressed. `RTK_ENABLED=0` disables compression; `RTK_BIN` overrides the binary.
6. **Graphify invariant — Controller-side and lazy.** The Controller queries the graph (`graphify explain` / `graphify path`) when writing task briefs and rebuilds it only when stale (best-effort, `GRAPHIFY_ENABLED=0` to disable). Graphify is **no longer chained into `red-gate`/`green-gate`** — those gates never read the graph; RTK covers the context-compression job the eager chains used to aim at. `pub-sync` still indexes newly added packages (a Controller feed). The graph exposes structure, not method bodies — that is what keeps the Controller's brief-writing context low.
7. **Isolation rule** — parallel subagents work on separate branches; merge sequentially or lock shared files.

## 4. Phase 4 — Project-Wide Review

- Revalidate the branch with `scripts/green-gate --no-commit` (full suite + analyze; report only, never commits).
- Full codebase code review after all tasks are green.
- Any correction re-enters the Phase 3 loop (red → fix → green → review → commit).
- **Repository documentation:** if this session changed the pipeline itself (scripts, skills, invariants, phases), update `README.txt` and `README-LLM.md` to reflect the changes and include them in the push. Run `scripts/doc-check` as a deterministic gate to verify before the merge — exit 1 means READMEs were not updated with pipeline changes; the Orchestrator must amend them.

## 5. Deterministic Scripts (no AI involvement)

| Script | Replaces |
|---|---|
| `pkg-score PACKAGE` | AI subjectively judging package quality |
| `pub-sync [PACKAGE]` | AI-driven download + AI reasoning about version conflicts + AI reconciling the lockfile |
| `red-gate WORKSPACE TASK` | AI judging whether the RED test failed for the expected reason (verifies the brief's `EXPECTED-RED:` text against the report) |
| `green-gate [--no-commit] [-m MSG]` | AI running/reading `flutter test` + `flutter analyze` and AI deciding commit boundaries |
| `cmd --full-file FILE -- CMD` (two-model) | AI seeing raw command output in context (saves FULL output to FILE, prints the RTK-compressed view on stdout, returns the command's true exit code) |
| `run-gates WS TEST ANALYZE` (two-model) | AI running/reading the gate-recorded test + analyze commands in the generic engine |
| `graphify-regen [ROOT]` | AI parsing raw file diffs for context (invokes `graphify update <root>`); now Controller-side lazy only |
| `graphify-package PACKAGE` | AI reading downloaded package source before the graph exists (invokes `graphify update <pkg_dir>`); feeds the Controller |
| `route-next WORKSPACE TASK [TOTAL]` (two-model) | AI deciding "review passed → next task / failed → fix round" — the router emits the next action deterministically |

All scripts honor `FLUTTER_BIN`, `DART_BIN`, `GIT_BIN`, `GRAPHIFY_BIN`, `RTK_BIN`
env overrides (used by tests and unusual setups). `cmd` respects `RTK_ENABLED=0`
(passthrough) and `RTK_BIN` (override). `pub-sync` keeps the graphify-package
chain (Controller feed, non-fatal; disable with `GRAPHIFY_ENABLED=0`); `red-gate`
and `green-gate` no longer chain graphify — they never read the graph. AI is
reserved for semantic decisions only: which solution fits a task, what to build
from scratch, RED-test authoring from a natural-language spec, and code review.

## 6. Data Sources for Score Computation (all scriptable, no LLM)

| Data | Source | Method |
|---|---|---|
| Pub points, popularity | pub.dev API | `GET /api/packages/{name}/score` |
| Last commit date | GitHub REST | `GET /repos/{owner}/{repo}/commits?per_page=1` (fallback: `latest.published`) |
| SDK compatibility | pub.dev API | `GET /api/packages/{name}` → `pubspec.environment.sdk` |
| Dependents count | pub.dev | HTML page scrape (best-effort) |
| Open/closed issue ratio | GitHub REST | `GET /search/issues?q=repo:{o}/{r}+type:issue+state:{open\|closed}` (`total_count`) |

## 7. GitHub Authentication (one-time setup)

GitHub REST rate limit is 60 req/h unauthenticated, 5000 req/h authenticated. Batch package research requires authentication.

1. GitHub → Settings → Developer settings → Personal access tokens → generate (fine-grained, minimal scope — public read only).
2. Store as an environment variable / CI secret — never hardcoded or committed.
3. `pkg-score` reads it as `GITHUB_TOKEN` (sent as `Authorization: Bearer`).
4. No further interaction needed — reused until revoked.

## 8. Summary of Flow

```
1a Commercial Requirements → 1b Generic Architecture
  → [per task] 2a Research + pkg-score → 2b Selection (developer) → 2c writing-plans tasks (lockfile only)
  → 3 two-model loop (pub-sync → red-gate → Coder → green-gate; Graphify before any LLM read)
  → 4 green-gate --no-commit + full review → done
```
