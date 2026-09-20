# superpowers-two-model-pipeline — LLM/Agent README

## Jev advisory classifier

`skills/two-model-sdd-pipeline/scripts/jev-classify` is a Choice-only TypeSafe
adapter. It reads a schema and state JSON file and requires `--workspace` and
`--site`; it uses `TYPESAFE_API_KEY` only for a real request to
`https://api.typesafe.ai/v1/systemone`. Its JSON output never contains the
key. Exit `0` means every valid answer meets the threshold, `1` means a valid
low-confidence answer or open circuit, `2` is invalid local input, and `3` is
unavailable setup, transport, or provider data. Cache and circuit records are
private to each workspace/site. Sites 1–4 default to shadow, require a bound
calibration report for active action, and Site 5 only permits explicit
`selected-apply`; Jev cannot approve, route, or write the authoritative ledger.

## Site 5 plan fusion

`plan-fusion propose DRAFT --workspace DIR --report REPORT` validates a complete draft and records shadow recommendations for independent, same-shape task pairs. `plan-fusion apply DRAFT --report REPORT --selection SELECTION --output OUTPUT` is offline and requires an explicit strategist selection of qualifying recommendations. It writes a distinct, consecutive-ID pre-runtime plan with provenance; it never fuses automatically or changes a runtime consumer. Shadow agreement and observed outcomes of executed fusions are evaluated separately.

`jev-evaluate REPORTS_JSON LABELS_JSON --output REPORT` is offline reporting
only. It separates recommendation agreement from observed executed outcomes
and reports missing evidence; it cannot activate a policy or infer a
counterfactual result.

## Template catalog evidence

`template-evidence OWNER/REPO --output FILE` collects the scoring report,
README, `pubspec.yaml`, repository tree, explicit SDK/license constraints, and
a content hash. Missing source text stays `null`. `template-catalog add|list|outcome`
persists the evidence transactionally; exit 0 means success, 1 means domain or
write failure, and 2 means usage or invalid local input. The score verdict is independent from
Jev triage, confidence, policy, actor, vector identity, and adoption history;
an evidence update clears only derived triage/vector fields. Catalog writes do
not clone, install, select, or adopt a project template.

### Site 2 deterministic template recall

`template-refresh OWNER/REPO --database DB --category CATEGORY --project NAME`
collects complete evidence and atomically refreshes one catalog row. Collection
or validation failure returns a domain/setup error and preserves the previous
row. `template-recall CATEGORY --database DB` is offline and read-only; it
filters fresh AUTO_APPROVE rows by package overlap and optional injected-vector
cosine similarity. A vector is eligible only when its model, vector identity,
source evidence hash, dimensions, and finite values match the query and row.
Missing databases, malformed vectors, invalid top/age arguments, and missing
embedding setup are setup errors, never silent MISS results.

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

- **`two-model-sdd-pipeline`** (generic engine): a deterministic **Script CEO**,
  invokable anywhere as `scripts/run-pipeline PLAN_FILE`,
  owns the per-task loop — gates, test/analyze decisions, subagent dispatch,
  routing, and commits. The interactive session (**Agente estratégico**) writes
  the spec and a complete `plan.json` (acceptance; no `expected_red`),
  then DONE. **Agente diretor** (`two-model-task-generator`) is a punctual
  task owner: it rules corrective/arbitrate episodes with script-controlled
  context and closes the branch once with a curated package (No EXPAND).
  **Agente operador** (`two-model-coder`) owns its RED/GREEN loop — it authors
  RED tests, runs them saving the machine-readable output, declares the
  expected reason, then implements and
  runs them green (ADR-0007). **Agente revisor**
  (`two-model-reviewer`) reviews compiler-approved code (plus
  test-vs-acceptance fit) and returns
  a structured JSON verdict; it is the sole independent semantic guarantee.
  State lives in the JSON plan, git history, and a
  script-maintained JSONL **ledger**, never in an LLM's memory.
- **`flutter-app-pipeline`** (Flutter layer, on top): adds package research
  with a corrected Quality Score, the deterministic Flutter scripts, and the
  **RTK-compression** ordering rule. It delegates the
  per-task implementation loop back to `two-model-sdd-pipeline`. Interface
  design is governed by the vendored **`apple-design`** skill
  (`skills/apple-design/SKILL.md`, MIT): Phase 1b/2 UI decisions and the
  operador's UI code must apply its principles (response, direct manipulation,
  interruptibility, springs, momentum, materials, typography, reduced motion),
  and the revisor checks them.

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
| Superpowers (this fork) | Skills: brainstorming (grill-with-docs + Incremental Persistence), writing-plans, test-driven-development, two-model-sdd-pipeline, flutter-app-pipeline, apple-design (vendored interface-design principles; MIT), write-script + skill-scripter (skill-authoring chain: audit a skill for scriptizable steps, then write the script) |
| RTK (`rtk`) | CLI proxy that compresses command output before it reaches an LLM context window (60-90% token savings); wired through `scripts/cmd` |
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
   `1b` generic technical architecture. `1c` interface design is governed by the
   vendored `apple-design` skill: before any UI design decision (screens,
   components, gestures, motion, materials, typography) the acting role invokes
   it and encodes the resulting requirements into the plan tasks' `acceptance`.
   Resolved terms persist in `CONTEXT.md` + ADRs (architectural path only).
2. **Phase 2 — Research & Planning (per task).** `2a` search (Tavily + reference
   sources) and score candidates with `pkg-score`; then, at project level, run
   `template-search` against the Category Skeleton's specific category (stars
   descending, 3-AUTO_APPROVE stop; fallback to generic ≥70 with the specific
   50–69 group). Score results with `template-score`. `2b` select with the
   developer (as-is / modified / from-scratch); `2c` clone the selected template
   → gap analysis against the plan, then write
   technically complete tasks with `writing-plans` (no code downloaded; lockfile
   only). Pure planning.
3. **Phase 3 — TDD Implementation.** Delegated to `two-model-sdd-pipeline`
   (script-autonomous per-task loop, preferably via `run-pipeline`).
   Flutter additions: `pub-sync` ->
   `red-gate` (dispatches Agente operador on a scaffolded brief, then chains
   straight into `coder-gate`, which owns every retry after that: RED-form
   check (`red-form-check`) + gate check -> PASS (`green-gate` commit + dispatch revisor) | FAIL
   (fix prompt + redispatch with `--continue`, unbounded until green) |
   TEST_DEFECT (stop, `route-next` emits ARBITRATE for Agente diretor) ->
   `route-next` (CORRECTIVE / ARBITRATE / NEXT / FINAL_REVIEW).
   `run-pipeline` delegates every script-owned action (BRIEF/RED/CODER) to
   `orchestrator`, the single dispatch table, and owns only the LLM branches
   (REVIEW parse, CORRECTIVE, ARBITRATE) and closing; `orchestrator` executes
   the brief scaffold and the gates and hands the re-routed `OUTCOME` back.
   Every LLM-invoked command runs through `scripts/cmd` (RTK compression).
4. **Phase 4 — Project-Wide Review.** Revalidate with `green-gate --no-commit`,
   full code review, corrections re-enter Phase 3.

## 5. Roles and tiers

| Role | Tier | Responsibility |
|---|---|---|
| Script CEO | none (deterministic) | gates, test/analyze decisions, dispatch operador/revisor/diretor, routing, commits, ledger; never implements/reviews itself |
| Agente estratégico | Strategic (human) | brainstorming, spec + complete `plan.json`, then DONE |
| Agente diretor | Strategic (`two-model-task-generator`, `mode: all`) | punctual task owner: corrective/arbitrate episodes (findings + full plan.json + target task) and one curated closing package; No EXPAND |
| Agente operador | Operational (`two-model-coder`, `mode: all`) | owns the RED/GREEN loop: authors RED tests, runs them to verify the expected failure, then implements; may run test/analyze/format, never git; unbounded retries until green, resume within task |
| Agente revisor | Strategic (`two-model-reviewer`, `mode: all`) | JSON verdict (APPROVED / SEND_BACK / ESCALATE) on compiler-approved code + test-vs-acceptance fit; never runs test/analyze |
| Strategic Coder | REMOVED | escalation is Agente diretor arbitration (`ARBITRATE`) |

Always dispatch via `scripts/dispatch`, which targets the named agent
definition explicitly; omitted model silently inherits the expensive session
model. Both tier agents are `mode: all` (spike-verified: subagent-mode agents
cannot be targeted headlessly by `opencode run --agent`).

## 6. Deterministic scripts (no AI involvement)

| Script | Purpose | Verdict |
|---|---|---|
| `cmd --full-file FILE -- CMD...` (two-model) | Generic command runner: runs any LLM-invoked command, saves the FULL output to FILE, prints the RTK-compressed view on stdout, returns the command's true exit code. `flutter test`/`flutter analyze` compress via `rtk test`/`rtk err` wrappers derived from the file (verdict from the raw run — wrappers mask child exit codes) | exit = command's exit code; 2 usage |
| `dispatch --agent NAME --task N [--continue SESSION] --prompt-file FILE --log LOG` (two-model) | Headless subagent launcher: `opencode run --agent <def> --format json`, tees the JSON event stream to LOG (observability) plus a live progress digest on stdout, records the session id for resume. The brief is passed as a positional so opencode auto-attaches it (never `--file` — this opencode version misparses the message when `--file` is present). The session id is extracted by the JSON digest filter (whitespace-tolerant) and written per-agent (`task-N-<agent>-session.txt`; the generic record was removed as a trap); a missing id ledgers `session_lost`. The not-a-primary-agent guard scans the non-JSON log lines (stderr/stdout interleave under buffering), so an embedded phrase inside a JSON event cannot false-trip it. On `--continue` (corrective round) the prompt explicitly tells the resumed model the brief has CHANGED and to re-read it fully. Refuses (exit 3) when the targeted agent is not `mode: all` | exit = opencode's exit; 2 usage; 3 not a primary agent |
| `session-clean WS TASK\|all` (two-model) | Session hygiene: deletes the opencode sessions a task recorded (`task-N-*-session.txt`, per-agent only; the generic record was removed as a trap). The per-task loop keeps sessions so corrective rounds and debugging can resume them; a phase launcher runs `session-clean WS all` **after** `run-pipeline` returns, and a DB-maintenance tool (`~/.config/opencode/tools/db-maintenance.py prune-sessions`) prunes stragglers, so headless sessions cannot accumulate — they grew `opencode.db` to multi-GB and contributed to a 2026-09-14 freeze. Best-effort; `OPENCODE_BIN` overrides the binary | exit 0 best-effort; 2 usage |
| `orchestrator WS TASK [TOTAL]` (two-model) | The single dispatch table: runs `route-next`, executes the script-owned emitted action (scaffold the BRIEF, run the lang-selected `red-gate`, or `coder-gate`), re-routes, and prints `OUTCOME:` for `run-pipeline`/the interactive session; hands CORRECTIVE/ARBITRATE/REVIEW/NEXT/FINAL_REVIEW back. `CODER_GATE_BIN` (legacy alias `CODER_GATE`) | exit 0 handoff; 1 inconsistent; 2 usage |
| `run-pipeline PLAN_FILE [TOTAL] [--no-push] [--max-parallel N]` (two-model) | Top-level Script CEO driver, invokable anywhere: drives the plan serially (`N == 1`) or in plan-derived waves (`N > 1`, default 2: `wave-next` → `worktree-alloc` → `task-run` per worktree in parallel → `integrate`), then closing (final-gate + package + diretor assessment) → push+PR | exit 0 closed; 1 blocked (fix + re-run continues); 2 usage |
| `touches-overlap WORKSPACE ID [ID...]` (two-model) | Declared-`touches` pairwise disjointness decider: two tasks may share a wave only when their `touches` sets are disjoint (exact path equality). Pure read; consumed by `wave-next` | exit 0 disjoint (`TOUCHES-OVERLAP: disjoint`); 1 overlap (conflicting pairs on stderr); 2 usage / missing plan / unknown id / malformed plan |
| `wave-next WORKSPACE [MAX_PARALLEL]` (two-model) | Plan-derived wave scheduler: reads `plan.json` + the merged ledger, prints `FINAL_REVIEW` when every task is done, else one `RUN <id>` per ready task (all `depends_on` done, not done, no open episode, `touches` pairwise-disjoint, capped at `MAX_PARALLEL`, default 2). A corrective or open-episode task is emitted alone. Selects fewest-touches-first (a wide low-id task must not wall out a schedulable pair) and prints every deferred task's conflicting files to stderr (`WAVE-DEFER`), so a collapsed wave is visible, not silent. In-flight episodes are only visible once `integrate` folds their shard in | exit 0 wave emitted / FINAL_REVIEW; 1 `WAVE_EMPTY` (nothing runnable, blocked); 2 usage |
| `ledger-merge INTEGRATION_WS SOURCE_LEDGER [SOURCE_LEDGER...]` (two-model) | Folds per-worktree ledger shards into the integration ledger through the sole writer in ONE batch write (`ledger-append --stdin-tsv`, TSV because the writer is bash and can split a tab line without a JSON parser); skips `gate` entries and content-identical duplicates (`ts`-insensitive) so re-runs are idempotent; rebuilds partitions via `ledger-migrate` | exit 0 merged; 1 the batch failed to append; 2 usage |
| `worktree-alloc WORKSPACE TASK` (two-model) | Allocates `<repo>/.superpowers/two-model/worktrees/task-<N>` + branch `task/<N>` from the integration HEAD, seeds the worktree workspace (`plan.json` + a ledger shard holding only the branch `gate` entry), records `base=<sha>`, ledgers `worktree_alloc`, prints `WORKTREE=`/`WS=`. Best-effort warms the new tree (copies `pubspec.lock` + `.dart_tool` from the integration tree, then `pub get --offline`) so the first gate pays no cold resolve/compile; a failed warm-up degrades to the cold path and never blocks allocation. The shard directory is `WS_SLUG` when set (never `basename` a cygpath'd path) | exit 0 allocated; 1 already allocated (still prints `WORKTREE=`/`WS=` for reuse); 2 usage |
| `worktree-release WORKSPACE TASK` (two-model) | Removes a task worktree + its `task/<N>` branch only after the branch tip is an ancestor of the integration HEAD; when the tip equals its allocation base (a never-committed branch) it releases only if the shard holds `task_complete` - an approved no-op task (ADR-0017); an unapproved never-worked branch is kept as the only debug copy. Ledgers `worktree_release`; never removes on failure. The shard directory is `WS_SLUG` when set | exit 0 released; 1 not merged / not approved / branch not found; 2 usage |
| `task-run WORKSPACE TASK TOTAL` (two-model) | The per-task lifecycle extracted from `run-pipeline`, shared by the serial path and each wave worktree: loops `orchestrator` and owns the LLM branches (REVIEW parse, CORRECTIVE, ARBITRATE) until the task is APPROVED or blocked. Operates on whatever working tree its cwd resolves to | exit 0 task complete (APPROVED); 1 blocked / escalated / unresolved arbitration; 2 usage |
| `integrate WORKSPACE TASK [TASK...]` (two-model) | Script-owned integration gate. Require every task's worktree shard to hold `task_complete` (a committed-but-unapproved shard is `integration_failed not approved`, never merged or released). An approved task whose branch never committed (its tip equals the `worktree_alloc` base) is a **no-op**: `integrated N "no-op (no commits)"`, shard folded and worktree released, with nothing merged, gated or committed (ADR-0017). A wave of **≥2** approved tasks is then merged first and gated **once** (`green-gate --no-commit` for `lang=flutter`, without the per-task scope check; else `run-gates`): green commits once and folds each shard + releases each worktree; red `git reset --hard`s the batch and falls back to the per-merge loop, which **is** the bisect (merge one, gate, `integration_failed` + `git merge --abort` on conflict/red/commit-failure, keep going). A wave of **one** task takes the per-merge path directly, which also carries the ADR-0013 skip, with an auditable `integrate_suite_skipped` entry, when the merge is provably tree-equivalent to the branch tip's already-gated commit (HEAD is an ancestor of `task/<N>` and the shard's recorded `tree=` matches that tree) | exit 0 every task integrated; 1 ≥1 `integration_failed`; 2 usage |
| `brief-scaffold WORKSPACE TASK` (two-model) | Scaffold the task brief mechanically from the plan (statement, acceptance, spec_refs and machine-readable RED instructions). The RED order OFFERS the scoped `rtk-run` runner (compressed output, evidence where the gate reads it) without mandating it — running the project runner directly and redirecting its machine-readable output to the same path is equally acceptable; it also states that `coder-gate` owns the authoritative full suite (ADR-0016, relaxed). It no longer asks for a RED reason declaration: no script read that file, so it was pure LLM step cost. Rejects test-like `touches` (test files are defined as changed minus `touches`, so a test path inside `touches` can never prove RED). No LLM | exit 0 wrote; 1 plan unreadable; 2 usage/missing fields/test-like touches |
| `coder-agent-for LANG` (two-model) | Maps a `resolve-toolchain` lang to the operador definition whose bash allowlist can run that ecosystem's tests (`two-model-coder-{python,node,rust,go}`; flutter/unknown → base). Shared by both red-gates, `coder-gate`, and the corrective path | agent name on stdout; 0 |
| `run-gates WS TEST ANALYZE` (two-model) | Generic green approval: full suite + analysis through `cmd` (language-agnostic mirror of green-gate) | exit 0 green; 1 tests failed; 2 analysis failed; 3 usage |
| `orient-llm [REPO]` | Brainstorming pre-flight: locate and print this repo's `README-LLM.md` so the agent is oriented on how to run the pipeline | exit 0 printed; 1 missing (gate — stop); 2 usage |
| `pkg-score PACKAGE` | Fetch pub.dev + GitHub, compute the corrected Quality Score | JSON + gate verdict (AUTO_APPROVE / DEVELOPER_DECISION / AUTO_REJECT) |
| `template-search CATEGORY` | Search GitHub for project templates in the given category (stars descending, 3-AUTO_APPROVE stop; fallback to generic ≥70 with the specific 50–69 group) | JSON list of candidates with scores |
| `template-score TEMPLATE` | Score a project template candidate (stars, recency, Flutter/Dart readiness, issue ratio, sustained interest, license, README) | JSON + gate verdict (same semantics as pkg-score) |
| `pub-sync [PACKAGE]` | `pub add`/`pub get` + lockfile; `pub upgrade --dry-run` conflict report | exit 0 resolved; exit 1 conflicts (`pub-sync-report.txt`) |
| `red-gate WORKSPACE TASK` (two-model; optional TEST_CMD) | The single per-task kickoff (H4): verify the scaffolded brief, dispatch the lang-selected operador variant, capture an interrupted dispatch (`dispatch_interrupted`, exit = dispatch's code), then chain `coder-gate` (retries, RED-form check via `red-form-check`, C2 scope gate, commit, revisor dispatch). The test command comes from the ledger's `gate.test_cmd`. The Flutter file is now a thin shim over this one | exit = `coder-gate`'s exit; dispatch's exit if interrupted; 2 usage/no test_cmd |
| `coder-gate WORKSPACE TASK` (two-model) | Unbounded retries until green, no hand-back: after **every** operador attempt (first from `red-gate`, or a resume), runs the gate (`green-gate` for lang=flutter, `run-gates` otherwise), auto-applies the toolchain formatter before the Flutter check (drift is mechanical, never an LLM round-trip), ledgers `coder_round`, and decides by exit code/log content alone — PASS → validate the saved RED form with `red-form-check` (suite loaded, ≥1 test executed, failed as assertion/runtime; a compile/load red fails the round), run the **C2 scope gate** (`keep-discard`; out-of-scope → ledger `scope_violation`, exit 2) then commit, then advisory `interface-check` (`interface_touched`), `review-package` and dispatch revisor; FAIL → rebuild the fix prompt (prior diff + gate report + `.analyze` annex + brief) and resume the operador's own per-agent session (the lang variant) with `--continue`, unbounded until green; `TEST_DEFECT` seen in the latest log → ledger `escalated` and stop | exit 0 green+RED-form-valid+scope-clean+committed+revisor dispatched; 2 TEST_DEFECT / scope violation; 3 usage |
| `red-form-check WORKSPACE TASK LANG` (two-model) | Deterministic RED-form classifier: reads the operador's saved machine-readable evidence (`<ws>/task-N-red.txt`) and requires the suite loaded, ≥1 test executed, and an assertion/runtime failure. Unsupported language → exit 2 (caller falls back to a presence check). No LLM call | exit 0 valid red; 1 invalid red / missing evidence; 2 unsupported language / usage |
| `resolve-toolchain WORKSPACE [ROOT]` (two-model) | One-time-per-branch, no-LLM detection: inspects `ROOT` for a known ecosystem marker (`pubspec.yaml`, `Cargo.toml`, `go.mod`, `package.json`, `pyproject.toml`/`requirements.txt`) and resolves `TEST_CMD`/`ANALYZE_CMD`; creates the workspace and ledgers the `gate` entry unconditionally (fresh-workspace safe — no chicken-and-egg with `route-next`). This is what lets `orchestrator` pick the right `red-gate` and lets the generic `red-gate`/`run-gates` run without ever asking | exit 0 resolved + ledgered; exit 1 ambiguous (multiple markers — manual fallback); exit 2 usage/no marker (manual fallback) |
| `green-gate [--no-commit] [-m MSG] [-l LEDGER] [-w WS -t TASK -b BASE]` | Chain `flutter test` + `flutter analyze` (both through `cmd` — M6) + commit. No format gate (M8: coder-gate auto-applies the formatter first, so it could never fire). On commit: appends the `commit` ledger entry (including the validated `tree=` hash that `integrate` compares to skip a provably redundant post-merge suite; ADR-0013), advisory `interface-check`, then review package + **dispatches revisor**; the C2 scope gate runs first via `keep-discard`. `--no-commit` never commits/never dispatches | exit 0 green (+commit +revisor); 1 tests; 2 analyze; 4 scope violation |
| `rtk-run [--ws WS --task N] <red\|test\|analyze> [ARGS...]` (flutter) | The Agente operador's SCOPED runner (T1, ADR-0016). It accepts only three modes and delegates to `cmd`, so the operador's test output is RTK-compressed while the FULL output lands on disk: `red` runs `flutter test --machine` and writes `WS/task-N-red.txt` (the exact path `red-form-check` reads), `test` runs `flutter test`, `analyze` runs `flutter analyze`. It is OFFERED by the brief, not mandated — the operador may run the project runner directly instead and redirect the evidence itself. Its allowlist entry is an install-independent two-sided wildcard (`*flutter-app-pipeline/scripts/rtk-run*`, permission `*` matches any character), so it matches from any checkout and however the shell wraps the call (`& "<path>"`, `bash "<path>"`, or bare). The coder definition ships platform-generic READ-ONLY allowances (Windows cmdlets `Get-ChildItem`/`Get-Content`/… and POSIX `ls`/`cat`/`grep`/…). It does NOT allow the generic interpreters (`bash*`/`python*`), which would be arbitrary execution — the measured saving comes from the read-only set, not from them. A per-machine override is what let install-specific paths leak into the mirror, so the LIVE definition and the mirror are kept identical | the wrapped command's exit code; 2 usage |
| `route-next WORKSPACE TASK [TOTAL]` | Deterministic router: reads the ledger, emits the next action (BRIEF / RED / CODER / REVIEW / CORRECTIVE / ARBITRATE / NEXT / FINAL_REVIEW). An `arbitrate_resolved` newer than the last escalation re-scaffolds (`BRIEF`); a re-escalation after a ruling is exit 1 "arbitration did not resolve task N" (C1). `scope_violation` escalates like `escalated`. Task count from JSON, not an `"id"` grep (M5) | exit 0 routed; 1 inconsistent / arbitration failed; 2 usage |
| `review-package WORKSPACE BASE HEAD [OUTFILE] [TASK]` | Build a review bundle (commits + stat + diff). When `TASK` is given, inlines `task-TASK-brief.md` ahead of the commit list so the revisor receives the brief in the single `--prompt-file` package | exit 0 wrote; 2 usage |
| `keep-discard WORKSPACE TASK` | The C2 scope gate (run before any commit): KEEP when the partial work is in `touches`; newly authored test files are exempt (H3, shared `is_test_path`), a modified committed test file is tampering; build output (`.freezed.dart`, `.g.dart`, `.gr.dart`, `.gen.dart`, `.mocks.dart`) and the tracked plan (`docs/superpowers/plans/*.json`) are exempt too — codegen is derived, not authored scope, and a whole-project generator run rewrites every drifted generated file (C3, ADR-0014) | exit 0 KEEP; 1 DISCARD out-of-scope/tampered; 2 usage; 3 DISCARD (no partial work) |
| `interface-check WORKSPACE TASK BASE` | Diff touched a file another task consumes (plan.json). Wired post-commit as an advisory ledger entry (`interface_touched`) | exit 0 clean; 1 interface changed; 2 usage |
| `final-gate WORKSPACE TOTAL_TASKS` | Pre-closing: all complete + no unresolved verdicts + no blocking parked (structured `PARKED_SEVERITY` Critical/Important — M7, never prose) + tests/analyze green (skipped when the tree is unchanged since the last green checkpoint — HEAD equal to the newest `commit` OR `integrated` ledger sha, so the skip also fires after a wave's merge commit) + no pending worktree (`worktree_alloc` without `worktree_release`), no leftover `task/<N>` branch, no newest `integration_failed` after completion (parallel run) | exit 0 ready; 1 blockers; 2 usage |
| `doc-check [REPO]` | Deterministic gate: pipeline files changed → READMEs must also change | exit 0 OK; 1 violation; 2 usage |
| `parse-review LOGFILE OUTFILE` (two-model) | Deterministic parser: reads the revisor's JSONL event log, extracts the structured verdict, writes it to a JSON file. Run after the log lands. Tolerant of the recurring revisor JSON defects — prose/fences, a trailing comma, invalid backslash escapes, and unescaped content quotes inside string values (repaired; regex fallback for the verdict) — so a malformed reply never blocks the run | exit 0 verdict written; 1 no verdict / read error / write error; 2 usage |

When a dispatch is interrupted — the hard `opencode-timed` CLI timeout kills a
provider-stalled run and returns `rc=124` — `red-gate` ledgers a terminal
`dispatch_interrupted` entry instead of leaving only a `red_check` line, and
`run-pipeline` captures the failing gate's exit code (`cmd || rc=$?`) so it
reports `BLOCKED` rather than dying as a silent `EXIT`. A re-run resumes at the
same task.

All scripts honor `FLUTTER_BIN`, `DART_BIN`, `GIT_BIN`, `RTK_BIN`,
`DISPATCH_BIN`, `OPENCODE_BIN` env overrides. `cmd` also respects `RTK_ENABLED=0`
(passthrough) and `RTK_BIN` (binary override); if RTK has no filter/wrapper for a
command it passes the full output through — nothing is lost.
`red-gate`/`green-gate` dispatch operador/revisor on success. Tests live in
`skills/flutter-app-pipeline/tests/` (flutter scripts) and
`skills/two-model-sdd-pipeline/tests/` (router + cmd runner + dispatch + gates),
run with `run-tests.sh` (`python3 -m unittest discover`).

## 7. Ordering invariants (do not violate)

- **Commands are scripted and RTK-compressed:** every LLM-invoked command
  line (test runs, analysis, git ops) runs through
  `scripts/cmd` — the generic runner saves the FULL output to a workspace
  file and prints the RTK-compressed view on stdout. Raw command output
  never enters an LLM context window. Deterministic gates keep reading full
  files, so nothing a verdict depends on (`red-form-check`'s machine-readable
  evidence, escalation packages) is ever compressed.
  `RTK_ENABLED=0` disables compression (passthrough); `RTK_BIN` overrides
  the binary. `flutter test`/`flutter analyze` use the `rtk test`/`rtk err`
  wrapper derivation from the full file — the verdict always comes from the
  raw run (RTK wrappers mask child exit codes, spike-verified).
- **Dispatch is script-owned (ADR-0001):** red-gate dispatches Agente operador on
  a scaffolded brief; green-gate dispatches Agente revisor after commit;
  `run-pipeline` drives the whole branch. The interactive session is never
  a link in the dispatch chain.
- **Batching is a plan-authoring decision, never a runtime one:** a task may
  cover several same-shape, mutually independent edits — every file in
  `touches`, every observable behavior in `acceptance`. The pipeline runs one brief / operador dispatch /
  commit / revisor / ledger entry per task, so batching needs no script
  change. Never batch a task whose files an earlier batch member changes
  (a batched RED would go stale against a mid-batch interface change).
  The revisor checks a batched brief's diff file by file.
- **Parallel execution is plan-derived and script-owned (ADR-0010/0011/0012):**
  `depends_on` + `touches` are scheduling-authoritative; `wave-next` computes
  each wave (plan + ledger, never an LLM judgment), `worktree-alloc` gives every
  task its own git worktree + `task/<N>` branch and per-worktree ledger shard,
  `task-run` drives the task inside that worktree, and `integrate` folds the
  wave back in ascending id order running the **full suite after each individual
  merge** (aborting only the failing merge), then `ledger-merge` folds the shard.
  `--max-parallel` defaults to 2; `--max-parallel 1` is the serial path,
  behavior-preserving (advances via `route-next` instead of `first_incomplete`;
  the ledger sequence is asserted by a regression test) — no worktrees, no
  `integrate`. Integration failure is a **bounded blocker**: exactly one
  re-attempt in the task's existing worktree (meaningful for an un-approved
  task; a no-op for a conflict on an approved one), then a human block — never
  an unbounded self-heal loop.
- **Operador owns the RED/GREEN loop (ADR-0007, superseding ADR-0002):** it
  authors RED tests, runs them saving the machine-readable output, declares and
  confirms the expected reason, then implements and runs them green. It may run
  test/analyze/format commands but never git. Script CEO validates the saved RED
  form with `red-form-check` and decides the authoritative gate (full suite →
  analyze) by exit code — unbounded retries until green; only TEST_DEFECT
  escalates to Agente diretor.
- **Revisor reviews compiler-approved code only (Item 2):** never
  runs or re-runs test/analyze; scope is design, architecture, spec
  compliance (incl. spec-refs alignment), interface discipline, and
  test-vs-acceptance fit. Returns a structured JSON verdict. It is the sole
  independent semantic guarantee that the tests encode the acceptance; weak or
  vacuous tests are SEND_BACK findings.
- **No knowledge graph:** no stage builds, updates, or queries a code graph.
  Briefs are scaffolded from plan tasks; the revisor reviews brief + diff only.
- **Gates are exit codes:** never judge "did the test fail for the expected
  reason" or "are tests green" by reading output — run the gate script and read
  its exit code. `red-form-check` additionally validates the operador's saved
  machine-readable RED (suite loaded, ≥1 test executed, failed as
  assertion/runtime) before green is approved.
- **Docs describe implemented behavior:** skill/integration docs must match the
  scripts — no `expected_red` step (ADR-0007) and no `green-gate` format gate
  (M8); stale claims are corrected in the same change as the code.
- **Routing is scripted:** after every review outcome (and every earlier
  ledgered transition) run `route-next` and execute its emitted action — the
  LLM never decides "APPROVED → next task" or "SEND_BACK → corrective" by
  reasoning. SEND_BACK → `CORRECTIVE` (diretor appends a task, same operador
  resumes); ESCALATE → `ARBITRATE` (diretor rules). An approved corrective
  reconciles its parent (`corrects: N`): the parent's last review becomes
  APPROVED and the parent is marked complete, so the loop never re-emits
  `CORRECTIVE` and `final-gate` sees all tasks closed.
- **Cache-aware calls:** operador and revisor retain their sessions WITHIN a task until
  approval (fix/correction rounds resume via `--continue --session`; the
  provider cache-bills the stable prefix — system + plan + brief); when the task changes, dispatch fresh. Agente diretor is punctual: each corrective/arbitrate episode resumes only within that episode with script-controlled context, and closing is one curated-package dispatch — no cross-branch persistent session.
- **Review pre-gates are exit codes:** `keep-discard` is the C2 scope gate run
  before every commit (out-of-scope → `scope_violation` → `ARBITRATE`; newly
  authored tests exempt, modified committed tests are tampering);
  `interface-check` is wired post-commit as the advisory `interface_touched`
  ledger entry; `final-gate` verifies all tasks complete, no unresolved
  verdicts, no blocking parked finding (structured `PARKED_SEVERITY`), and
  tests/analyze green (skipped when the tree is unchanged since the last green
  commit) before closing.
- **Ledger via script:** the ledger is appended through `ledger-append`, never
  free-handed as prose.
- **Workers never commit:** only Script CEO (via `green-gate` or the
  orchestrator) commits.
- **Observability without pollution:** operador/revisor progress shows in the
  live dispatch digest plus workspace logs
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
  pipeline test suite. `check-superpowers` reports a `node_modules/superpowers`
  npm install with a specific message (the sync scripts need a git working
  copy, not a tarball), rather than a misleading "not installed".
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
| Strategic (D, B-side judgment) | `two-model-reviewer` | `opencode-go/deepseek-v4.1-flash` |
| Operational (C) | `two-model-coder` | `opencode-go/deepseek-v4.1-flash` |

No `variants` block is used; the model is selected by the agent definition.
The repo mirrors these definitions under `agent/` for versioning.

On Git Bash for Windows, `pipeline-workspace` and `cmd` normalize native
Windows paths through their shared `lib/path-normalize.sh` helper before
passing them to POSIX filesystem tools. This keeps workspaces and full command
logs inside the selected checkout, including paths with spaces, instead of
asking MSYS `mkdir` to create a literal `C:` directory.

## 12. Repository layout

```
README.txt                        <- this repo's human-facing readme
README-LLM.md                     <- this file (agent-facing)
CONTEXT.md                        <- resolved glossary (architectural path)
agent/                            <- mirrored tier agent definitions (coder + variants/controller/reviewer/task-generator/flutter-pipeline), kept byte-identical to the live `~/.config/opencode/agent/` definitions
docs/superpowers/adr/             <- accepted architecture decisions
docs/superpowers/specs/           <- branch design specs
docs/superpowers/plans/           <- implementation plans
skills/flutter-app-pipeline/SKILL.md
skills/flutter-app-pipeline/scripts/     <- deterministic scripts (bash + python3)
skills/flutter-app-pipeline/tests/       <- python unittest suite (run-tests.sh)
skills/two-model-sdd-pipeline/SKILL.md
skills/two-model-sdd-pipeline/scripts/   <- run-pipeline, brief-scaffold, pipeline-workspace, ledger-append, cmd, dispatch,
                                             orchestrator, coder-agent-for, keep-discard, interface-check, run-gates,
                                             review-package, route-next, final-gate, red-gate, coder-gate, red-form-check,
                                             resolve-toolchain, doc-check, parse-review,
                                             task-run, touches-overlap, wave-next, ledger-merge, ledger-migrate,
                                             worktree-alloc, worktree-release, integrate
skills/write-script/SKILL.md      <- deterministic-script conventions (one file per rule family)
skills/skill-scripter/SKILL.md    <- audits a skill/stage for prose decisions that should be scripts
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
   tasks -> `pub-sync` -> Agente estratégico writes the complete `plan.json` + spec (then DONE) ->
   `run-pipeline PLAN_FILE`: the plan is already complete (No EXPAND); per task `brief-scaffold` ->
   `red-gate` (dispatches operador) -> Script CEO gates (RED-form check, task
   tests, full suite, analyze; operador retried until green, never hands back) ->
   `green-gate` (commit + dispatch revisor; `keep-discard` scope gate first)
   -> revisor JSON verdict -> `route-next`. SEND_BACK →
   `CORRECTIVE` (diretor appends task, same operador resumes `--continue --session`);
   ESCALATE → `ARBITRATE` (diretor rules). After all tasks: `final-gate`
   (short-circuit when unchanged) then diretor closing. Push + PR default.
   The router, not the LLM, decides every transition. All command lines go
   through `scripts/cmd`.
4. Non-Flutter work: standard superpowers flow (brainstorming + TDD), no Flutter
   layer.
### Site 1 catalog triage

The Flutter pipeline exposes `template-triage EVIDENCE_FILE CONTEXT_FILE --workspace DIR --output REPORT` for shortlist triage. It requires complete evidence and all Category Skeleton fields, only evaluates `DEVELOPER_DECISION` scoring results, and keeps AUTO_APPROVE/AUTO_REJECT on their existing paths. Jev adopt/reject outcomes are shortlist metadata under calibrated active policy; they never select, clone, install, or download a project template. Off, shadow, unavailable, uncertain, and invalid evidence fall back to the existing developer path with an explicit reason.
