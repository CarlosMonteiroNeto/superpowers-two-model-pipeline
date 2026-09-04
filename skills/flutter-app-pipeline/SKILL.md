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

## 2. Phase 2 — Research & Planning (project-level + per task)

### 2a. Solution research

**Package search** — same task-level cycle as before:
- Search for packages/APIs matching the task: Tavily + reference sources (pub.dev, Flutter Gems, GitHub awesome-flutter/awesome-selfhosted/public-apis).
- Score every candidate with `scripts/pkg-score` (corrected formula, below).
- Findings presented to the developer before proceeding.

**Project-level template search** (runs once per project, Phase 2a, before package research):
- Search the **specific** category first (stars descending via GitHub search API), using `scripts/template-search` + `scripts/template-score`.
- Collect up to **3** `AUTO_APPROVE` (≥70) candidates then **STOP** — nothing is downloaded without an explicit developer pick.
- If the specific category yields no `AUTO_APPROVE` candidates, collect its 50–69 group **and** the generic category's ≥70 candidates, presenting both groups in one comparison table for the developer's decision.
- Template search order: specific category → generic fallback; stars descending within each tier.

### 2b. Solution selection
- Brainstorming with the developer + grill-with-docs.
- Per component: use as-is, use with modification, or build from scratch.

### 2c. Task documentation
- Produced with `writing-plans` (the standard superpowers pattern): each task is technically complete — touched files, interfaces, acceptance criteria, dependencies, and verification.
- No code is downloaded or implemented here. Only a version-conflict check + lockfile update (`scripts/pub-sync`) for what was decided.
- If the developer adopted a template in 2b: **clone** the template and run `graphify` to produce a **template gap analysis** (what the template provides / what to strip / what is missing → dependency search or from-scratch). This gap analysis seeds the plan tasks. The "no code downloaded" invariant is relaxed **only** for the adopted template (clone + graphify); package downloads stay lockfile-only in 2c.
- Output feeds the Controller's `plan.json` for the two-model loop.

Phase 2 is pure planning and documentation. Nothing is implemented yet.

### Quality Score (0–100), per candidate package (pkg-score)

| Criterion | Weight | Scoring |
|---|---|---|
| Pub points (pub.dev) | 20 | (points / 160) × 20 |
| Popularity (pub.dev) | 10 | popularity% × 10 |
| Last commit recency | 20 | <3mo=20 / 3–6mo=12 / 6–12mo=5 / >12mo=0 |
| Flutter/Dart SDK compatibility | 20 | compatible=20 / needs override=7 / incompatible=0 |
| Dependents count (pub.dev) | 15 | ≥50=15 / 10–49=9 / 1–9=4 / 0=0 |
| Open/closed issue ratio | 15 | <20% open=15 / 20–40%=7 / >40%=0 |

Health signals (recency + SDK compatibility + issue ratio) sum to **55** of 100.

Corrections vs the original draft:
- **/160, not /140** — pub.dev `grantedPoints` max is 160; `/140` let a perfect package exceed 100 and loosened the gate.
- **Issue ratio is PR-aware** — GitHub `open_issues_count` counts issues + PRs; `pkg-score` queries `search/issues?type=issue` for clean counts.
- **Dependents via the pub.dev page** — no official endpoint; the HTML scrape is best-effort and falls back to 0 (the orchestrator may substitute `pub_api_client` when precision matters).
- **Last-commit fallback** — packages without a GitHub repo use `latest.published` from the pub.dev API instead of commit recency.

### Template Score (0–100), per candidate template (template-score)

| Criterion | Weight | Scoring |
|---|---|---|
| Stars (primary sort key) | 30 | ≥1000=30 / 300–999=24 / 100–299=18 / 30–99=12 / 10–29=6 / <10=0 |
| Last commit recency | 20 | <3mo=20 / 3–6mo=12 / 6–12mo=5 / >12mo=0 |
| Flutter/Dart readiness | 20 | current SDK + null-safe pubspec=20 / dated SDK=10 / not Flutter=0 |
| Open/closed issue ratio | 10 | <20% open=10 / 20–40%=5 / >40%=0 |
| Sustained interest (stars ÷ repo age) | 10 | ≥10/yr=10 / 1–10/yr=6 / <1/yr=2 |
| License | 5 | MIT/Apache/BSD=5 / other=3 / none=0 |
| README quality (setup + structure docs) | 5 | full setup docs=5 / partial=2 / none=0 |

Gate logic (reported by `pkg-score` / `template-score` as the verdict):
- Score ≥ 70 → auto-approved (`AUTO_APPROVE`)
- Score 50–69 → included in the 2a comparison table for the developer's decision in 2b (`DEVELOPER_DECISION`)
- Score < 50 → auto-rejected, defaults to from-scratch in 2b (`AUTO_REJECT`)

## 3. Phase 3 — TDD Implementation (two-model loop)

Delegate to `two-model-sdd-pipeline`. The gate records `flutter test` as the test command and `flutter analyze` as the analysis command.

Flutter-specific additions to the per-task loop (script-autonomous — the
interactive session B writes the brief and receives feedback only through
script outputs; Script A owns dispatch):

1. **Download & resolve — `scripts/pub-sync`** (deterministic, no LLM). Download what Phase 2 decided, update the lockfile, report version conflicts from `pub upgrade --dry-run` to a file.
2. **RED gate — `scripts/red-gate`** (deterministic, no LLM judgment). Materializes the brief's RED tests and verifies the expected failure **for the expected reason**: the brief's `EXPECTED-RED:` block holds a verbatim substring the failing output must contain. Exit code is the verdict; a RED test that passes before implementation, or that fails for the wrong reason (e.g. a compile error in test setup instead of the missing symbol), means the brief is defective → back to B for arbitration. **On success, red-gate dispatches the Coder headlessly** (Item 4 — `scripts/dispatch --agent two-model-coder`).
3. **Coder rounds** — Operational tier (`two-model-coder`, write-only). C never runs tests/analysis (ADR-0002): Script A decides task tests → full suite → `flutter analyze` by exit code and feeds failures back. Round 1 + 3 fixes (4 attempts); resume via `--continue --session`; overflow → `ARBITRATE` to B.
4. **Green gate — `scripts/green-gate`** (deterministic, no LLM judgment). Chains the full suite + `flutter analyze` + format check + commit in one script. Green → commits, ledger-appends, runs the **post-commit `graphify-update`**, builds the review package, and **dispatches the Reviewer headlessly** (Item 3 — `scripts/dispatch --agent two-model-reviewer`). Not green → writes a failure report, exit ≠ 0, no commit. Failing analysis is a finding for review, never a silent fix. `--no-commit` validates only (no graphify, no dispatch).
5. **Reviewer (D)** — `two-model-reviewer`, Strategic, reviews compiler-approved code only (Item 2 — never runs test/analyze). Returns a structured JSON verdict (APPROVED / SEND_BACK / ESCALATE + findings + minors). Context kept within the task's correction loops (ADR-0003); minors documented by B only.
6. **RTK compression invariant — every command line runs through `scripts/cmd`.** The two-model engine's generic runner (`skills/two-model-sdd-pipeline/scripts/cmd`) wraps every LLM-invoked command (`flutter test`, `flutter analyze`, git ops, graphify queries): it saves the FULL output to a workspace file and prints the RTK-compressed view on stdout. `flutter test` → `rtk test` and `flutter analyze` → `rtk err` wrapper derivation (verdict always from the raw run — RTK wrappers mask child exit codes). Gates keep reading full files — nothing a verdict depends on is ever compressed. `RTK_ENABLED=0` disables compression; `RTK_BIN` overrides the binary.
7. **Graphify invariant — post-commit only, subgraph extraction (ADR-0004).** `graphify-update` rebuilds the graph ONLY after an approved task's commit (green-gate chain) — never per Coder iteration. `graphify-subgraph WS TASK` extracts the affected-dependency slice (`explain`/`path` on the task's `touches`) into `<ws>/task-N-interfaces.md` for B's next brief and D's review — never whole source. `pub-sync` still indexes newly added packages (a B feed). The graph exposes structure, not method bodies.
8. **Isolation rule** — parallel subagents work on separate branches; merge sequentially or lock shared files.

## 4. Phase 4 — Project-Wide Review

- Revalidate the branch with `scripts/green-gate --no-commit` (full suite + analyze; report only, never commits).
- Full codebase code review after all tasks are green.
- Any correction re-enters the Phase 3 loop (red → fix → green → review → commit).
- **Repository documentation:** if this session changed the pipeline itself (scripts, skills, invariants, phases), update `README.txt` and `README-LLM.md` to reflect the changes and include them in the push. Run `scripts/doc-check` as a deterministic gate to verify before the merge — exit 1 means READMEs were not updated with pipeline changes; the Orchestrator must amend them.

## 5. Deterministic Scripts (no AI involvement)

| Script | Replaces |
|---|---|
| `pkg-score PACKAGE` | AI subjectively judging package quality |
| `template-search --specific QUERY --generic QUERY` | AI manually searching GitHub for project-level templates (searches specific then generic category, stars descending, collects up to 3 AUTO_APPROVE before stopping) |
| `template-score OWNER/REPO [--github-token TOKEN]` | AI subjectively judging template quality (stars, recency, Flutter/Dart readiness, issue ratio, sustained interest, license, README) |
| `pub-sync [PACKAGE]` | AI-driven download + AI reasoning about version conflicts + AI reconciling the lockfile |
| `red-gate WORKSPACE TASK` | AI judging whether the RED test failed for the expected reason (verifies the brief's `EXPECTED-RED:` text against the report; on success dispatches the Coder) |
| `green-gate [--no-commit] [-m MSG] [-w WS -t TASK -b BASE]` | AI running/reading `flutter test` + `flutter analyze` and AI deciding commit boundaries (on commit: graphify-update + reviewer dispatch) |
| `graphify-update [ROOT]` | AI deciding when the graph is stale (post-commit only, ADR-0004) |
| `graphify-subgraph WS TASK` | AI gathering interface signatures for B/D from raw files (extracts the affected-dependency subgraph into `<ws>/task-N-interfaces.md`) |
| `cmd --full-file FILE -- CMD` (two-model) | AI seeing raw command output in context (saves FULL output to FILE, prints the RTK-compressed view on stdout, returns the command's true exit code; flutter test/analyze via rtk test/err wrappers) |
| `dispatch --agent NAME --task N [--continue SESSION] ...` (two-model) | AI launching subagents from the session (headless `opencode run`; JSON stream teed to a workspace log; session id recorded for resume) |
| `orchestrator WS TASK [TOTAL]` (two-model) | AI deciding the per-task transition (executes route-next actions, hands `OUTCOME:` back to B) |
| `token-kill err\|src\|json FILE` (two-model) | AI reading raw logs/source/reports into context (RTK minification, lossless) |
| `run-gates WS TEST ANALYZE` (two-model) | AI running/reading the gate-recorded test + analyze commands in the generic engine |
| `graphify-regen [ROOT]` | AI parsing raw file diffs for context (invokes `graphify update <root>`); now post-commit Script-A-side only |
| `graphify-package PACKAGE` | AI reading downloaded package source before the graph exists (invokes `graphify update <pkg_dir>`); feeds B |
| `route-next WORKSPACE TASK [TOTAL]` (two-model) | AI deciding "review passed → next task / failed → corrective / escalate → arbitrate" — the router emits the next action deterministically |

All scripts honor `FLUTTER_BIN`, `DART_BIN`, `GIT_BIN`, `GRAPHIFY_BIN`, `RTK_BIN`,
`DISPATCH_BIN`, `OPENCODE_BIN` env overrides (used by tests and unusual setups).
`cmd` respects `RTK_ENABLED=0` (passthrough) and `RTK_BIN` (override). `pub-sync`
keeps the graphify-package chain (B feed, non-fatal; disable with
`GRAPHIFY_ENABLED=0`); `graphify-update` runs post-commit only; `red-gate` and
`green-gate` dispatch C/D on success but never read the graph. AI is reserved
for semantic decisions only: which solution fits a task, what to build from
scratch, RED-test authoring from a natural-language spec, and code review.

## 6. Data Sources for Score Computation (all scriptable, no LLM)

| Data | Source | Method |
|---|---|---|
| Pub points, popularity | pub.dev API | `GET /api/packages/{name}/score` |
| Last commit date | GitHub REST | `GET /repos/{owner}/{repo}/commits?per_page=1` (fallback: `latest.published`) |
| SDK compatibility | pub.dev API | `GET /api/packages/{name}` → `pubspec.environment.sdk` |
| Dependents count | pub.dev | HTML page scrape (best-effort) |
| Open/closed issue ratio | GitHub REST | `GET /search/issues?q=repo:{o}/{r}+type:issue+state:{open\|closed}` (`total_count`) |
| Template stars | GitHub REST | `GET /search/repositories?q=...&sort=stars&order=desc` |
| Template repo metadata | GitHub REST | `GET /repos/{owner}/{repo}` (stars, created_at, license, open_issues_count) |
| Template issue ratio | GitHub REST | `GET /search/issues?q=repo:{o}/{r}+type:issue` (open vs total) |
| Template README | GitHub REST | `GET /repos/{owner}/{repo}/contents/README.md` (base64 decode, check for setup/structure docs) |

## 7. GitHub Authentication (one-time setup)

GitHub REST rate limit is 60 req/h unauthenticated, 5000 req/h authenticated. Batch package research requires authentication.

1. GitHub → Settings → Developer settings → Personal access tokens → generate (fine-grained, minimal scope — public read only).
2. Store as an environment variable / CI secret — never hardcoded or committed.
3. `pkg-score` reads it as `GITHUB_TOKEN` (sent as `Authorization: Bearer`).
4. No further interaction needed — reused until revoked.

## 8. Summary of Flow

```
1a Commercial Requirements → 1b Generic Architecture
  → [project-level] 2a template-search + template-score (specific category first, stars descending, 3-AUTO_APPROVE stop)
  → [per task] 2a package research + pkg-score → 2b Selection (developer) → 2c writing-plans tasks (lockfile only; template: clone + gap analysis seeds plan tasks)
  → 3 two-model loop, script-autonomous (pub-sync → red-gate → dispatch C → gates → green-gate → dispatch D → route-next)
  → 4 green-gate --no-commit + full review → done
```
