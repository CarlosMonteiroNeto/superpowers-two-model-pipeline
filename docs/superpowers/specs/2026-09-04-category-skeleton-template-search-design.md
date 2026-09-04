# Category Skeleton + Tiered Template Search Design

Date: 2026-09-04
Status: Approved (brainstorming), pending spec review
Branch context: two-model-sdd-pipeline fork (flutter-app-pipeline layer)

## 1. Problem

Phase 2a today searches for "templates/packages/APIs matching the task" generically.
Templates are presented raw — never scored — so the developer has no deterministic
signal to choose one, and the search is not ordered by anything that predicts
reuse value. There is also no structured elicitation of what the app actually is
(category) before research begins, so every search starts broad.

This design adds:

1. A **Category Skeleton** elicited in Phase 1a brainstorming: generic category →
   specific category → original implementations.
2. A **project-level template stage** with a deterministic GitHub-based score and a
   search order keyed to the heaviest-weight criterion (stars, descending).
3. A **re-weighted package score** that favors health signals over popularity.
4. A template **adoption flow**: present → clone + graphify → gap analysis.

## 2. Goals

- Reuse proven community templates before building from scratch, prioritizing
  the most specific match that clears a quality gate.
- Make template selection deterministic and comparable (same gate semantics as
  `pkg-score`), while keeping the final download decision human.
- Stop searching once enough auto-approvable candidates are found (3), instead of
  searching broadly.
- Route original implementations to dependency research (pub.dev), and only fall
  back to from-scratch when no adequate dependency exists.
- Favor healthy packages (recency, SDK compatibility, issue ratio) over popular
  but possibly abandoned ones.

## 3. Category Skeleton (Phase 1a, brainstorming skill)

`brainstorming` Phase 1a gains a REQUIRED elicitation step, in this exact order,
persisted to `CONTEXT.md`:

1. **Generic category** — the broad app family (e.g., POS).
2. **Specific category** — the niche (e.g., women's fashion POS).
3. **Original implementations** — the features that make it yours
   (e.g., voice command, auto-calc installments).

These three fields drive the downstream research:

- Template search query derives from generic + specific category.
- Each original implementation becomes a per-task dependency research target
  (pub.dev) in Phase 2a.

The three fields are REQUIRED outputs of Phase 1a; the spec cannot be written
without them.

## 4. Template search (new project-level Phase 2a step)

Two new deterministic scripts: `template-search` (orchestration) and
`template-score` (per-candidate scoring), both under
`skills/flutter-app-pipeline/scripts/`.

### 4.1 Search order (specific category)

Primary search targets the **specific category**, ordered by the heaviest-weight
criterion of `template-score` descending — i.e., **stars descending** via the
GitHub search API. The heaviest-weight criterion is always the primary sort key
of the search.

### 4.2 Stop rule (3 auto-approvable)

If the specific category yields at least one `AUTO_APPROVE` (score ≥ 70)
candidate, keep collecting until **3** `AUTO_APPROVE` candidates are found or
the search is exhausted, then **STOP** searching. If fewer than 3 are found,
present what was found.

### 4.3 Fallback (specific 50–69 vs generic ≥ 70)

If the specific category yields **no** `AUTO_APPROVE` candidate:

- Collect the specific-category candidates in the **50–69** range
  (`DEVELOPER_DECISION`).
- Search the **generic category** and collect its **≥ 70** `AUTO_APPROVE`
  candidates (also stars descending).
- Present **both groups** in one comparison table so the developer decides:
  a lower-quality *specific* template vs. a high-quality *generic* one. If only
  one group has candidates, present that group alone.

### 4.4 No template

If neither category yields anything ≥ 50, no template is adopted; the base is
built from scratch.

### 4.5 Presentation

All candidates that reach the presentation stage are shown in a comparison table
with the full `template-score` breakdown. The developer picks which template to
download. No download happens without that explicit pick.

## 5. template-score (GitHub-based, new)

Scoring criteria (0–100). The heaviest-weight criterion — **Stars** — is the
primary search sort key.

| Criterion | Weight | Scoring |
|---|---|---|
| Stars (primary sort key) | 30 | ≥1000=30 / 300–999=24 / 100–299=18 / 30–99=12 / 10–29=6 / <10=0 |
| Last commit recency | 20 | <3mo=20 / 3–6mo=12 / 6–12mo=5 / >12mo=0 |
| Flutter/Dart readiness | 20 | current SDK + null-safe pubspec=20 / dated SDK=10 / not Flutter=0 |
| Open/closed issue ratio | 10 | <20% open=10 / 20–40%=5 / >40%=0 |
| Sustained interest (stars ÷ repo age) | 10 | ≥10/yr=10 / 1–10/yr=6 / <1/yr=2 |
| License | 5 | MIT/Apache/BSD=5 / other=3 / none=0 |
| README quality (setup + structure docs) | 5 | full setup docs=5 / partial=2 / none=0 |

Gate (same semantics as `pkg-score`):

- Score ≥ 70 → `AUTO_APPROVE`
- Score 50–69 → `DEVELOPER_DECISION`
- Score < 50 → `AUTO_REJECT`

GitHub REST data sources mirror `pkg-score`: `search/repositories` for candidate
listing, `/repos/{owner}/{repo}` for metadata (stars, license, dates),
`search/issues?type=issue` for the issue ratio. README content is fetched from
the GitHub API and keyword-scored for setup/structure documentation. Reads
`GITHUB_TOKEN` from the environment like `pkg-score`.

## 6. pkg-score re-weight (health over popularity)

| Criterion | Old | New |
|---|---|---|
| Recency | 20 | 20 |
| SDK compatibility | 15 | 20 |
| Issue ratio | 10 | 15 |
| Pub points | 30 | 20 |
| Dependents | 10 | 15 |
| Popularity | 15 | 10 |

Health signals (recency + SDK + issue ratio) now sum to 55 of 100. Gate
thresholds unchanged (≥70 / 50–69 / <50).

## 7. Template adoption and downstream flow

- **Phase 2c change**: after the developer picks a template, clone/download it and
  run `graphify` on it → a **template gap analysis**: what the template already
  provides that we need / what we don't want (strip) / what is missing
  (→ dependency search or from-scratch). This gap analysis seeds the plan tasks.
- **Per task**: original implementations → pub.dev `pkg-score` search; no adequate
  candidate → from-scratch task. Templates are never re-searched per task
  (project-level decision only).
- **Phase 2c "no code downloaded" invariant**: relaxed ONLY for the adopted
  template (the clone + graphify step). Package downloads remain as-is
  (lockfile only in Phase 2c; real download via `pub-sync` in Phase 3).

## 8. Implementation scope

Files to change/add:

- `skills/brainstorming/SKILL.md` — Category Skeleton elicitation (Section 3).
- `skills/flutter-app-pipeline/SKILL.md` — project-level template stage, revised
  Phase 2a/2c, new score tables (Sections 4–7).
- `skills/flutter-app-pipeline/scripts/template-search` — new orchestrator
  (bash, uses `cmd` for RTK-compressed output).
- `skills/flutter-app-pipeline/scripts/template-score` + `template_score.py` —
  new scorer (python3, mirrors `pkg_score.py` structure).
- `skills/flutter-app-pipeline/scripts/pkg_score.py` — re-weighted criteria.
- Tests: `skills/flutter-app-pipeline/tests/` for `template_score.py`
  (`compute_score` pure function, fallback orchestration logic) and updated
  `pkg-score` tests.
- `README-LLM.md`, `README.txt` — reflect the new phase (doc-check gate).
- `CONTEXT.md` — document the Category Skeleton fields.

Script conventions follow the existing pipeline: every LLM-invoked command runs
through `scripts/cmd` (RTK compression); gate verdicts are exit codes; env
overrides (`GITHUB_TOKEN`, `RTK_BIN`, `GIT_BIN`, API base overrides for tests)
are honored.

## 9. Testing

- `template_score.compute_score` unit tests (pure function): criterion buckets,
  gate thresholds, verdict transitions.
- `template-search` orchestration tests (mocked API base env): specific-first
  ordering, 3-candidate stop rule, specific-no-auto → generic fallback with both
  groups presented, all-<50 → from-scratch.
- Updated `pkg_score` tests for the re-weighted formula.
- `run-tests.sh` remains the single test entry point.

## 10. Doc check

Pipeline behavior changes in this design require updating `README-LLM.md` and
`README.txt` in the same push; `scripts/doc-check` is the deterministic gate.