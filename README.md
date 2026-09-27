# Superpowers — canonical harness reference

This README.md is the single canonical operational and architectural reference
for this repository: installation, backends, the deterministic two-tier
pipeline, its scripts, its rules, and its glossary. Root CONTEXT.md and
README-LLM.md are retired; useful content was migrated here. Historical
detail remains in linked ADRs and specs.

## 1. What this is

A fork of [`obra/superpowers`](https://github.com/obra/superpowers) (MIT)
turned into an AI-assisted, **two-tier** development pipeline with a
Flutter/Dart layer on top. The design rule: **LLMs reason and scripts
decide** — mechanical steps are chained into deterministic scripts whose
verdict is an exit code, and LLM calls are **cache-aware** (within-task
OpenCode within-task resume via `--continue --session`, while Codex resume
uses explicit identity-checked session IDs; fresh context when the task changes).

Each of the 14 original skills was kept intact and given a **"Pipeline
Integration"** section inserted right after its title, applying this
harness's principles (the `two-model-sdd-pipeline` / `flutter-app-pipeline`
engine):

- **LLMs reason, scripts decide** — every checkable judgment call a skill
  used to leave to the LLM is pointed at the deterministic script/exit-code
  that now owns it (`route-next`, `red-gate`, `green-gate`, `final-gate`,
  `doc-check`, `run-gates`).
- **Fixed five-role engine** — Script CEO (deterministic loop owner,
  invokable as `run-pipeline`), Agente estratégico (plan authoring + spec, then
  DONE), Agente diretor (`two-model-task-generator`: task expansion,
  correctives, closing), Agente operador (`two-model-coder`, owns the
  RED/GREEN loop, Operational), Agente revisor (`two-model-reviewer`,
  Strategic). `subagent-driven-development`'s SKILL.md carries the full
  role-mapping table.
- **Structured verdicts, not prose** — review-related skills
  (`requesting-code-review`, `receiving-code-review`) now route on the
  fixed JSON shape (APPROVED / SEND_BACK / ESCALATE) instead of free-text
  comments.
- **State is external** — plan.json + git + JSONL ledger, never
  conversational memory; this is what makes every loop resumable after
  compaction.
- **Cache-aware, logged dispatch** — OpenCode task workers use the legacy
  `scripts/dispatch` route; Codex task workers use the explicit Codex adapter
  and identity-bound session contract. Model-directed Codex subagents are a
  separate host feature, not a substitute for the pipeline's worker protocol.
- **RTK compression** — large outputs (logs, diffs, JSON reports) get
  minified via `cmd` before hitting context; dependency context comes from
  diffs and gate reports, not manual grepping.
- **English-only artifacts** — specs, briefs, ADRs, ledger summaries, commit
  messages, skill files: English regardless of the developer's language. The
  only exception anywhere in the pipeline is user-facing UI copy.

**Execution honesty.** OpenCode and Codex use explicit plan-driven entry
points. Codex runs through `scripts/run-codex-pipeline PLAN --config FILE`
(PowerShell: `run-codex-pipeline.ps1`), with pinned role models, reasoning,
publication and concurrency. Before dispatch, review and trust the packaged
hooks and confirm managed policy and inherited instructions are clear.
Backend selection has no silent fallback. Package extraction and fake-runtime
fixtures verify paths and contracts; they do not prove live model,
authentication, hook trust or permission behavior. See the packaged
[worker runtime compatibility guide](skills/two-model-sdd-pipeline/references/worker-runtime.md).

## 2. Installation

The plugin loads from a vendored git checkout of this repository
(`~/.config/opencode/vendor/superpowers`), decoupled from npm.

```
scripts/install-superpowers          # clones the fork into the vendor dir
```

`install-superpowers` refuses to clobber a non-empty, non-repo path
(an unrelated installed plugin cache is never patched). After cloning it
verifies with the pipeline test suite, then stages the checkout as a
validated immutable bundle (`.harness/bundles/<id>/`: runtime files,
prompts, skills, canonical docs, license) and atomically selects it
(`.harness/selected`), writing backend-specific entry points under the
installed vendor checkout (`${SUPERPOWERS_DIR:-$HOME/.config/opencode/vendor/superpowers}/.harness/entrypoints/`).
They resolve the current project's pin through relocatable identities and
auto-enroll only that project on first use. Failed bundle validation preserves
the prior selection: on a fresh install no selection file is left behind.

Keep the checkout current with the safe-update scripts (they auto-detect
the checkout dir, or take it as the first argument):

```
scripts/check-superpowers    # exit 0 = up to date; 1 = behind; 2 = not installed
scripts/sync-superpowers     # inspect, validate the candidate, fast-forward a clean strictly-behind checkout
```

At session start the agent runs `scripts/check-superpowers`; if behind it
runs `scripts/sync-superpowers`, if not installed it runs
`scripts/install-superpowers`, and in either case asks the developer to
restart OpenCode (skills load at session start). The bundle store lives
under the git-ignored `.harness/` directory, so safe updates keep working
and project pins are never rewritten by installation or synchronization.

To use the OpenCode pipeline from a project, launch a plan through its entry
point. The agent prompt `agent/flutter-pipeline.md` describes the workflow:

```
"${SUPERPOWERS_DIR:-$HOME/.config/opencode/vendor/superpowers}/.harness/entrypoints/opencode.sh" --project "$PWD" docs/superpowers/plans/example-plan.json
```

The entry point is inside the installed vendor checkout, not the project. The
installer prints its path; set `SUPERPOWERS_DIR` when using a custom install
directory.

Tier models (mirrored under `agent/`, both `mode: all` so they can be
dispatched headlessly): Strategic (Agente diretor / Agente revisor) and
Operational (Agente operador).

On Git Bash for Windows, `pipeline-workspace` and `cmd` normalize native
Windows paths through their shared `lib/path-normalize.sh` helper before
passing them to POSIX filesystem tools. This keeps workspaces and full
command logs inside the selected checkout, including paths with spaces,
instead of asking MSYS `mkdir` to create a literal `C:` directory.

## 3. Harness bundles and project binding

Installations are versioned immutable bundles; projects pin one.

```
"${SUPERPOWERS_DIR:-$HOME/.config/opencode/vendor/superpowers}/.harness/entrypoints/opencode.sh" --project "$PWD" docs/superpowers/plans/example-plan.json
```

The entry point enrolls only the project in use on first use. It writes a
versioned `.superpowers/harness.json` pin (bundle id, bundle hash, backend,
relocatable backend configuration and policy references) and merges a marked
`AGENTS.md` section idempotently while preserving user instructions. It then
starts OpenCode from that project's pinned bundle. The Codex worker adapter
is packaged, but the full plan-driven Codex entry point remains R3 work.

For an existing project, `harness-project prepare --project DIR --backend opencode`
resolves its pin and reports changed paths when a newer bundle is selected.
The pin changes only on user acceptance: choose `--accept-upgrade` or `--keep-pinned`. Active runs retain their original version.
The OpenCode entry point offers that choice before a new run. It detects
an existing plan ledger and keeps its original bundle when resuming. A missing
pin in an existing harness project, an uninstalled bundle, or a hash mismatch
is diagnosed without falling back to the newest installation. Only the given
project is touched; unrelated projects are never scanned or altered.

## 4. Safe updates at startup

Startup may apply the validated safe update automatically. The sync
command inspects the checkout, shows the diff summary, validates the
candidate version in isolation, and fast-forwards a clean strictly-behind
installation; `--check-only` permits inspection without application, and
no confirmation is needed for this safe update. Ahead, diverged, dirty,
unexpected detached HEAD, or remote mismatch preserves commits, index,
untracked files, and working-tree bytes, and asks the user to resolve
them — never reset, clean, stash, rebase, or auto-merge. Failed
validation preserves the current checkout and selection, and never
reports a rollback that did not occur. Existing project version pins are
preserved.

## 5. Backends and launch choices

The backend is one of `codex` or `opencode`, chosen per run. Each run
confirms its backend, operator and reviewer models (the director uses the
reviewer model unless overridden), publication (`local` or `pull_request`)
and concurrency limit at launch; resume retains those choices. There are
no product model defaults and no silent fallbacks. Coder invocation
allowances are [5, 3, 3] per task episode (configurable) and completed-run
retention is 30 days (configurable).

## 6. Architecture (script-autonomous, two layers)

- **`two-model-sdd-pipeline`** (generic engine): a deterministic **Script
  CEO**, launched through the installed vendor checkout's
  `.harness/entrypoints/opencode.sh PLAN_FILE`, owns the
  per-task loop — gates, test/analyze decisions, subagent dispatch,
  routing, and commits. The interactive session (**Agente estratégico**)
  writes the spec and a complete `plan.json` (acceptance; no
  `expected_red`), then DONE. **Agente diretor**
  (`two-model-task-generator`) is a punctual task owner: it rules
  corrective/arbitrate episodes with script-controlled context and closes
  the branch once with a curated package (No EXPAND). **Agente operador**
  (`two-model-coder`) owns its RED/GREEN loop — it authors RED tests, runs
  them saving the machine-readable output, declares the expected reason,
  then implements and runs them green. **Agente revisor**
  (`two-model-reviewer`) reviews compiler-approved code (plus
  test-vs-acceptance fit) and returns a structured JSON verdict; it is the
  sole independent semantic guarantee. State lives in the JSON plan, git
  history, and a script-maintained JSONL **ledger**, never in an LLM's
  memory.
- **`flutter-app-pipeline`** (Flutter layer, on top): adds package research
  with a corrected Quality Score, the deterministic Flutter scripts, and
  the **RTK-compression** ordering rule. It delegates the per-task
  implementation loop back to `two-model-sdd-pipeline`. Interface design
  is governed by the vendored **`apple-design`** skill
  (`skills/apple-design/SKILL.md`, MIT): Phase 1b/2 UI decisions and the
  operador's UI code must apply its principles (response, direct
  manipulation, interruptibility, springs, momentum, materials,
  typography, reduced motion), and the revisor checks them.

**Corollary — script-decided routing.** If a check can be performed by a
script, the script performs it *and* routes straight to the next step,
without waiting for an LLM to read the result and approve it. This applies
recursively: the choice of *which* deterministic check to run (which test
command, which gate script) is itself scripted whenever it's derivable
from the project (`resolve-toolchain` reading marker files, `orchestrator`
reading the ledger's `gate.lang` to pick a gate script) — never asked by
default. A human/LLM question is reserved for genuine ambiguity or missing
data (two ecosystem markers present, no marker at all), asked once, then
recorded so it is never asked again for that branch.

The human-approval gate in `brainstorming` is untouched by automation: no
script substitutes for the human's explicit approval of scope or design.
Design approval permits writing both the spec and the plan without another
written-spec approval.

**Fork history (condensed).** Verified against the actual scripts: after
round 1's script-driven Coder dispatch, nothing ever called `green-gate`,
and `orchestrator`'s `CODER*`/`REVIEW*` cases were no-op stubs — fixed
with `coder-gate` (unbounded retries until green, RED-form check before
commit, TEST_DEFECT short-circuit) plus `red-gate` chaining and
`orchestrator` dispatch-table fixes. A subagent-driven-development audit
added TEST_DEFECT handling and `test-integrity` tamper checks. A routing
pass added `resolve-toolchain` (one-time-per-branch test/analyze
detection; ask only on genuine ambiguity) and the generic `red-gate`, with
`orchestrator` picking the gate by the ledger's `gate.lang`.

## 7. Pipeline phases

1. **Phase 1 — Requirements (once, project-level).** `1a` commercial
   requirements via brainstorming + grill-with-docs; this also produces
   the **Category Skeleton** — three fields (generic category, specific
   category, original implementations) that drive the template search and
   per-task dependency research downstream. `1b` generic technical
   architecture. `1c` interface design is governed by the vendored
   `apple-design` skill: before any UI design decision (screens,
   components, gestures, motion, materials, typography) the acting role
   invokes it and encodes the resulting requirements into the plan tasks'
   `acceptance`. Resolved terms persist in this README.md's glossary +
   ADRs (architectural path only).
2. **Phase 2 — Research & Planning (per task).** `2a` search (Tavily +
   reference sources) and score candidates with `pkg-score`; then, at
   project level, run `template-search` against the Category Skeleton's
   specific category (stars descending, 3-AUTO_APPROVE stop; fallback to
   generic ≥70 with the specific 50–69 group). Score results with
   `template-score`. `2b` select with the developer (as-is / modified /
   from-scratch); `2c` clone the selected template → gap analysis against
   the plan, then write technically complete tasks with `writing-plans`
   (no code downloaded; lockfile only). Pure planning.
3. **Phase 3 — TDD Implementation.** Delegated to
   `two-model-sdd-pipeline` (script-autonomous per-task loop, preferably
   via `run-pipeline`). Flutter additions: `pub-sync` -> `red-gate`
   (dispatches Agente operador on a scaffolded brief, then chains straight
   into `coder-gate`, which owns every retry after that: RED-form check
   (`red-form-check`) + gate check -> PASS (`green-gate` commit + dispatch
   revisor) | FAIL (fix prompt + redispatch with `--continue`, unbounded
   until green) | TEST_DEFECT (stop, `route-next` emits ARBITRATE for
   Agente diretor) -> `route-next` (CORRECTIVE / ARBITRATE / NEXT /
   FINAL_REVIEW). Every LLM-invoked command runs through `scripts/cmd`
   (RTK compression).
4. **Phase 4 — Project-Wide Review.** Revalidate with `green-gate
   --no-commit`, full code review, corrections re-enter Phase 3.

## 8. Roles and tiers

| Role | Tier | Responsibility |
|---|---|---|
| Script CEO | none (deterministic) | gates, test/analyze decisions, dispatch operador/revisor/diretor, routing, commits, ledger; never implements/reviews itself |
| Agente estratégico | Strategic (human) | brainstorming, spec + complete `plan.json`, then DONE |
| Agente diretor | Strategic (`two-model-task-generator`, `mode: all`) | punctual task owner: corrective/arbitrate episodes (findings + full plan.json + target task) and one curated closing package; No EXPAND |
| Agente operador | Operational (`two-model-coder`, `mode: all`) | owns the RED/GREEN loop: authors RED tests, runs them to verify the expected failure, then implements; may run test/analyze/format, never git; unbounded retries until green, resume within task |
| Agente revisor | Strategic (`two-model-reviewer`, `mode: all`) | JSON verdict (APPROVED / SEND_BACK / ESCALATE) on compiler-approved code + test-vs-acceptance fit; never runs test/analyze |
| Strategic Coder | REMOVED | escalation is Agente diretor arbitration (`ARBITRATE`) |

For the plan-driven OpenCode pipeline, `scripts/dispatch` targets the named
agent definition explicitly. The compatibility route without `--backend`
retains OpenCode behavior. New task-worker calls select a backend explicitly;
the Codex adapter takes the strict request via `--request` and its validated
runtime envelope via `CODEX_RUNTIME_JSON`. Both routes reject mismatched
backend requests and never silently cross providers. Both tier agents are `mode: all` (spike-verified:
subagent-mode agents cannot be targeted headlessly by `opencode run
--agent`).

## 9. Deterministic scripts (no AI involvement)

| Script | Purpose | Verdict |
|---|---|---|
| `cmd --full-file FILE -- CMD...` (two-model) | Generic command runner: runs any LLM-invoked command, saves the FULL output to FILE, prints the RTK-compressed view on stdout, returns the command's true exit code | exit = command's exit code; 2 usage |
| `dispatch --agent NAME --task N [--continue SESSION] --prompt-file FILE --log LOG` (two-model) | Legacy-compatible OpenCode worker call; tees JSON events and records the session ID for continuation | OpenCode exit; 2 usage; 3 wrong OpenCode agent |
| `dispatch --backend codex --request REQUEST.json` (two-model) | Native `codex exec --json` worker call; runtime envelope comes from `CODEX_RUNTIME_JSON`; resume requires an identity-bound explicit session ID | 2 usage; 4 invalid configuration/request; 5 confirmed pre-exec startup failure; 6 ambiguous/post-start failure; 124 timeout; 130 interruption |
| `dispatch --backend opencode --agent NAME --task N ...` (two-model) | Explicit legacy OpenCode adapter selection; no Codex fallback | OpenCode exit; 2 usage; 3 wrong OpenCode agent |
| `orchestrator WS TASK [TOTAL]` (two-model) | The single dispatch table: runs `route-next`, executes the script-owned emitted action, prints `OUTCOME:` for the runner | exit 0 handoff; 1 inconsistent; 2 usage |
| `$SUPERPOWERS_DIR/.harness/entrypoints/opencode.sh PLAN_FILE [TOTAL] [--no-push] [--max-parallel N]` | Project-aware OpenCode entry point in the installed vendor checkout: enrolls this project on first use, resolves its pin, and retains the bundle while resuming | exit 0 closed; 1 blocked; 2 usage; 4 upgrade decision required |
| `run-pipeline PLAN_FILE [TOTAL] [--no-push] [--max-parallel N]` (two-model, internal) | Script CEO driver invoked by the project-aware entry point; drives a plan serially or in plan-derived waves to closing → push+PR | exit 0 closed; 1 blocked; 2 usage |
| `harness-project init --project DIR --bundle ID --backend NAME` (two-model) | Safe project enrollment: writes the versioned `.superpowers/harness.json` pin and merges the marked `AGENTS.md` section idempotently; only the given project is touched | exit 0 enrolled; 2 invalid input; 3 operational failure |
| `harness-project prepare --project DIR --backend NAME` (two-model) | Enrolls a first-use project or resolves its pin; reports changed paths before an optional accepted upgrade, and keeps the pin during a resume | exit 0 ready; 2 invalid state; 3 operational failure; 4 upgrade decision required |
| `brief-scaffold WORKSPACE TASK` (two-model) | Scaffold the task brief mechanically from the plan (statement, acceptance, spec_refs, machine-readable RED instructions). No LLM | exit 0 wrote; 1 plan unreadable; 2 usage |
| `coder-agent-for LANG` (two-model) | Maps a `resolve-toolchain` lang to the operador variant (`two-model-coder-{python,node,rust,go}`) | agent name on stdout; 0 |
| `run-gates WS TEST ANALYZE` (two-model) | Generic green approval: full suite + analysis through `cmd` | exit 0 green; 1 tests failed; 2 analysis failed; 3 usage |
| `orient-llm [REPO]` | Brainstorming pre-flight: locate and print this repo's `README.md` so the agent is oriented before work starts | exit 0 printed; 1 missing (gate — stop); 2 usage |
| `pkg-score PACKAGE` | Fetch pub.dev + GitHub, compute the corrected Quality Score | JSON + gate verdict (AUTO_APPROVE / DEVELOPER_DECISION / AUTO_REJECT) |
| `template-search CATEGORY` | Search GitHub for project templates (stars descending, 3-AUTO_APPROVE stop; fallback to generic ≥70 with the specific 50–69 group) | JSON list of candidates with scores |
| `template-score TEMPLATE` | Score a project template candidate | JSON + gate verdict (same semantics as pkg-score) |
| `pub-sync [PACKAGE]` | `pub add`/`pub get` + lockfile; `pub upgrade --dry-run` conflict report | exit 0 resolved; exit 1 conflicts (`pub-sync-report.txt`) |
| `red-gate WORKSPACE TASK` (two-model) | Per-task kickoff: verify the scaffolded brief, dispatch the lang-selected operador variant, chain `coder-gate` (RED-form check via `red-form-check`) | exit = `coder-gate`'s exit; 2 usage |
| `coder-gate WORKSPACE TASK` (two-model) | Unbounded retries until green: RED-form check via `red-form-check`, scope gate via `keep-discard`, commit, advisory `interface-check`, `review-package`, dispatch revisor; TEST_DEFECT stops | exit 0 green+committed+revisor dispatched; 1 blocking failure; 2 TEST_DEFECT / scope violation; 3 usage |
| `red-form-check WORKSPACE TASK LANG` (two-model) | Deterministic RED-form classifier: requires the suite loaded, ≥1 test executed, and an assertion/runtime failure | exit 0 valid red; 1 invalid red; 2 unsupported language / usage |
| `resolve-toolchain WORKSPACE [ROOT]` (two-model) | One-time-per-branch ecosystem detection, ledgers `TEST_CMD`/`ANALYZE_CMD` | exit 0 resolved; 1 ambiguous; 2 usage/no marker |
| `green-gate [--no-commit] [-m MSG] [-l LEDGER] [-w WS -t TASK -b BASE]` | Chain `flutter test` + `flutter analyze` (through `cmd`) + commit, then review package + revisor dispatch | exit 0 green (+commit +revisor); 1 tests; 2 analyze; 4 scope violation |
| `rtk-run [--ws WS --task N] <red\|test\|analyze> [ARGS...]` (flutter) | The Agente operador's SCOPED runner: `red` writes `WS/task-N-red.txt` (the path `red-form-check` reads) | the wrapped command's exit code; 2 usage |
| `route-next WORKSPACE TASK [TOTAL]` | Deterministic router: emits BRIEF / RED / CODER / REVIEW / CORRECTIVE / ARBITRATE / NEXT / FINAL_REVIEW | exit 0 routed; 1 inconsistent; 2 usage |
| `review-package WORKSPACE BASE HEAD [OUTFILE] [TASK]` | Build a review bundle (commits + stat + diff), inline the task brief | exit 0 wrote; 2 usage |
| `keep-discard WORKSPACE TASK` | The scope gate: KEEP when partial work is in `touches` (newly authored tests exempt) | exit 0 KEEP; 1 DISCARD; 2 usage; 3 DISCARD (no partial work) |
| `interface-check WORKSPACE TASK BASE` | Advisory ledger entry when the diff touches a file another task consumes | exit 0 clean; 1 interface changed; 2 usage |
| `final-gate WORKSPACE TOTAL_TASKS` | Pre-closing: all complete + no unresolved verdicts + no blocking parked + tests/analyze green + no pending worktree | exit 0 ready; 1 blockers; 2 usage |
| `doc-check [REPO]` | Deterministic gate: pipeline files changed → README.md must also change | exit 0 OK; 1 violation; 2 usage |
| `parse-review LOGFILE OUTFILE` (two-model) | Deterministic parser: extracts the revisor's structured verdict from the JSONL event log | exit 0 verdict written; 1 no verdict; 2 usage |

All scripts honor `FLUTTER_BIN`, `DART_BIN`, `GIT_BIN`, `RTK_BIN`,
`DISPATCH_BIN`, `OPENCODE_BIN` env overrides. `cmd` also respects
`RTK_ENABLED=0` (passthrough) and `RTK_BIN` (binary override).

## 10. Ordering invariants (do not violate)

- **Commands are scripted and RTK-compressed:** every LLM-invoked command
  line runs through `scripts/cmd`. Raw command output never enters an LLM
  context window. Deterministic gates keep reading full files, so nothing
  a verdict depends on is ever compressed.
- **Dispatch is script-owned:** red-gate dispatches Agente operador on a
  scaffolded brief; green-gate dispatches Agente revisor after commit;
  `run-pipeline` drives the whole branch. The interactive session is never
  a link in the dispatch chain.
- **Batching is a plan-authoring decision, never a runtime one:** a task
  may cover several same-shape, mutually independent edits — every file in
  `touches`, every observable behavior in `acceptance`.
- **Parallel execution is plan-derived and script-owned:**
  `depends_on` + `touches` are scheduling-authoritative; `wave-next`
  computes each wave, `worktree-alloc` gives every task its own git
  worktree + branch and ledger shard, `task-run` drives it, and
  `integrate` folds the wave back. Default `--max-parallel 2`.
- **Operador owns the RED/GREEN loop:** it authors RED tests, runs them
  saving the machine-readable output, declares and confirms the expected
  reason, then implements and runs them green. It may run test/analyze/
  format commands but never git. Script CEO validates the saved RED form
  with `red-form-check` and decides the authoritative gate by exit code —
  unbounded retries until green; only TEST_DEFECT escalates to Agente
  diretor.
- **Revisor reviews compiler-approved code only:** never runs or re-runs
  test/analyze; scope is design, architecture, spec compliance (incl.
  spec-refs alignment), interface discipline, and test-vs-acceptance fit.
  It is the sole independent semantic guarantee that the tests encode the
  acceptance.
- **No knowledge graph:** no stage builds, updates, or queries a code
  graph. Briefs are scaffolded from plan tasks; the revisor reviews brief
  + diff only.
- **Gates are exit codes:** never judge test outcomes by reading output —
  run the gate script and read its exit code.
- **Docs describe implemented behavior:** skill/integration docs must match
  the scripts; stale claims are corrected in the same change as the code.
- **Routing is scripted:** after every review outcome run `route-next` and
  execute its emitted action — the LLM never decides transitions by
  reasoning.
- **Cache-aware calls:** operador and revisor retain their sessions WITHIN
  a task until approval; when the task changes, dispatch fresh. Agente
  diretor is punctual.
- **Review pre-gates are exit codes:** `keep-discard` runs before every
  commit; `interface-check` is the post-commit advisory entry;
  `final-gate` verifies completion before closing.
- **Ledger via script:** the ledger is appended through `ledger-append`,
  never free-handed as prose.
- **Workers never commit:** only Script CEO (via `green-gate` or the
  orchestrator) commits.
- **No approval after decisions:** approval happens at the gate (once per
  branch) and at Phase 2a/2b selection; from Phase 2c onward the branch
  runs to completion without check-ins.

## 11. Quality Score (0–100)

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

Corrections: **/160 not /140** (pub.dev max is 160); issue ratio is
**PR-aware** (`open_issues_count` includes PRs — use
`search/issues?type=issue`); dependents have no official endpoint
(best-effort scrape or `pub_api_client`); no-GitHub packages fall back to
`latest.published`.

Gate: ≥70 auto-approve; 50–69 developer decision; <50 reject ->
from-scratch.

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
candidates descending). Same gate semantics as pkg-score (≥70
auto-approve; 50–69 developer decision; <50 reject).

### Category Skeleton

The Category Skeleton is produced during Phase 1a and contains three
fields: the **generic category**, **specific category**, and **original
implementations**. These fields drive the `template-search` query
(specific category first) and the per-task dependency research in Phase 3.

## 12. Glossary (roles, gates, flows)

- **Script CEO (Orchestrator)** — the deterministic, modular bash layer
  that owns the per-task flow: gates, test/analyze decisions, subagent
  dispatch, routing, and commits. A thin driver script (`orchestrator`,
  topped by `run-pipeline` for full-branch runs) plus specialized
  sub-scripts. Script CEO is never an LLM; its verdicts are exit codes
  and its outputs are files.
- **Agente estratégico** — the interactive OpenCode session the developer
  opened for brainstorming. Produces the design spec and a COMPLETE
  `plan.json` (tasks with acceptance, spec_refs, touches, depends_on; no
  expected_red), then DONE. Never in the per-task loop.
- **Agente diretor** — Strategic tier (`two-model-task-generator`).
  Punctual task owner: on corrective/arbitrate the script dispatches it
  with script-controlled context, resuming only within the same episode;
  closing is a one-shot curated package. No EXPAND, no cross-branch
  persistent session.
- **Agente operador** — Operational tier. Owns the RED/GREEN loop:
  receives the scaffolded brief, authors RED tests, RUNS them and saves
  the machine-readable output (form-checked by the script), DECLARES and
  confirms the expected reason before implementing, then writes
  implementation code and runs the tests green. May run test/analyze/
  format, never git.
- **Agente revisor** — Strategic tier. Reviews only compiler-approved code.
  Evaluates design, architecture, spec compliance (incl. spec-refs
  alignment), interface discipline, and test-vs-acceptance fit. Returns a
  structured JSON verdict (APPROVED / SEND_BACK / ESCALATE + findings +
  minors). Context kept during the task's correction loops; zeroed after
  approval.
- **run-pipeline** — top-level Script CEO driver: loops route-next →
  execute until FINAL_REVIEW → closing → push+PR.
- **brief-scaffold** — mechanically scaffolds task briefs from plan tasks.
  No LLM call.
- **red-gate** — verifies the scaffolded brief exists, dispatches Agente
  operador, then chains coder-gate.
- **green-gate** — chains full suite + `flutter analyze` + commit, then
  dispatches Agente revisor.
- **coder-gate** — unbounded retries until green; verifies the operador's
  saved RED evidence by FORM via `red-form-check`; the keep-discard scope
  gate runs before commit. Only TEST_DEFECT leaves the loop.
- **route-next** — deterministic router; Script CEO executes its emitted
  action.
- **dispatch** — legacy OpenCode headless launcher with `--continue --session`
  resume; Codex worker continuation uses an explicit identity-checked session ID.
- **cmd** — command runner; RTK-compressed LLM-facing stdout, full output
  to files.
- **Context retention:** operador and revisor keep their sessions until
  the revisor approves the task; both are zeroed at task approval. Agente
  diretor is punctual. The ledger is the compaction-safe state checkpoint.
- **Parallel task execution:** `depends_on` + `touches` are
  scheduling-authoritative; waves are computed by `wave-next`; one git
  worktree + `task/<N>` branch per task with a per-worktree ledger shard;
  `integrate` is the script-owned serial merge gate.

## 13. Packaging and distribution

Two package paths distribute the same validated bundle (runtime files,
prompts, skills, canonical docs, license):

- `scripts/package-codex-plugin.sh` — portal archive (zip or tar.gz,
  rootless: `.codex-plugin/`, `agent/`, `assets/`, `skills/`, README.md,
  LICENSE, CODE_OF_CONDUCT.md). Both formats carry the same files.
- `scripts/sync-to-codex-plugin.sh` — embedded plugin sync into the
  collection repository (tracked plugin files only; OpenAI-owned
  marketplace metadata is preserved, never overwritten).

## 14. Repository layout

```
README.md                       <- this file: the single canonical harness reference
README.txt                      <- human-facing readme (condensed)
agent/                          <- mirrored tier agent definitions (coder + variants/controller/reviewer/task-generator/flutter-pipeline)
docs/superpowers/               <- ADRs, specs, plans (historical records are preserved)
skills/flutter-app-pipeline/    <- the Flutter layer + scripts + tests
skills/two-model-sdd-pipeline/  <- the generic two-tier engine + scripts
skills/apple-design/            <- vendored Apple interface-design skill (MIT)
skills/write-script/            <- deterministic-script conventions
skills/skill-scripter/          <- audits a skill/stage for prose decisions that should be scripts
```

## 15. How to work with this harness

1. New dev request -> invoke `brainstorming` before any code. Its
   pre-flight runs `scripts/orient-llm` deterministically, which prints
   this `README.md` as orientation before anything is classified or
   designed.
2. Flutter/Dart work -> run `flutter-app-pipeline`; on the two-tier gate
   default to YES. Tiers are pre-configured locally
   (`two-model-coder` / `two-model-reviewer` agents); test/analyze
   commands resolve via `resolve-toolchain` once per branch — ask about
   tiers only when the local pipeline is not installed.
3. Per task: `pkg-score` candidates -> select with the developer ->
   `writing-plans` tasks -> `pub-sync` -> Agente estratégico writes the
   complete `plan.json` + spec (then DONE) -> the installed vendor checkout's
   `.harness/entrypoints/opencode.sh PLAN_FILE`:
   the plan is already complete (No EXPAND); per task `brief-scaffold` ->
   operador RED/GREEN -> commit -> revisor verdict -> `route-next`.
4. After a session that changed the pipeline itself, update this
   `README.md` and include it in the push (`doc-check` enforces this
   deterministically). Do not churn docs when behavior did not change.

## 16. Language policy

All responses and all internal artifacts are in **English** — task
briefs, RED tests, design docs, glossary entries, ADRs, ledger summaries,
review reports, commit messages, code comments — regardless of the
developer's language. The one exception is the software's **UI**
(user-facing strings, labels, copy), which defaults to the developer's
language (pt-br).

## 17. GitHub authentication

GitHub REST: 60 req/h unauthenticated, 5000 req/h authenticated. Set a
fine-grained PAT (public read only) as `GITHUB_TOKEN` (env or CI secret).
Never hardcode or commit tokens. `pkg-score` reads the env var
automatically.

## 18. Tests

The deterministic scripts have python unittest suites:

```
skills/flutter-app-pipeline/tests/run-tests.sh
skills/two-model-sdd-pipeline/tests/run-tests.sh
```

Additional harness contract suites live under `tests/` (packaging, sync,
plugin loading, shell lint).

## 19. License

MIT — see LICENSE. Upstream: https://github.com/obra/superpowers
