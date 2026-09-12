SUPERPOWERS - TWO-MODEL PIPELINE FORK
=====================================

A fork of obra/superpowers (MIT) that turns it into a deterministic,
two-tier development pipeline for AI coding agents, with a Flutter/Dart
layer on top.

WHAT THIS FORK ADDS
-------------------

1. two-model-sdd-pipeline (new skill)
   A script-autonomous fork of subagent-driven-development. A deterministic
   "Script CEO" (modular bash, invokable anywhere as `scripts/run-pipeline
   PLAN_FILE`) owns the per-task loop: gates, test/analyze
   decisions, subagent dispatch (headless `opencode run --agent`), routing,
   and commits. The interactive session (Agente estratégico) writes
   the spec and a complete `plan.json` (acceptance; no `expected_red`),
   then DONE. A cheap "Operational"
   Agente operador writes RED tests + code; an expensive "Strategic"
   Agente revisor reviews compiler-approved code (plus test-vs-acceptance
   fit) and returns a structured JSON verdict. A "Strategic" Agente diretor
   is a punctual task owner: it appends corrective tasks, rules arbitration,
   and closes the branch (No EXPAND).
   Every LLM call is fed curated context - no agent holds a continuous
   session across the branch (operador/revisor retain within-task
   sessions for fix/correction loops; the diretor is punctual, one episode
   at a time).

2. brainstorming enrichment
   grill-with-docs merged into brainstorming, plus Incremental
   Persistence: resolved terms and decisions are written to CONTEXT.md as
   they resolve; ADRs require three simultaneous gates; fact-finding
   questions stay open-ended; the approaches step presents exactly 3
   options plus a free-form custom answer.

3. flutter-app-pipeline (new skill, layered on top)
   A Flutter/Dart specialization that adds package research with a
   corrected pub.dev/GitHub Quality Score, deterministic Flutter scripts,
   and the RTK-compression ordering rule. It
   delegates the per-task implementation loop back to two-model-sdd-pipeline.

PRINCIPLES
----------

- LLMs reason; scripts decide. Mechanical steps (download, dependency
  resolution, test execution, lint, commit, task routing, subagent
  dispatch) are chained into deterministic scripts whose verdict is an
  exit code or a stdout action line.
- Script-autonomous dispatch (ADR-0001): red-gate dispatches Agente operador on
  a scaffolded brief (then coder-gate retries it until green, RED-form
  check before commit); green-gate commits and dispatches Agente revisor;
  route-next + the orchestrator driver route every transition.
  The interactive session is never a link in the dispatch chain.
- Agente operador owns its RED/GREEN loop (ADR-0007, superseding ADR-0002): it
  authors RED tests, runs them and saves the machine-readable output, declares
  and confirms the expected reason, then implements and runs them green. It may
  run test/analyze/format, never git. Script CEO checks the RED form with
  `red-form-check` and decides the authoritative
  test/analyze gate by exit code and
  feeds failures back (unbounded retries until green; only TEST_DEFECT
  escalates to Agente diretor). The revisor is the sole independent semantic
  guarantee that the tests encode the acceptance.
- Agente revisor reviews compiler-approved code only (Item 2) and returns a
  structured JSON verdict; minor findings are PARKED for closing, never fix
  loops.
- Corrective tasks append to plan.json (`corrects: N`); `brief-scaffold`
  builds the corrective brief and the SAME operador session resumes until
  green. On resume (dispatch --continue --session),
  the corrective-round prompt tells the resumed model the brief has
  CHANGED and to re-read it fully.
- Batching is a plan-authoring decision, never a runtime one: a task may
  cover several same-shape, mutually independent edits (every file in
  touches, every behavior in acceptance). The pipeline
  runs one brief/operador/commit/revisor/ledger entry per task, so no
  script changes; never batch a task whose files an earlier batch member
  changes (stale RED vs a mid-batch interface change). The revisor checks
  a batched brief's diff file by file.
- Every command line is scripted and RTK-compressed. All LLM-invoked
  commands run through scripts/cmd: full output is saved to a workspace
  file (gates and escalation read the file) and the LLM sees the
  RTK-compressed view on stdout. flutter test/analyze compress via the
  rtk test/rtk err wrappers (verdict from the raw run - wrappers mask
  child exit codes).
- Cache-aware LLM calls with curated context; within-task resume
  (--continue --session) is allowed (prefix-cached); fresh dispatch when
  the task changes (ADR-0003). The ledger + git are the source of truth.
- No knowledge graph: no stage builds, updates, or queries a code graph.
  Briefs are scaffolded from plan tasks; reviews read the brief + diff only.
- Observability without pollution: operador/revisor progress shows in the
  live dispatch digest and workspace logs
  (task-N-coder.log, task-N-reviewer.log) you can tail; headless sessions
  never pollute the main session's history. Script CEO reads only curated
  script outputs (OUTCOME lines, the ledger, and the parsed verdict JSON)
  - never raw dispatch logs or full gate reports.
- No approval after decisions: approval happens at the gate (once per
  branch) and at solution selection; from Phase 2c onward the branch runs
  to completion without check-ins. The ledger is the compaction-safe state
  checkpoint.
- All responses and internal artifacts are in English; only the software
  UI uses the developer's language.

TOOLS (one-time setup)
----------------------

- RTK (Rust Token Killer): CLI proxy that compresses command output before
  it reaches the LLM context. Install and enable the OpenCode plugin:

      winget install --id rtk-ai.rtk
      rtk init -g --opencode     # installs ~/.config/opencode/plugins/rtk.ts
      # restart OpenCode; verify: rtk --version && rtk gain

  RTK_ENABLED=0 disables compression; RTK_BIN overrides the binary.

INSTALL (OpenCode)
------------------

Make OpenCode load this fork instead of the upstream superpowers package.

In ~/.config/opencode/package.json:

    "dependencies": {
      "superpowers": "github:CarlosMonteiroNeto/superpowers-two-model-pipeline"
    }

Then, from ~/.config/opencode:

    npm install

The plugin stays registered as "~/.config/opencode/node_modules/superpowers"
in opencode.json. Restart OpenCode after installing.

To use the pipeline automatically in every session, set a default agent
that runs the pipeline (see the harness doc for the agent prompt):

    "default_agent": "flutter-pipeline"

USAGE
-----

Start a session and describe the work. For a Flutter/Dart app, the
flutter-app-pipeline runs end to end: requirements (brainstorming +
grill-with-docs + Category Skeleton), research + pkg-score for every
candidate package, then a project-level template stage (template search for
  the specific category, template scoring, clone → gap analysis),
selection with you, writing-plans tasks, then the script-autonomous
two-model TDD loop, then a project-wide review. On the two-tier gate,
default to YES: the tiers are pre-configured locally (two-model-coder /
two-model-reviewer), so only the test/analyze commands are asked - once
per branch. Ask about tiers only when the pipeline is not installed.
After selection, the branch runs without further approval check-ins;
you write the briefs and read script outputs. Non-Flutter work follows
the standard superpowers flow without the Flutter layer.

DETERMINISTIC SCRIPTS (no AI involvement)
-----------------------------------------

skills/flutter-app-pipeline/scripts/:
  pkg-score            corrected Quality Score for a pub.dev package
  template-search      search GitHub for project templates in a category
                       (stars descending, 3-AUTO_APPROVE stop; fallback to
                       generic ≥70 with the specific 50–69 group)
  template-score       score a project template candidate (stars, recency,
                       Flutter/Dart readiness, issue ratio, sustained interest,
                       license, README)
  pub-sync             download + lockfile + version-conflict report
  red-gate             verify the scaffolded brief, dispatch Agente operador
                       on success (then chains into coder-gate, which owns
                       the retry loop: RED-form check (`red-form-check`) + commit
                       + revisor dispatch)
  green-gate           chain test + analyze + format + commit (RED form
                         already verified), then review package + revisor dispatch.
                         On commit appends the ledger `commit` entry
                         (task from -t when given; ledger-append resolved
                         from the two-model scripts dir)

skills/two-model-sdd-pipeline/scripts/:
  run-pipeline         top-level Script CEO driver: PLAN_FILE [TOTAL]
                       [--no-push]; loops route-next -> execute to closing
                       -> push+PR. Invokable anywhere, no estrategista loop
  pipeline-workspace   create the per-plan git-ignored workspace (+ working
                       plan.json copy)
  brief-scaffold       scaffold task briefs from plan tasks (statement,
                       acceptance, spec_refs, reason-declaration and
                       machine-readable RED instructions). Rejects test-like
                       touches (tests are changed-minus-touches). No LLM
  resolve-toolchain    one-time-per-branch ecosystem detection: inspects the
                       project for a known marker (pubspec.yaml, Cargo.toml,
                       go.mod, package.json, pyproject.toml, requirements.txt),
                       creates the workspace and ledgers TEST_CMD/ANALYZE_CMD
                       unconditionally (exit 1/2 = ask once, then ledger
                       manually)
  ledger-append        append one structured JSONL ledger entry
  red-gate             per-task kickoff: verify the scaffolded brief,
                       dispatch Agente operador, chain coder-gate
  coder-gate           owns every retry after the first dispatch: runs the gate
                       check-only first (Flutter) + auto-format before the
                       check, ledgers coder_round, builds the fix prompt
                       (prior diff + gate/annex reports + brief) + resumes the
                       operador's own session with --continue on failure;
                       unbounded until green; validates the saved RED form with
                       red-form-check before commit; stops on TEST_DEFECT ->
                       ARBITRATE (Agente diretor rules)
  red-form-check       classify the operador's saved machine-readable RED
                       evidence (suite loaded, >=1 test executed, failed as
                       assertion/runtime; compile/load red -> exit 1)
  cmd                  generic command runner: saves FULL output to a file,
                       prints the RTK-compressed view on stdout, returns the
                       command's true exit code (flutter test/analyze via
                       rtk test/err wrappers; RTK_ENABLED=0 / RTK_BIN)
  dispatch             headless subagent launcher: opencode run --agent,
                       JSON stream teed to a workspace log + live progress
                       digest on stdout, session id
                       recorded for resume (--continue --session). The brief
                       is passed as a positional (auto-attach; never --file);
                       on --continue (corrective round) the prompt explicitly
                       tells the resumed model the brief has CHANGED and to
                       re-read it fully; exit 3 when the targeted agent is
                       not mode: all
  session-clean        manual cleanup: deletes the opencode sessions a task
                       recorded (task-N-*-session.txt); never auto-run -
                       sessions are kept for resume/debugging
  orchestrator         thin per-task driver: executes route-next actions,
                       prints OUTCOME for the runner
  token-kill           RTK minification of error logs / source / JSON
                       reports (lossless fallback)
  run-gates            generic green approval: full suite + analysis via cmd
  review-package       build a review bundle (commits + diff); with a TASK
                       arg, inlines the task brief so the
                       revisor gets it in the single package file
  route-next           deterministic router: reads the ledger and emits
                       the next action (BRIEF / RED / CODER / REVIEW /
                       CORRECTIVE / ARBITRATE / NEXT / FINAL_REVIEW)
  red-integrity        hash-compare tests vs a snapshot when one exists
                       (exit 0 intact; 1 weakened; 2 usage)
  keep-discard         escalation pre-gate: empty diff / out-of-scope
                       files -> DISCARD; else KEEP (exit 0/1/2)
  interface-check      diff touched a file another task consumes
                       (exit 0 clean; 1 interface changed; 2 usage)
  final-gate           pre-closing: all tasks complete + no unresolved
                       verdicts + no blocking parked + tests/analyze green
                       (skipped when the tree is unchanged since the last
                       green commit; exit 0 ready; 1 blockers; 2 usage)
  doc-check            pipeline files changed -> READMEs must change too
                       (exit 0 OK; 1 violation; 2 usage)
  parse-review         deterministic parser for the revisor's verdict:
                       reads JSONL event log, extracts structured verdict,
                       writes JSON file (exit 0 verdict written; 1 no
                       verdict / read error / write error; 2 usage).
                       Run by Script CEO after the log lands.

skills/brainstorming/scripts/:
  orient-llm           pre-flight orientation gate: locate and print
                       README-LLM.md (the agent-facing harness reference)
                       before work starts (exit 0 printed; 1 missing; 2 usage)

Every LLM-invoked command line runs through scripts/cmd, so no raw command
output ever enters an LLM context window. Deterministic gates keep reading
full files - nothing a verdict depends on (red-form-check's machine-readable
evidence, escalation packages, red-integrity byte-compare) is ever compressed.

Dispatch is script-owned too: red-gate dispatches Agente operador on a
scaffolded brief (then coder-gate retries it until green, validates the RED
form);
green-gate commits,
builds the review package, and dispatches Agente revisor. The
revisor reviews compiler-approved code only (plus test-vs-acceptance fit)
and returns a structured JSON
verdict; minor findings are PARKED for closing, never fix loops.
Agente operador owns its RED/GREEN loop: it runs its RED tests, saves the
machine-readable output and declares the expected reason, then implements and
runs green; Script CEO validates the RED form and
runs the authoritative task tests ->
full suite -> analyze, feeding failures back (unbounded retries until
green; only TEST_DEFECT escalates to Agente diretor). The revisor is the
sole independent semantic guarantee of test-vs-acceptance fit.

Routing is scripted too: after every ledgered outcome Script CEO runs
`route-next` and executes the action it emits - the LLM never decides
"review passed -> next task" or "failed -> corrective" by reasoning.

KEEPING THE HARNESS IN SYNC
---------------------------

The OpenCode plugin loads from a vendored git checkout of this repository
(~/.config/opencode/vendor/superpowers). To keep it current, run the
self-update scripts under `scripts/` (they auto-detect the checkout dir,
or take it as the first argument):

  scripts/check-superpowers    exit 0 = up to date; 1 = behind; 2 = not installed
  scripts/sync-superpowers     fetch + reset to origin/main + run the pipeline tests
  scripts/install-superpowers  full clone when not installed (refuses to clobber)

The agent runs check-superpowers at session start and, if behind or not
installed, syncs/installs and asks you to restart OpenCode. Tier models
(mirrored under `agent/`, both `mode: all` so they can be dispatched
headlessly): Strategic (Agente diretor / Agente revisor) =
opencode-go/muse-spark-1.3-contributor; Operational (Agente operador) =
opencode-go/deepseek-v4-flash.

TESTS
-----

The deterministic scripts have python unittest suites:

    skills/flutter-app-pipeline/tests/run-tests.sh
    skills/two-model-sdd-pipeline/tests/run-tests.sh

REPOSITORY LAYOUT
-----------------

README.txt            this file (for people)
README-LLM.md         harness reference (for LLM agents)
CONTEXT.md            resolved glossary (architectural path)
agent/                mirrored tier agent definitions
docs/superpowers/     ADRs, specs, plans
skills/               the skills (SKILL.md per skill)
  flutter-app-pipeline/   the Flutter layer + scripts + tests
  two-model-sdd-pipeline/ the generic two-tier engine + scripts

LICENSE
-------

MIT - see LICENSE file for details. Upstream: https://github.com/obra/superpowers