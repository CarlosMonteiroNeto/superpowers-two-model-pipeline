SUPERPOWERS - TWO-MODEL PIPELINE FORK
=====================================

A fork of obra/superpowers (MIT) that turns it into a deterministic,
two-tier development pipeline for AI coding agents, with a Flutter/Dart
layer on top.

WHAT THIS FORK ADDS
-------------------

1. two-model-sdd-pipeline (new skill)
   A script-autonomous fork of subagent-driven-development. A deterministic
   "Script A" (modular bash) owns the per-task loop: gates, test/analyze
   decisions, subagent dispatch (headless `opencode run --agent`), routing,
   commits, and graph maintenance. The interactive session (B) is the
   strategist - it writes the plan and per-task briefs + RED tests and
   receives feedback only through script outputs. A cheap "Operational"
   Coder (C) writes code only; an expensive "Strategic" Reviewer (D)
   reviews compiler-approved code and returns a structured JSON verdict.
   Every LLM call is a stateless dispatch fed curated context - no agent
   holds a continuous session across the branch (C/D retain within-task
   sessions for fix/correction loops).

2. brainstorming enrichment
   grill-with-docs merged into brainstorming, plus Incremental
   Persistence: resolved terms and decisions are written to CONTEXT.md as
   they resolve; ADRs require three simultaneous gates; fact-finding
   questions stay open-ended; the approaches step presents exactly 3
   options plus a free-form custom answer.

3. flutter-app-pipeline (new skill, layered on top)
   A Flutter/Dart specialization that adds package research with a
   corrected pub.dev/GitHub Quality Score, deterministic Flutter scripts,
   and the RTK-compression + Graphify-before-LLM ordering rules. It
   delegates the per-task implementation loop back to two-model-sdd-pipeline.

PRINCIPLES
----------

- LLMs reason; scripts decide. Mechanical steps (download, dependency
  resolution, test execution, lint, commit, task routing, subagent
  dispatch) are chained into deterministic scripts whose verdict is an
  exit code or a stdout action line.
- Script-autonomous dispatch (ADR-0001): red-gate dispatches the Coder on
  RED verified; green-gate commits, updates the graph, and dispatches the
  Reviewer; route-next + the orchestrator driver route every transition.
  The interactive session is never a link in the dispatch chain.
- The Coder is write-only (ADR-0002): it never runs tests or analysis.
  Script A decides task tests -> full suite -> analyze by exit code and
  feeds failures back (budget: round 1 + 3 fixes, then arbitration to B).
- The Reviewer reviews compiler-approved code only (Item 2) and returns a
  structured JSON verdict; minor findings are documented by B, never fix
  loops.
- Every command line is scripted and RTK-compressed. All LLM-invoked
  commands run through scripts/cmd: full output is saved to a workspace
  file (gates and escalation read the file) and the LLM sees the
  RTK-compressed view on stdout. flutter test/analyze compress via the
  rtk test/rtk err wrappers (verdict from the raw run - wrappers mask
  child exit codes).
- Cache-aware LLM calls with curated context; within-task resume
  (--continue --session) is allowed (prefix-cached); fresh dispatch when
  the task changes (ADR-0003). The ledger + git are the source of truth.
- Graphify-before-LLM (post-commit + subgraph, ADR-0004): the graph is
  rebuilt only after an approved task's commit; graphify-subgraph extracts
  the affected-dependency slice for B's next brief and D's review.
- Observability without pollution: C/D progress is teed to workspace logs
  (task-N-coder.log, task-N-reviewer.log) you can tail; headless sessions
  never pollute the main session's history.
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

- Graphify (graphifyy): on-device code knowledge graph for structure
  queries. Python 3.10+ required:

      python -m pip install graphifyy
      graphify --version

  Graphify is optional (best-effort); RTK_ENABLED=0 disables compression
  and GRAPHIFY_ENABLED=0 disables graphify. RTK_BIN / GRAPHIFY_BIN
  override the binaries.

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
grill-with-docs), research + pkg-score for every candidate package,
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
  pub-sync             download + lockfile + version-conflict report
  red-gate             materialize RED tests, verify the failure is the
                       EXPECTED-RED reason, and dispatch the Coder on success
  green-gate           chain test + analyze + format + commit; on commit:
                       graphify-update + review package + Reviewer dispatch
  graphify-update      rebuild the graph post-commit only (ADR-0004)
  graphify-subgraph    extract the affected-dependency subgraph
                       (task-N-interfaces.md) for B's next brief and D
  graphify-regen       rebuild the project knowledge graph
                       (invokes `graphify update <root>` - the real CLI form)
  graphify-package     build the graph for a downloaded dependency
                       (invokes `graphify update <pkg_dir>`)

skills/two-model-sdd-pipeline/scripts/:
  pipeline-workspace   create the per-plan git-ignored workspace
  ledger-append        append one structured JSONL ledger entry
  cmd                  generic command runner: saves FULL output to a file,
                       prints the RTK-compressed view on stdout, returns the
                       command's true exit code (flutter test/analyze via
                       rtk test/err wrappers; RTK_ENABLED=0 / RTK_BIN)
  dispatch             headless subagent launcher: opencode run --agent,
                       JSON stream teed to a workspace log, session id
                       recorded for resume (--continue --session). The brief
                       is passed as a positional (auto-attach; never --file);
                       exit 3 when the targeted agent is not mode: all
  session-clean        deletes the opencode sessions a completed task recorded
                       (task-N-*-session.txt) so headless dispatches don't
                       pollute session history; run by the orchestrator on
                       NEXT / FINAL_REVIEW
  orchestrator         thin per-task driver: executes route-next actions,
                       prints OUTCOME for B
  token-kill           RTK minification of error logs / source / JSON
                       reports (lossless fallback)
  run-gates            generic green approval: full suite + analysis via cmd
  review-package       build a review bundle (commits + diff)
  route-next           deterministic router: reads the ledger and emits
                       the next action (BRIEF / RED / CODER / REVIEW /
                       CORRECTIVE / ARBITRATE / NEXT / FINAL_REVIEW)
  red-integrity        byte-compare committed tests vs brief RED-TESTS
                       (exit 0 intact; 1 tampered; 2 usage)
  keep-discard         escalation pre-gate: empty diff / out-of-scope
                       files -> DISCARD; else KEEP (exit 0/1/2)
  interface-check      diff touched a file another task consumes
                       (exit 0 clean; 1 interface changed; 2 usage)
  final-gate           pre-holistic: all tasks complete + no unresolved
                       verdicts + no blocking parked + tests/analyze green
                       (exit 0 ready; 1 blockers; 2 usage)
  doc-check            pipeline files changed -> READMEs must change too
                       (exit 0 OK; 1 violation; 2 usage)

skills/brainstorming/scripts/:
  orient-llm           pre-flight orientation gate: locate and print
                       README-LLM.md (the agent-facing harness reference)
                       before work starts (exit 0 printed; 1 missing; 2 usage)

Every LLM-invoked command line runs through scripts/cmd, so no raw command
output ever enters an LLM context window. Deterministic gates keep reading
full files - nothing a verdict depends on (red-gate's EXPECTED-RED substring,
escalation packages, red-integrity byte-compare) is ever compressed.

Dispatch is script-owned too: red-gate dispatches the Coder on RED verified;
green-gate commits, runs graphify-update (post-commit only - never per Coder
iteration), builds the review package, and dispatches the Reviewer. The
Reviewer reviews compiler-approved code only and returns a structured JSON
verdict; minor findings are documented by the strategist, never fix loops.
The Coder is write-only: it never runs commands; Script A runs task tests ->
full suite -> analyze and feeds failures back (round 1 + 3 fixes, then
arbitration to the strategist).

Routing is scripted too: after every ledgered outcome Script A runs
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
installed, syncs/installs and asks you to restart OpenCode. Tier models:
Strategic (Reviewer / controller fallback) = deepseek-v4-flash;
Operational (Coder) = mimo-v2.5. Both agent definitions are `mode: all`
so they can be dispatched headlessly; the repo mirrors them under `agent/`.

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