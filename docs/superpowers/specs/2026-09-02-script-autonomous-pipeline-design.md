# Script-Autonomous Two-Model Pipeline — Design

- **Date:** 2026-09-02
- **Status:** Approved in brainstorming; implementation pending
- **Scope:** this branch only. Vocabulary and long-lived decisions live in
  `CONTEXT.md` and `docs/superpowers/adr/` (ADRs 0001–0005) — referenced, not
  restated.

## 1. Problem

The per-task loop is main-agent-driven: the Orchestrator session runs gates,
dispatches Coder/Reviewer via the `task` tool, reads `route-next`, and loops.
The developer wants the deterministic layer (Script A) to own the entire
per-task flow — dispatch, gates, routing — so the interactive session (B) is
out of the hot path, its context stays clean, and subagent work is observable
without polluting session history. Seven change requests were mapped during
brainstorming (items 1–7); all are resolved and recorded in `CONTEXT.md`.

## 2. Target architecture

```
B (this session, strategist)  ──writes plan/brief+RED test──►  Script A (orchestrator)
        ▲                                                            │ red-gate (verify RED)
        │                                                            ▼
        │  only script stdout enters B's context          dispatch C (opencode run, fresh)
        │                                                            │ C writes code (write-only)
        │  observability: Script A tees full C/D           task tests → full suite → analyze
        │  activity to <ws>/*.log (tail freely,            ▲           │ any fail → resume C (4 attempts)
        │  never pollutes session history)                 └───────────┘
        │                                                            │ green-gate (commit + graphify-update)
        │                                                            ▼
        │                                                    dispatch D (opencode run, fresh)
        │                                                            │ D returns structured JSON verdict
        │                                                            ▼
        │                                                     route-next (deterministic)
        └────────────────────── outcome → B writes next brief / corrective brief / arbitration
```

### Actors

| Actor | Tier / kind | Responsibility |
|---|---|---|
| Script A | deterministic bash | gates, test/analyze decisions, dispatch C/D, routing, commits, graph update, ledger, token-kill |
| B | main session (strategist) | plan.json, task breakdown, briefs + RED tests, corrective briefs, TEST_DEFECT arbitration, final holistic review (fresh `/new` session) |
| C | Operational (`opencode-go/mimo-v2.5`) | write-only implementation against brief + RED tests |
| D | Strategic (`opencode-go/deepseek-v4-flash`) | architecture/design review of compiler-approved code; structured JSON verdict |

### Flow (per task, autonomous once B hands over the brief)

1. **BRIEF** — B writes `<ws>/task-N-brief.md` (statement, exact values, RED
   tests, `EXPECTED-RED:`, out-of-scope). Script A stores it.
2. **RED** — Script A runs `red-gate`: materializes tests, verifies expected
   failure + expected reason. Defective brief → `ARBITRATE` to B. (Item 1, 6 —
   EXPECTED-RED already works, unchanged.)
3. **CODER** — Script A runs `dispatch` (fresh) for C with the filled coder
   template. C writes code only; never runs tests (Item: write-only).
4. **GATES** — Script A runs task tests → full suite → `flutter analyze`, each
   decision by exit code inside the script (Item 2). Any failure → resume C via
   `--continue --session` with token-killed failure output; budget round 1 + 3
   fixes, then `ARBITRATE`.
5. **GREEN** — all gates pass → `green-gate` commits, ledger `commit`,
   `graphify-update` (post-commit only — ADR-0004).
6. **REVIEW** — Script A builds the review package (`review-package` BASE HEAD),
   runs `graphify-subgraph` for `<ws>/task-N-interfaces.md`, dispatches D fresh
   with the filled reviewer template. D returns JSON: `APPROVED` / `SEND_BACK` /
   `ESCALATE` + findings + minors (Item 3; D never runs test/analyze — Item 2).
7. **ROUTE** — Script A ledger-appends `review_outcome`, runs `route-next`
   (Item 7):
   - `APPROVED` → `NEXT N+1` (minors → PARKED, documented by B; no fix loop)
   - `SEND_BACK` → `CORRECTIVE` → B writes a corrective brief → resume C
     (correction cycle)
   - `ESCALATE` → `ARBITRATE` → B validates brief/test viability
8. **FINAL_REVIEW** — all tasks done → Script A emits `FINAL_REVIEW`; B starts a
   fresh `/new` session, fed only the original plan + consolidated diff + ledger
   (Item 5). If approved → README update + push + deploy (Item 5, per developer).

### Dispatch mechanism (ADR-0001)

New `scripts/dispatch`:

```
dispatch --agent <two-model-coder|two-model-reviewer> --task N [--continue SESSION] \
         --brief <ws>/task-N-brief.md --prompt-file <filled-template> \
         --log <ws>/task-N-coder.log
```

Runs `opencode run --agent <def> --dir <worktree> --file <brief> --format json
--prompt <filled>`; tees the JSON event stream to the log; captures the session
ID for `--continue --session` on the next round. D's verdict is parsed from its
JSON reply and written to `<ws>/task-N-review.json`.

### The `orchestrator` driver (sequencer)

`orchestrator <ws> TASK [TOTAL]` is the thin driver B invokes once per task. It
executes the route-next actions in sequence and owns the transitions between
steps; the gates own their respective dispatch calls:

1. `route-next` → on `BRIEF`/`CORRECTIVE`, exit and tell B what to write.
2. On a brief present: run `red-gate` (which dispatches C on success).
3. Wait for C's report (`<ws>/task-N-report.md`), run task tests → full suite →
   analyze; on failure resume C (`dispatch --continue`), up to 4 attempts.
4. On all green: run `green-gate` (which commits, runs `graphify-update`, then
   dispatches D on success).
5. Parse `<ws>/task-N-review.json`, ledger `review_outcome`, run `route-next`,
   print the outcome for B, exit. B writes the next/corrective brief and re-invokes.

### Subagent headers (developer question resolved)

Headers are fixed templates + deterministically-resolved per-task values:

| Placeholder | Source (all deterministic) |
|---|---|
| `[WORKTREE_PATH]` | ledger gate entry / worktree root |
| `[BRIEF_FILE]` | `<ws>/task-N-brief.md` (B wrote it) |
| `[GLOBAL_CONSTRAINTS]` | verbatim from `plan.json` (B wrote it) |
| `[INTERFACES_FILE]` | `graphify-subgraph` output (replaces main-agent gathering) |
| `[DIFF_FILE]` / base/head | `review-package` output |
| round-2 diff / failing output | `<ws>/task-N-diff.txt`, `<ws>/task-N-test-out.txt` |
| `[REPORT_FILE]` | `<ws>/task-N-report.md` |
| system prompt / model | agent definitions (`two-model-coder.md`, `two-model-reviewer.md`) |

B passes only the brief body + workspace/task IDs to Script A.

### RTK / Token Killer (ADR-0005)

- `cmd` filter map extended: flutter test → `rtk test`, flutter analyze →
  `rtk err`, git diff → `rtk diff`, JSON → `rtk json`.
- `token-kill`: minify error logs, strip comments/whitespace from source payloads
  to C/D, trim D's JSON report. Full output always saved; only LLM-facing stdout
  compressed. `RTK_ENABLED=0` / `RTK_BIN` honored.

## 3. File changes

| File | Change |
|---|---|
| `~/.config/opencode/agent/two-model-coder.md` | write-only framing; explicit permissions (edit/read/glob/grep; no test-running) |
| `~/.config/opencode/agent/two-model-reviewer.md` | **NEW** — Strategic, read-only (edit deny; bash limited to read-only git/log), JSON output |
| `~/.config/opencode/agent/two-model-controller.md` | retired or narrowed (final-review fallback) |
| `~/.config/opencode/agent/flutter-pipeline.md` | fix stale graphify-chain claim (line 20); describe script-autonomous flow |
| `skills/two-model-sdd-pipeline/SKILL.md` | rewrite roles + per-task loop + ledger types (`CORRECTIVE`, `ARBITRATE`; drop `STRATEGIC`) |
| `skills/flutter-app-pipeline/SKILL.md` | flow updates (red-gate→C, green-gate→D, graphify timing, RTK wiring) |
| `scripts/cmd` | RTK filter map extension |
| `scripts/route-next` | `CORRECTIVE`/`ARBITRATE` actions; drop `STRATEGIC`; budget 4 attempts |
| `scripts/red-gate` | chain C dispatch on success |
| `scripts/green-gate` | analyze + commit + `graphify-update` + D dispatch |
| `scripts/dispatch` | **NEW** — headless `opencode run` wrapper |
| `scripts/orchestrator` | **NEW** — thin driver executing route-next actions |
| `scripts/token-kill` | **NEW** — RTK minify helpers |
| `scripts/graphify-update` | **NEW** — post-commit graph rebuild |
| `scripts/graphify-subgraph` | **NEW** — affected-dependency subgraph extraction |
| `skills/.../coder-prompt.md`, `reviewer-prompt.md` | rewrite (write-only C; JSON-verdict D; no test/analyze in D) |
| `skills/.../strategic-coder-prompt.md` | delete |
| `skills/.../controller-brief-prompt.md` | convert to B-side guidance (no dispatch template) |
| `README.txt`, `README-LLM.md` | doc-check gate: pipeline changes require updates; fix stale variant table |
| `tests/*` | update `test_cmd_runner`, `test_route_next`, `test_gates`; new `test_dispatch`, `test_subgraph`, `test_token_kill` |

## 4. Spikes (verify first, before building)

1. `opencode run --agent <subagent> --format json` headless viability; `--continue
   --session` resume semantics; `--auto` vs explicit permissions. *(Linchpin —
   everything depends on this.)*
2. `rtk test` / `rtk err` on Windows for Flutter output shape.
3. Graphify `explain`/`path` output shape for subgraph extraction.
4. Invoking `opencode` from inside bash scripts on Windows (Git Bash path,
   `OPENCODE_GIT_BASH_PATH`).

## 5. Out of scope

- Changing EXPECTED-RED / red-gate expected-reason semantics (works as-is; Item 6).
- Deploy mechanics beyond "README update + push" (deploy tooling is the
  developer's; pipeline hands off after final review approval).
- Non-Flutter language support (generic engine keeps `run-gates`; Flutter keeps
  `green-gate`).