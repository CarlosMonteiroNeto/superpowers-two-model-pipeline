SUPERPOWERS - TWO-MODEL PIPELINE FORK
=====================================

A fork of obra/superpowers (MIT) that turns it into a deterministic,
two-tier development pipeline for AI coding agents, with a Flutter/Dart
layer on top.

WHAT THIS FORK ADDS
-------------------

1. two-model-sdd-pipeline (new skill)
   A hybrid-orchestrated fork of subagent-driven-development. A
   deterministic Orchestrator (scripts + your session) owns state, git
   worktrees, task transitions, test execution, commits, and a JSONL
   ledger. An expensive "Strategic" model handles reasoning (plan,
   just-in-time RED-test briefs, reviews); a cheap "Operational" model
   writes code. Every LLM call is a stateless dispatch fed curated
   context - no agent holds a continuous session across the branch.

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
  resolution, test execution, lint, commit, task routing) are chained into
  deterministic scripts whose verdict is an exit code or a stdout action
  line.
- Every command line is scripted and RTK-compressed. All LLM-invoked
  commands run through scripts/cmd: full output is saved to a workspace
  file (gates and escalation read the file) and the LLM sees the
  RTK-compressed view on stdout. Raw command output never enters an LLM
  context window.
- Cache-aware LLM calls with curated context; same-tier, same-task
  resume is allowed (prefix-cached); fresh dispatch when role or task
  changes. The ledger + git are the source of truth.
- Graphify-before-LLM (Controller-side, lazy): the Controller queries the
  code knowledge graph (graphify explain / path) when writing briefs and
  rebuilds it only when stale. It is no longer chained into the gates.
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

- Graphify (graphifyy): on-device code knowledge graph for the Controller's
  structure queries. Python 3.10+ required:

      python -m pip install graphifyy
      graphify --version

  Graphify is optional (best-effort); RTK_ENABLED=0 disables compression
  and GRAPHIFY_ENABLED=0 disables graphify chains. RTK_BIN / GRAPHIFY_BIN
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
selection with you, writing-plans tasks, then the two-model TDD loop, then
a project-wide review. On the two-tier gate, default to YES: the tiers are
pre-configured locally (two-model-controller / two-model-coder), so only
the test/analyze commands are asked - once per branch. Ask about tiers
only when the pipeline is not installed. After selection, the branch runs
without further approval check-ins. Non-Flutter work follows the standard
superpowers flow without the Flutter layer.

DETERMINISTIC SCRIPTS (no AI involvement)
-----------------------------------------

skills/flutter-app-pipeline/scripts/:
  pkg-score            corrected Quality Score for a pub.dev package
  pub-sync             download + lockfile + version-conflict report
  red-gate             materialize RED tests and verify the failure is
                       the EXPECTED-RED reason (not just any failure)
  green-gate           chain test + analyze + format + commit (one script)
  graphify-regen       rebuild the project knowledge graph
                       (invokes `graphify update <root>` - the real CLI form)
  graphify-package     build the graph for a downloaded dependency
                       (invokes `graphify update <pkg_dir>`)

skills/two-model-sdd-pipeline/scripts/:
  pipeline-workspace   create the per-plan git-ignored workspace
  ledger-append        append one structured JSONL ledger entry
  cmd                  generic command runner: saves FULL output to a file,
                       prints the RTK-compressed view on stdout, returns the
                       command's true exit code (RTK_ENABLED=0 / RTK_BIN)
  run-gates            generic green approval: full suite + analysis via cmd
  review-package       build a review bundle (commits + diff)
  route-next           deterministic router: reads the ledger and emits
                       the next action (BRIEF / RED / CODER / ESCALATE /
                       STRATEGIC / REVIEW / FIX / NEXT / FINAL_REVIEW)
  red-integrity        byte-compare committed tests vs brief RED-TESTS
                       (exit 0 intact; 1 tampered; 2 usage)
  keep-discard         escalation pre-gate: empty diff / out-of-scope
                       files -> DISCARD; else KEEP (exit 0/1/2)
  interface-check      diff touched a file another task consumes
                       (exit 0 clean; 1 interface changed; 2 usage)
  final-gate           pre-holistic: all tasks complete + no unresolved
                       verdicts + no blocking parked + tests/analyze green
                       (exit 0 ready; 1 blockers; 2 usage)

skills/brainstorming/scripts/:
  orient-llm           pre-flight orientation gate: locate and print
                       README-LLM.md (the agent-facing harness reference)
                       before work starts (exit 0 printed; 1 missing; 2 usage)

Every LLM-invoked command line runs through scripts/cmd, so no raw command
output ever enters an LLM context window. Deterministic gates keep reading
full files - nothing a verdict depends on (red-gate's EXPECTED-RED substring,
escalation packages, red-integrity byte-compare) is ever compressed.

Graphify is Controller-side and lazy: pub-sync still indexes each newly
added package (a Controller feed) and the Controller queries the graph
(graphify explain / path) at brief time, rebuilding only when stale. The
eager graphify chains in red-gate and green-gate are gone - those gates
never read the graph, and RTK now covers the context-compression job they
used to aim at. All graphify invocations are best-effort (a failure never
fails a gate) and can be disabled with GRAPHIFY_ENABLED=0.

Routing is scripted too: after every ledgered outcome the Orchestrator
runs `route-next` and executes the action it emits - the LLM never decides
"review passed -> next task" or "failed -> fix round" by reasoning.

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
installed, syncs/installs and asks you to restart OpenCode. On the
reference setup the two tiers use the same model with different reasoning
effort: Strategic = deepseek-v4-flash high, Operational = deepseek-v4-flash
low.

TESTS
-----

The deterministic scripts have python unittest suites:

    skills/flutter-app-pipeline/tests/run-tests.sh
    skills/two-model-sdd-pipeline/tests/run-tests.sh

REPOSITORY LAYOUT
-----------------

README.txt            this file (for people)
README-LLM.md         harness reference (for LLM agents)
skills/               the skills (SKILL.md per skill)
  flutter-app-pipeline/   the Flutter layer + scripts + tests
  two-model-sdd-pipeline/ the generic two-tier engine + scripts

LICENSE
-------

MIT - see LICENSE file for details. Upstream: https://github.com/obra/superpowers
