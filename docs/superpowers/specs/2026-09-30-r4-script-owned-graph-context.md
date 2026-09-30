# R4 Script-Owned Graph Context and Gate Reuse

## Goal

Let deterministic pipeline scripts refresh and read the code graph once for a run, derive task dependencies without sending the full graph to the plan author, attach only task-relevant graph context to each coder brief, avoid repeating that task's already-passed Green tests in its affected integration gate, and retain one complete closing test run.

## User-facing behavior

- The planning agent writes the ordinary canonical `plan.json` from the specification. It is not given the graph and does not spend context tokens reading or summarizing it.
- After the plan is validated and before the first coder brief is created, Script CEO refreshes the run's graph snapshot, reads and validates it once, and stores a run-scoped local index with provenance.
- A deterministic brief script queries that index by the task's `touches` and adds a bounded, task-specific dependency/interface section to the coder brief. The coder never receives the full graph. Reviewer input remains governed by its existing review package.
- The script records graph-derived task dependencies as generated runtime metadata associated with `plan.json`; it does not alter the tracked plan authored by the planning agent.
- Task gates run the task's own declared RED/GREEN tests once. Its subsequent affected integration selection omits those tests when the Green evidence still matches the same test files and relevant inputs. It includes them again when intervening changes invalidate that evidence.
- The closing phase runs every configured full suite. This is the authoritative check for interactions introduced after the run-start graph snapshot.
- For push-and-PR publication, refresh the repository's tracked Graphify view before closing verification and final review, so those outputs are part of the reviewed candidate that is sent to `origin`. Do not mutate the candidate after final review. Local-only runs do not refresh or commit publication graph artifacts.

## Architecture

### Run-start graph preparation

1. The run coordinator invokes one graph-preparation script after initial plan validation and before any task brief dispatch.
2. The script uses the R4 isolated raw AST extraction contract to build a fresh graph from the exact run-start source tree. Extraction is the refresh operation for the dependency graph; `graphify update` output is not trusted for directional test-impact edges.
3. The adapter validates the allowlisted Graphify version/schema, source inventory, AST-origin import edges, and source/path mapping. It reads the complete raw graph once and serializes a compact, immutable run-local adjacency index plus graph digest, source tree identity, plan identity, and diagnostics.
4. For every task, the script derives affected code paths and relevant test paths from `touches`, using the existing conservative R4 impact rules. Derived data is stored in a sidecar keyed to the plan task and graph provenance, not in the planner-authored canonical plan file. The graph cache remains valid across correction-plan changes when the run-start source identity is unchanged; only the affected task slice is regenerated from that cache.
5. Missing Graphify, unsupported output, incomplete mapping, stale run identity, or any uncertain dependency causes the affected-test path to select configured full suites. Brief creation remains deterministic and labels missing graph context; it never asks the plan author to inspect the graph as fallback.

### Per-task brief generation and gates

- `brief-scaffold` reads the task's generated graph slice from the run-local index/sidecar and appends a bounded `Graph context (script-derived)` section capped at 100 lines and 12,000 bytes. It does not invoke Graphify or parse the full graph file. If the context exceeds the cap, it reports truncation; the separate test-impact map remains complete or falls back to full suites.
- If a correction adds a task or changes `touches`, scripts recompute only that task's derived slice from the same run-local index. A plan snapshot refresh must validate provenance and reattach derived metadata; it must not rebuild or reread the Graphify graph.
- Gate manifests continue to bind actual candidate diffs, commands, environment, and selected tests. The source dependency map is explicitly identified as the run-start snapshot. Task integration gates use it for the affected selection and subtract only tests whose exact Green evidence remains valid.
- If the graph cache is absent, mismatched, or incomplete, or actual changes cannot be covered by the run-start map, select the full configured suite for the affected gate. Never treat a partial map as complete.

### Closing and publication

- Closing remains full-suite; selective impact metadata cannot narrow it.
- If publication is `pull_request`, Script CEO refreshes the tracked Graphify project view before the closing full-suite gate and final review. Any graph artifacts changed by that refresh become part of the candidate before those checks. The publication tool may push only the same reviewed HEAD; it must not run a graph update that changes files after approval.
- `graphify update` may refresh the human-facing tracked Graphify view for publication, but its merged/undirected relations are never used as R4 dependency evidence. The isolated raw AST adapter remains the source of directional test dependencies.
- If publication graph refresh fails, publication is blocked and the run remains resumable. With `local` publication, no tracked Graphify artifacts are refreshed as a side effect.

## Data contracts

- Canonical authored `plan.json`: unchanged by graph preparation; task fields such as `touches`, `depends_on`, and verification remain planner-authored and retain existing validation/transaction hashes.
- Run-local graph sidecar: schema-versioned, immutable for the run-start source tree, keyed by repository/workspace/run identity, plan task id, task `touches` hash, and Graphify/source tree digest.
- Task graph slice: bounded repository-relative paths and validated relation labels only; no method bodies or arbitrary Graphify prose are sent to the coder.
- Green evidence: records test paths, command identity, test-file hashes, relevant dependency inputs, and the candidate identity against which Green passed. An integration selector may omit a task test only while this evidence remains valid.
- Closing evidence: always records full configured suite commands and final candidate identity.

## Compatibility and failure handling

- Python and Flutter/Dart keep using the R4 adapter's allowlisted raw AST import schema. Other languages continue to use configured full-suite commands.
- Dynamic/ambiguous imports, unsupported source forms, incomplete inventories, unresolved local paths, and graph version/schema mismatch are uncertainty and require broader testing.
- Brief generation may proceed without graph context after recording a diagnostic; test gating must fall back to full suites when graph-derived selection is uncertain.
- Resume reuses a cache only when repository, run, source tree, Graphify version, schema, and policy identities match. Plan hash and `touches` hash key each derived task slice, not the whole graph cache, so a corrected plan can reuse the same source graph without rereading it.
- A corrective task's derived context is recalculated from its updated `touches`; it cannot inherit a parent's dependency slice silently.

## Verification

- Tests prove the planning prompt/dispatch never includes a graph payload and graph preparation is script-owned.
- Fake Graphify fixtures prove one extraction and one complete graph read per initial run preparation, with no Graphify invocation from per-task brief generation.
- Brief tests prove each coder receives only the task's bounded slice, including correction tasks, and never the complete graph.
- Impact tests prove run-start dependencies select affected tests, invalid evidence falls back to full suites, and unchanged Green tests are omitted only while their evidence remains valid.
- Closing tests prove every configured full suite runs once in the closing phase and that publication graph refresh occurs before closing evidence/final review, not after approval.
- Publication tests prove a failed graph refresh blocks push and a successful push uses the exact reviewed candidate.

## Risks and limits

- A run-start import graph cannot predict every dependency introduced by later edits. Selective task gates can therefore miss an emergent interaction; the mandatory closing full suite prevents such a candidate from being published without validation.
- Graph slices are structural context, not implementation instructions. The plan and task acceptance remain authoritative.
- Updating tracked Graphify output changes the reviewed candidate and can produce a sizeable diff. The publication refresh must be deterministic, scoped, and performed before the closing gate and review.
- If tracked Graphify files already have user changes before publication refresh, the pipeline must preserve them and block automatic refresh rather than staging or replacing them.

## Supersession

This spec narrows the earlier R4 gate design's per-gate Graphify extraction: dependency extraction is prepared once at run start and reused for brief and task-gate selection, with full-suite closing as the final stale-map safety gate. It also reopens the historical context-graph workflow only for script-generated coder brief context. It does not authorize graph access by the planning agent or LLM execution of Graphify.
