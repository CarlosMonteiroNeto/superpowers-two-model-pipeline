# ADR-0004: Graphify — isolated test-impact extraction and evidence reuse

> **Historical decision superseded for R4's narrow test-impact use (2026-09-30).**
> The old knowledge/context graph workflow remains removed. R4 adds a new,
> isolated AST dependency-extraction use described in the amendment below.
> The efficiency revision at the end is the current target design; its
> implementation is pending. Earlier sections preserve historical decisions.

- **Status:** AMENDED (historical context-graph workflow remains superseded)
- **Date:** 2026-09-02 (amended 2026-09-05, superseded 2026-09-10, narrowly amended 2026-09-30)

## Context

Graphify was made Controller-side and lazy in a prior change (query at brief
time, rebuild only when stale). The developer's architecture re-ties the graph
to the deterministic layer with two rules: (1) the graph is updated only at the
moment it is about to be read — never per Coder iteration (that would be
wasted overhead), and never orphaned (updated but unread); (2) when B is
called for the next brief (and when D reviews), Script A extracts only the
affected-dependency subgraph — interfaces, models, and callers of the module —
and sends that slice instead of whole source files.

## Decision (amended 2026-09-05)

- `graphify-update` runs as part of the green-gate / coder-gate chain,
  **immediately before the task's commit**, so the regenerated graph artifacts
  (graphify-out/) enter the task's own commit. It is never per Coder iteration.
- `graphify-subgraph <ws> TASK` runs **immediately after** `graphify-update`
  (still before the commit) and queries the graph (`explain` / `path`) for the
  task's `touches`/`depends_on` modules, writing `<ws>/task-N-interfaces.md`
  (capped, ~100 lines). This file replaces the main agent's manual interface
  gathering for both B's next brief and D's review; `review-package` inlines it
  into the review package D receives.
- The graph exposes structure, not method bodies; the subgraph is the only code
  context sent to B per task.
- Both graph steps are best-effort: a missing graphify binary never blocks the
  gate (the gate's verdict stays the test/analyze exit code).

### What changed from the original decision

The original ADR said `graphify-update` runs only **after** a task is approved
and committed, and that "the graph can lag uncommitted work by design". The
developer's later feedback (2026-09-05) required the graph to **enter the
commit** it describes and to be **read immediately after being written** — an
update that is never read is orphaned work. The ordering is therefore inverted:
update → read → commit. The commit still happens before review (the full
commit-after-approval inversion was considered and rejected as too costly for
the benefit).

## Consequences

- B's per-task prompt input shrinks to the affected slice — direct token savings
  on the strategic tier.
- `graphify-subgraph` becomes the single deterministic replacement for the one
  LLM-composed header slice (interfaces) identified in the header analysis.
- The graph is never orphaned: every `graphify-update` in the gate chain is
  immediately followed by the `graphify-subgraph` read that consumes it.
- Because the graph is updated before the commit, the regenerated artifacts are
  part of the task's own commit — D's review and the next brief both read the
  freshest graph.

## Alternatives considered

- **Update per Coder iteration:** rejected by the developer — unnecessary
  overhead; the graph is consumed at brief time and review time, not mid-edit.
- **Post-commit update only (original ADR):** rejected by the developer's
  2026-09-05 feedback — the graph lagged uncommitted work and was never read in
  the scripted flow; the write was orphaned.
- **Commit after reviewer approval (full inversion):** considered and rejected —
  the cost (working-tree diffs, a post-approval commit step, red-integrity
  rework) outweighed the benefit; commit-before-review is kept.
- **Keep the main agent gathering interfaces (current):** rejected — it is the
  only non-deterministic slice in subagent headers and defeats the script-driven
  dispatch design.

## R4 amendment (2026-09-30): isolated AST dependency extraction

The user authorized reconsidering Graphify for R4 and changing this ADR. A
disposable probe of installed Graphify 0.9.50 confirmed that
`graphify extract <snapshot> --code-only --no-cluster --out <temporary-dir>`
produces a raw AST graph with oriented import edges for Python and Dart without
invoking an LLM. The `update` command is explicitly rejected: the observed
0.9.50 output set `directed: false`, and Graphify documents that update can
drop direction through its graph merge ([Graphify issue #2342](https://github.com/Graphify-Labs/graphify/issues/2342)).
The raw extractor writes `edges` rather than `links`; the adapter accepts that
raw schema only and verifies that each import edge's source node matches its
`source_file` before trusting source-to-target orientation. Python imports may
refer to standard-library/declared external modules without repository nodes.
Dart package imports may also target URI-only nodes, so the R4 adapter resolves
the project's own `package:` URIs through its `pubspec.yaml`, ignores only
verified external dependencies, and fails closed for missing or ambiguous
files.

The R4 decision is deliberately narrower than the superseded workflow:

- Graphify may build a fresh, temporary raw AST graph solely to derive
  source-to-test dependencies for task and integration test selection. Only
  `extract --code-only --no-cluster` is used; `update` is prohibited because
  its persisted undirected format cannot prove import orientation.
- Only validated Graphify version/schema and AST-origin `imports` or
  `imports_from` relations may contribute edges. Other relations, inferred
  edges, semantic extraction, clustering, and labeling are not used.
- Raw graphs are built from exact isolated Git source snapshots, identity-bound
  to their source commit/tree, and deleted with the temporary workspace.
  The efficiency revision below permits private reuse of normalized evidence.
  No `graphify-out/` artifact enters the user's checkout or commit.
- Missing or incompatible Graphify, extraction errors, failed sources,
  unsupported/dynamic imports, unresolved targets, or ambiguous path mapping
  select complete configured suites. Closing verification remains full-suite.
- The adapter feeds the existing deterministic selector; it does not expose
  graph context to workers/reviewers, query the general knowledge graph, or
  add another dispatch/stage to the LLM workflow.
- R5 may consume the shared R4 impact contract but must not broaden this
  adapter into template recall, planning context, or a new Graphify stage.

The user explicitly approved this scope change on 2026-09-30. This amendment
supersedes only the 2026-09-10 statement that no stage may build a code graph;
all other removal decisions above remain in force.

## R4 efficiency revision (2026-09-30): decide first, reuse evidence

The user requested this documentation revision for implementation in another
session. The goals are fewer repeated tests per task, no additional graph work
for the agent creating `plan.json`, and fewer unnecessary graph loads/extractions.

The initial R4 implementation creates base and candidate graphs both before and
after commands: normally four extractions per task/integration gate. It also
extracts before checking rules that can already require full suites. Keep the
adapter and change this lifecycle:

- Apply graph-independent full-suite rules before snapshots, cache reads, or
  extraction. Baseline/closing and decisions already requiring full suites need
  no graph. Unknown changes retain conservative behavior; this revision adds
  no new test-skipping policy.
- Reuse validated normalized dependency evidence in a supervisor-owned cache
  outside source checkouts, shared for one pipeline run and removed at teardown.
  Raw output remains ephemeral. Bind cache keys to complete input content,
  resolution manifests, extractor installation/version/schema/flags, adapter,
  and policy. Branch names, mtimes, or commit IDs alone cannot establish reuse.
- Validate cache integrity and provenance; publish complete entries atomically.
  Missing/corrupt/incompatible entries cause extraction or safe fallback. Never
  treat incomplete evidence as trusted or a cached graph as a cached test PASS.
- Preserve deterministic base/candidate edge union and exact gate identities.
  Extract at most once per distinct uncached snapshot identity; materialize
  snapshots only on misses. Revalidate sealed inputs/evidence after commands
  without invoking Graphify, reselection, or rewriting the original manifest.
  Drift still rejects PASS.
- Keep selection in scripts. Add no graph context, graph dispatch stage, or
  affected-test authoring requirement to planning, workers, or reviewers.
  Baseline/closing full suites and existing analysis/format scope remain intact.

This supersedes the initial R4 requirement to discard all normalized dependency
evidence after each extraction; it does not restore a persistent knowledge graph.
Prefer this bounded lifecycle change over retaining repeated extraction or
replacing Graphify with new parsers before measuring the alternatives.

Acceptance requires zero extraction for known full-suite decisions, zero for
warm identical inputs, and zero during post-run verification. Record cold/warm
net gate time, extraction counts, cache hits, selection size, and fallback reasons
before claiming performance gains. Use focused regressions during development
and complete shared/Flutter verification on the final candidate.

The authoritative details and remaining implementation work are in
[the R4 spec](../specs/2026-09-30-r4-trusted-impact-gates-design.md) and
[the R4 plan](../plans/2026-09-30-r4-graphify-impact-adapter.md).
