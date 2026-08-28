---
name: flutter-app-pipeline
description: Flutter/Dart specialization layered on top of two-model-sdd-pipeline. Adds package research with the corrected pub.dev/GitHub Quality Score, deterministic Flutter scripts (pub-sync, red-gate, green-gate, graphify-regen/package), and the Graphify-before-LLM ordering rule. Use when building a Flutter/Dart app with the two-tier pipeline opted in.
---

# Flutter App Pipeline (layered on two-model-sdd-pipeline)

## 0. Relationship to two-model-sdd-pipeline

This is the Flutter/Dart specialization. It does **not** replace the generic engine; it layers on it. Read `two-model-sdd-pipeline` first — the gate (opt-in, tier models, test/analyze commands), worktree, ledger, and the Controller/Coder/Strategic Coder/Reviewer roles all come from there. This skill adds the Flutter phases and the deterministic script set below, and overrides the Phase 2/3 details.

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
2. **RED gate — `scripts/red-gate`** (deterministic, no LLM judgment). Materializes the brief's RED tests and verifies the expected failure. Exit code is the verdict; a RED test that passes means the brief is defective → back to the Controller.
3. **Coder rounds** — as in two-model (Operational tier; escalation after 2 rounds).
4. **Green gate — `scripts/green-gate`** (deterministic, no LLM judgment). Chains the full suite + `flutter analyze` + format check + commit in one script. Green → commits and ledger-appends; not green → writes a failure report, exit ≠ 0, no commit. Failing analysis is a finding for review, never a silent fix.
5. **Graphify invariant — before any LLM reads.** Enforced automatically at the script→LLM boundaries, where an LLM reads code right after a script changed files:
   - `pub-sync` chains `graphify-package` for each newly added package;
   - `red-gate` chains `graphify-regen` after verifying RED (before the Coder reads the materialized tests);
   - `green-gate` chains `graphify-regen` after committing (before the Reviewer / next task reads).
   The chains are best-effort — a graphify failure never fails a gate — and can be disabled with `GRAPHIFY_ENABLED=0`. The LLM queries the graph for structure and interfaces first; only then does it make targeted reads of the few files it actually needs (the graph exposes structure, not method bodies). This is what keeps entry token/context consumption low.
6. **Isolation rule** — parallel subagents work on separate branches; merge sequentially or lock shared files.

## 4. Phase 4 — Project-Wide Review

- Revalidate the branch with `scripts/green-gate --no-commit` (full suite + analyze; report only, never commits).
- Full codebase code review after all tasks are green.
- Any correction re-enters the Phase 3 loop (red → fix → green → review → commit).

## 5. Deterministic Scripts (no AI involvement)

| Script | Replaces |
|---|---|
| `pkg-score PACKAGE` | AI subjectively judging package quality |
| `pub-sync [PACKAGE]` | AI-driven download + AI reasoning about version conflicts + AI reconciling the lockfile |
| `red-gate WORKSPACE TASK` | AI judging whether the RED test failed for the expected reason |
| `green-gate [--no-commit] [-m MSG]` | AI running/reading `flutter test` + `flutter analyze` and AI deciding commit boundaries |
| `graphify-regen [ROOT]` | AI parsing raw file diffs for context |
| `graphify-package PACKAGE` | AI reading downloaded package source before the graph exists |

All scripts honor `FLUTTER_BIN`, `DART_BIN`, `GIT_BIN`, `GRAPHIFY_BIN` env overrides (used by tests and unusual setups). `pub-sync`, `red-gate` and `green-gate` auto-chain the graphify rebuild at the script→LLM boundaries (non-fatal; disable with `GRAPHIFY_ENABLED=0`). AI is reserved for semantic decisions only: which solution fits a task, what to build from scratch, RED-test authoring from a natural-language spec, and code review.

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