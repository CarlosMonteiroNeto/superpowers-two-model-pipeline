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
   and the Graphify-before-LLM ordering rule. It delegates the per-task
   implementation loop back to two-model-sdd-pipeline.

PRINCIPLES
----------

- LLMs reason; scripts decide. Mechanical steps (download, dependency
  resolution, test execution, lint, commit, graph rebuild) are chained
  into deterministic scripts whose verdict is an exit code.
- Stateless LLM calls with curated context; the ledger + git are the
  source of truth.
- Graphify-before-LLM: newly downloaded or changed code is indexed into a
  knowledge graph before any LLM reads it, minimizing token consumption.
- All responses and internal artifacts are in English; only the software
  UI uses the developer's language.

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
a project-wide review. On the two-tier gate, pick the Strategic and
Operational models and the test/analyze commands (flutter test,
flutter analyze) - once per branch. Non-Flutter work follows the standard
superpowers flow without the Flutter layer.

DETERMINISTIC SCRIPTS (no AI involvement)
-----------------------------------------

skills/flutter-app-pipeline/scripts/:
  pkg-score            corrected Quality Score for a pub.dev package
  pub-sync             download + lockfile + version-conflict report
  red-gate             materialize RED tests and verify expected failure
  green-gate           chain test + analyze + format + commit (one script)
  graphify-regen       rebuild the project knowledge graph
  graphify-package     build the graph for a downloaded dependency

skills/two-model-sdd-pipeline/scripts/:
  pipeline-workspace   create the per-plan git-ignored workspace
  ledger-append        append one structured JSONL ledger entry
  review-package       build a review bundle (commits + diff)

Graphify is chained automatically into the gates at the script->LLM
boundaries: pub-sync indexes each newly added package, red-gate rebuilds
the project graph after RED is verified, green-gate rebuilds it after a
commit. The chains are best-effort (a graphify failure never fails a gate)
and can be disabled with GRAPHIFY_ENABLED=0.

TESTS
-----

The deterministic scripts have a python unittest suite:

    skills/flutter-app-pipeline/tests/run-tests.sh

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