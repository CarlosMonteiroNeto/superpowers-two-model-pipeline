SUPERPOWERS - TWO-MODEL PIPELINE FORK

JEV ADVISORY CLASSIFIER
-----------------------
`skills/two-model-sdd-pipeline/scripts/jev-classify` is a Choice-only
TypeSafe adapter. It reads schema and state JSON and requires `--workspace`
and `--site`. It uses `TYPESAFE_API_KEY` only for live requests and never
prints or stores the key. Exit 0 means all valid answers meet threshold; 1
means low confidence or an open circuit; 2 means invalid local input; 3 means
unavailable setup, transport, or provider data. Cache and circuit records are
isolated by workspace and site. Sites 1-4 default to shadow and active mode
requires a bound calibration report. Site 5 only supports selected-apply.
Jev cannot approve work, route tasks, or write the ledger.

Site 5 plan fusion is advisory during plan authoring. `plan-fusion propose` writes a shadow recommendation report; `plan-fusion apply` requires an explicit strategist selection and writes a separate pre-runtime plan. It never applies a recommendation automatically or changes runtime plan consumers. Keep shadow-agreement evidence separate from outcomes of actually executed fused tasks.

`jev-evaluate REPORTS_JSON LABELS_JSON --output REPORT` reports recommendation
agreement and observed executions separately. It is offline only: it cannot
activate policies or claim counterfactual outcomes.
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
   Interface design is governed by a vendored apple-design skill
   (skills/apple-design/): every UI the pipeline designs or implements must
   apply its principles (response, direct manipulation, interruptibility,
   springs, momentum, materials, typography, reduced motion), and the revisor
   checks them.

4. write-script + skill-scripter (new skills)
   The fork's skill-authoring chain. skill-scripter audits a skill or pipeline
   stage for decisions still settled by prose but mechanically decidable (and
   for dead, duplicated, or unbounded-loop scripts), and writes a scriptization
   plan under docs/superpowers/specs/. write-script then encodes the fork's
   deterministic-script conventions (fixed exit-code family per script type,
   ledger-append as the sole ledger writer, the cmd/dispatch boundaries,
   idempotent re-runs, a resource-profile header, Windows git-bash rules, and
   one unit test per script). writing-skills invokes the chain: draft the skill,
   audit it with skill-scripter, implement approved items with write-script,
   then have the skill reference the script instead of restating the procedure.

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
   CHANGED and to re-read it fully. An approved corrective reconciles its
   parent (parent review becomes APPROVED, parent `task_complete`), so
   `route-next` never re-emits `CORRECTIVE` and `final-gate` sees every
   task closed.
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

The plugin loads from a vendored git checkout
(~/.config/opencode/vendor/superpowers), NOT from node_modules: the
self-update scripts (check-superpowers / sync-superpowers) need a real git
working copy to fetch/reset, which an npm tarball cannot provide. Clone it:

    scripts/install-superpowers          # clones the fork into the vendor dir
    # or, if this fork is already checked out somewhere:
    #   git clone <fork-url> ~/.config/opencode/vendor/superpowers

Then register the plugin path "~/.config/opencode/vendor/superpowers" in
~/.config/opencode/opencode.json and restart OpenCode. If you previously
followed an npm install, remove that dependency and the
node_modules/superpowers tree so there is only one copy - check-superpowers
reports a node_modules install with a specific message instead of silently
saying "not installed".

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
  red-gate             thin shim over the generic two-model red-gate (one
                       implementation: dispatch the lang-selected operador,
                       capture an interrupted dispatch, chain coder-gate)
  green-gate           chain test + analyze (through cmd) + commit
                         (no format gate: coder-gate auto-applies the
                         formatter first), scope gate then review package +
                         revisor dispatch.
                         On commit appends the ledger `commit` entry
                         (task from -t when given; ledger-append resolved
                         from the two-model scripts dir), including the
                         validated `tree=` hash integrate uses to skip a
                         provably redundant post-merge suite (ADR-0013)
  rtk-run              the operador's SCOPED test runner (T1, ADR-0016):
                       accepts only red|test|analyze and delegates to cmd,
                       so its test output is RTK-compressed while the full
                       output lands on disk. `red` writes WS/task-N-red.txt
                       (the path red-form-check reads). The brief OFFERS it
                       rather than mandating it: running the project runner
                       directly and redirecting the evidence is equally fine.
                       Its allowlist entry is an install-independent
                       two-sided wildcard `*flutter-app-pipeline/scripts/
                       rtk-run*` (permission `*` matches any character) that
                       tolerates the shell's wrapping (`& "<path>"`,
                       `bash "<path>"`, bare). The coder def also carries
                       platform-generic read-only allowances; it does NOT
                       allow `bash*`/`python*` (arbitrary execution), because
                       the measured saving comes from the read-only set, and
                       it no longer asks for a RED reason declaration (no
                       script ever read it)

skills/two-model-sdd-pipeline/scripts/:
  run-pipeline         top-level Script CEO driver: PLAN_FILE [TOTAL]
                       [--no-push] [--max-parallel N]; drives the plan
                       serially (N == 1) or in plan-derived waves (N > 1,
                       default 2) to closing -> push+PR. Invokable anywhere,
                       no estrategista loop. Resumable: an already-allocated
                       task worktree (worktree-alloc exit 1, which still
                       reports the paths) is reused, not a blocker
  touches-overlap      declared-touches pairwise disjointness decider (two
                       tasks share a wave only when their touches are
                       disjoint; exit 0 disjoint; 1 overlap; 2 usage)
  wave-next            plan-derived wave scheduler: reads plan.json + the
                       merged ledger, prints FINAL_REVIEW or one RUN <id>
                       per ready, touches-disjoint task (capped at
                       MAX_PARALLEL, default 2); a corrective/open-episode
                       task is emitted alone. Selects fewest-touches-first
                       and prints each deferred task's conflicting files to
                       stderr (WAVE-DEFER), so a collapsed wave is visible
                       (exit 0 emitted/FINAL_REVIEW; 1 WAVE_EMPTY blocked;
                       2 usage)
  ledger-merge         fold per-worktree ledger shards into the integration
                       ledger through the sole writer in ONE batch write
                       (ledger-append --stdin-tsv); skips gate entries and
                       content-identical duplicates; rebuilds partitions
                       (exit 0 merged; 1 the batch failed; 2 usage)
  ledger-migrate       rebuild the per-task ledger partitions; deferred while
                       a wave is in flight (unmatched worktree_alloc)
  worktree-alloc       allocate one git worktree + task/<N> branch for a
                       parallel task, seed its workspace (plan.json + a
                       ledger shard with only the branch gate entry), ledger
                       worktree_alloc, print WORKTREE=/WS= (exit 0 allocated;
                       1 already allocated - still prints the paths; 2 usage).
                       Best-effort warms the new tree (copies pubspec.lock +
                       .dart_tool from the integration tree, then
                       pub get --offline) so the first gate pays no cold
                       resolve/compile; failure degrades to the cold path
  worktree-release     remove a task worktree + branch once the branch tip is
                       an ancestor of the integration HEAD; a never-committed
                       branch (tip == its allocation base) is released only
                       when the shard holds task_complete (an approved no-op
                       task, ADR-0017) - an unapproved never-worked branch is
                       kept as the debug copy; never removes on failure
                       (exit 0 released; 1 not merged/not approved/not found;
                       2 usage)
  task-run             per-task lifecycle extracted from run-pipeline: loops
                       orchestrator and owns the REVIEW/CORRECTIVE/ARBITRATE
                       branches until the task is APPROVED or blocked; runs
                       in the serial root or inside a wave worktree (exit 0
                       complete; 1 blocked/escalated; 2 usage)
  integrate            script-owned integration gate: require every task's
                       shard to hold task_complete (else integration_failed
                       not approved). An approved task that never committed
                       is a no-op: integrated "no-op (no commits)" + shard
                       folded + worktree released, nothing merged or gated
                       (ADR-0017). A wave of >=2 approved tasks is merged
                       first and gated ONCE (S2): green commits once, folds
                       each shard and releases each worktree; red
                       git reset --hard the batch and falls back to the
                       per-merge loop, which IS the bisect (merge one, gate,
                       abort+integration_failed the bad one, keep going). A
                       one-task wave takes the per-merge path, which also
                       carries the ADR-0013 skip (ledger
                       integrate_suite_skipped) when the merge is provably
                       tree-equivalent to the branch tip's gated commit
                       (exit 0 all integrated; 1 >=1 integration_failed;
                       2 usage)
  pipeline-workspace   create the per-plan git-ignored workspace (+ working
                       plan.json copy)
  brief-scaffold       scaffold task briefs from plan tasks (statement,
                       acceptance, spec_refs and
                       machine-readable RED instructions). The RED order
                       OFFERS the rtk-run runner without mandating it and
                       notes that coder-gate owns the full suite (ADR-0016,
                       relaxed). Rejects test-like
                       touches (tests are changed-minus-touches). No LLM
  resolve-toolchain    one-time-per-branch ecosystem detection: inspects the
                       project for a known marker (pubspec.yaml, Cargo.toml,
                       go.mod, package.json, pyproject.toml, requirements.txt),
                       creates the workspace and ledgers TEST_CMD/ANALYZE_CMD
                       unconditionally (exit 1/2 = ask once, then ledger
                       manually)
  ledger-append        append one structured JSONL ledger entry
  red-gate             per-task kickoff: verify the scaffolded brief,
                       dispatch the lang-selected operador variant, chain
                       coder-gate. An interrupted dispatch (opencode-timed
                       rc=124) ledgers a terminal dispatch_interrupted entry;
                       run-pipeline reports BLOCKED instead of a silent EXIT,
                       and a re-run resumes at the same task
  coder-gate           owns the retry loop after the first dispatch: validates
                       the saved RED form with red-form-check, runs the gate
                       (auto-format before the Flutter check), ledgers
                       coder_round, builds the fix prompt (prior diff + gate/
                       annex reports + brief) + resumes the operador's own
                       lang-variant session with --continue on failure;
                       unbounded until green; runs the keep-discard scope gate
                       before commit (scope_violation -> ARBITRATE); wires
                       interface-check post-commit; stops on TEST_DEFECT ->
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
  session-clean        session hygiene: deletes the opencode sessions a task
                       recorded (task-N-*-session.txt, per-agent only; the
                       generic record was removed as a trap). The per-task loop
                       keeps sessions for resume/debugging; a phase launcher
                       runs it with 'all' after run-pipeline returns, and a DB
                       tool (~/.config/opencode/tools/db-maintenance.py
                       prune-sessions) prunes stragglers, so headless sessions
                       never accumulate (opencode.db bloat / freeze guard)
  orchestrator         the single dispatch table: runs route-next, executes
                       the script-owned action (scaffold BRIEF, lang-selected
                       red-gate, coder-gate), prints OUTCOME for the runner
  coder-agent-for      map a resolve-toolchain lang to the operador variant
                       (two-model-coder-{python,node,rust,go}) that can run
                       that ecosystem's tests; shared by the gates
  run-gates            generic green approval: full suite + analysis via cmd
  review-package       build a review bundle (commits + diff); with a TASK
                       arg, inlines the task brief so the
                       revisor gets it in the single package file
  route-next           deterministic router: reads the ledger and emits
                       the next action (BRIEF / RED / CODER / REVIEW /
                       CORRECTIVE / ARBITRATE / NEXT / FINAL_REVIEW).
                       arbitrate_resolved re-scaffolds; a re-escalation is
                       exit 1 "arbitration did not resolve"; scope_violation
                       escalates; task count from JSON
  keep-discard         the C2 scope gate: KEEP when partial work is in
                       touches (newly authored tests exempt); build output
                       (.freezed.dart/.g.dart/.gr.dart/.gen.dart/.mocks.dart)
                       and the tracked plan (docs/superpowers/plans/*.json)
                       are exempt too - codegen is derived, not authored
                       scope (C3, ADR-0014); out-of-scope or tampered ->
                       DISCARD (exit 0/1/2/3)
  interface-check      diff touched a file another task consumes; wired
                       post-commit as the advisory interface_touched entry
                       (exit 0 clean; 1 interface changed; 2 usage)
  final-gate           pre-closing: all tasks complete + no unresolved
                       verdicts + no blocking parked (structured
                       PARKED_SEVERITY) + tests/analyze green (skipped when
                       the tree is unchanged since the last green checkpoint;
                       HEAD equal to the newest commit OR integrated ledger
                       sha, so the skip also fires after a wave merge;
                       exit 0 ready; 1 blockers; 2 usage)
  doc-check            pipeline files changed -> READMEs must change too
                       (exit 0 OK; 1 violation; 2 usage)
  parse-review         deterministic parser for the revisor's verdict:
                       reads JSONL event log, extracts structured verdict,
                       writes JSON file (exit 0 verdict written; 1 no
                       verdict / read error / write error; 2 usage).
                       Tolerant of the revisor's recurring JSON defects
                       (prose/fences, trailing comma, invalid backslash
                       escapes, unescaped content quotes) so a malformed
                       reply never blocks the run.
                       Run by Script CEO after the log lands.

skills/brainstorming/scripts/:
  orient-llm           pre-flight orientation gate: locate and print
                       README-LLM.md (the agent-facing harness reference)
                       before work starts (exit 0 printed; 1 missing; 2 usage)

Every LLM-invoked command line runs through scripts/cmd, so no raw command
output ever enters an LLM context window. Deterministic gates keep reading
full files - nothing a verdict depends on (red-form-check's machine-readable
evidence, escalation packages) is ever compressed.

Skill/integration docs track the implemented behavior: there is no
`expected_red` step (ADR-0007) and no green-gate format check (M8); stale
claims are corrected in the same change as the code.

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

PARALLEL TASK EXECUTION
-----------------------

run-pipeline can run mutually independent tasks concurrently without changing
the founding rule (LLMs reason; scripts decide). Pass `--max-parallel N`:

  - The plan's `depends_on` and `touches` are scheduling-authoritative. A
    "wave" is the ready tasks (all depends_on done, not yet complete) whose
    `touches` are pairwise disjoint, capped at N. `wave-next` computes it;
    the LLM never infers it (ADR-0010). A file whose change is a dependency
    ordering (shared router/DI registration, pubspec.yaml, lockfile) belongs
    in `depends_on`, never in `touches` - one shared file in two tasks'
    `touches` silently serializes the whole plan.
  - Each wave task gets its own git worktree + `task/<N>` branch and its own
    ledger shard (`worktree-alloc`); `task-run` drives it inside that
    worktree, so a task's files and its session never contend with a sibling.
    `worktree-alloc` best-effort warms the new tree (pubspec.lock +
    .dart_tool copied from the integration tree, then `pub get --offline`)
    so the first gate is not a cold resolve/compile.
  - `run-pipeline` prefixes each background task's output with `[task N]`
    (the heartbeat), so a wave shows progress instead of going silent until
    `wait` returns.
  - `integrate` merges the whole wave first and gates ONCE (S2); on red it
    resets and bisects with the per-merge loop, which aborts only the failing
    merge, so the integration branch is never left red. In the per-merge path
    the suite is skipped (ledger `integrate_suite_skipped`) only when the merge
    is provably tree-equivalent to what green-gate already validated
    (ADR-0013). Each task's shard is then merged into the integration ledger
    (ADR-0011/0012).
  - Default is `--max-parallel 2`. `--max-parallel 1` is the serial path,
    behavior-preserving (advances via `route-next` instead of `first_incomplete`;
    the ledger sequence is asserted by a regression test) - no worktrees, no
    integration - the regression contract.
  - Integration failure is a bounded blocker: one re-attempt in the task's
    existing worktree, then a human block. It never self-heals in a loop; a
    true in-place corrective is deferred.

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
headlessly): Strategic (Agente diretor / Agente revisor) and Operational
(Agente operador) = opencode-go/deepseek-v4.1-flash.

On Git Bash for Windows, pipeline-workspace and cmd normalize native paths
through their shared lib/path-normalize.sh helper before POSIX filesystem
operations. This supports checkout and output paths with spaces and prevents
MSYS from attempting to create a literal C: directory.

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
agent/                mirrored tier agent definitions (kept byte-identical
                      to the live ~/.config/opencode/agent/ definitions)
docs/superpowers/     ADRs, specs, plans
skills/               the skills (SKILL.md per skill)
  flutter-app-pipeline/   the Flutter layer + scripts + tests
  two-model-sdd-pipeline/ the generic two-tier engine + scripts
  apple-design/           vendored Apple interface-design skill (MIT;
                          https://github.com/emilkowalski/skills)
  write-script/           deterministic-script conventions (exit-code families,
                          ledger sole-writer, resource header, unit tests)
  skill-scripter/         audits a skill/stage for prose decisions that should
                          be scripts; writes a scriptization plan

LICENSE
-------

MIT - see LICENSE file for details. Upstream: https://github.com/obra/superpowers
