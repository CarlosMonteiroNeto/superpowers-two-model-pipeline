# R4 Script-Owned Graph Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Prepare the Graphify dependency graph once per run in scripts, reuse task-specific slices in coder briefs and affected gates, skip still-valid task Green tests in post-Green integration selection, and retain full-suite closing and reviewed graph publication.

**Architecture:** A script refreshes and reads a validated raw AST graph once after the canonical plan is accepted, then writes an immutable run-local index and per-task generated metadata. `brief-scaffold` reads only a task slice. R4 selectors use the run-start dependency map and actual diffs, with conservative full-suite fallback; publication graph artifacts refresh before closing verification/review so the pushed HEAD stays candidate-bound.

**Tech Stack:** Python 3 standard library, Graphify raw `extract` CLI, existing Bash pipeline scripts, JSON run artifacts, existing Python unittest suite.

**Spec:** `docs/superpowers/specs/2026-09-30-r4-script-owned-graph-context.md`

## Global Constraints

- Script CEO owns graph refresh, cache/index identity, brief enrichment, gates, and publication.
- The planning agent receives no graph payload and does no graph-reading work.
- Graph-derived runtime data never changes the planner-authored canonical `plan.json` or its transaction identity.
- Only allowlisted Graphify raw AST import relations can supply directed R4 dependencies.
- Unknown, stale, malformed, incomplete, or mismatched graph data selects full configured suites.
- Closing verification always executes all configured suites.
- Graph updates that affect a published candidate happen before its closing gate and final review; publication does not mutate approved HEAD.
- Preserve the user's existing uncommitted files and unrelated worktree changes.

## Review Focus

- Stale cache after resume or plan refresh: reject by run/tree/plan/touches identity, with tests for cache mismatch and reuse.
- Corrective task has new paths: query its new bounded slice from the same validated index; never inherit the parent's slice.
- Green test becomes invalid after another task changes an input: include it again in affected selection.
- Raw Graphify extraction is incomplete or unsupported: no partial selection; execute full suite and keep coder brief generation deterministic.
- Graph publication changes HEAD after approval: reject; ensure refresh is before closing evidence and final review.

---

### Task 1: Create a run-scoped graph context index

**Files:**
- Create: `skills/two-model-sdd-pipeline/scripts/graph_context.py`
- Modify: `skills/two-model-sdd-pipeline/scripts/test_dependency_graph.py`
- Test: `skills/two-model-sdd-pipeline/tests/test_r4_graph_context.py`

**Interfaces:**
- `graph_context.prepare(workspace: pathlib.Path, repository: pathlib.Path, plan_path: pathlib.Path, source_commit: str) -> dict`
- `graph_context.load_task_context(workspace: pathlib.Path, task: dict) -> dict`
- The cache stores schema/version, repository/run identity, source commit/tree, Graphify version, graph digest, complete flag/diagnostics, and normalized dependency adjacency. Per-task context records the canonical plan hash and `touches` digest separately so plan corrections can reuse the same graph cache.
- Cache files live only in the gitignored run workspace; preparation reads the raw Graphify graph once.

- [x] **Step 1: Write failing tests** for one raw extraction/read, task-scoped dependency mapping, graph provenance, and stale cache rejection.
- [x] **Step 2: Run** `python3 -m unittest discover -s skills/two-model-sdd-pipeline/tests -p test_r4_graph_context.py -v`; verify failures are the missing prepare/cache behavior.
- [x] **Step 3: Implement** graph context preparation and serialization by reusing the validated raw AST adapter; do not use `graphify update` for oriented impact evidence.
- [x] **Step 4: Add failing-then-passing tests** for unavailable Graphify, incomplete source mapping, and unsupported schema selecting `complete=False` with diagnostics and no partial task map.
- [x] **Step 5: Run the focused graph-context tests** and verify each case passes.

### Task 2: Enrich generated coder briefs from the cached graph slice

**Files:**
- Modify: `skills/two-model-sdd-pipeline/scripts/brief-scaffold`
- Modify: `skills/two-model-sdd-pipeline/scripts/orchestrator`
- Modify: `skills/two-model-sdd-pipeline/scripts/task-run`
- Modify: `skills/two-model-sdd-pipeline/scripts/pipeline-workspace`
- Test: `skills/two-model-sdd-pipeline/tests/test_brief_scaffold.py`
- Test: `skills/two-model-sdd-pipeline/tests/test_r4_graph_context.py`

**Interfaces:**
- Brief generation consumes `graph_context.load_task_context` or its serialized task slice; it never invokes Graphify or reads the complete raw graph.
- Run-start preparation occurs after the canonical plan/workspace is validated and before the first task brief can dispatch.
- Plan refresh reattaches generated metadata from the matching cache; a new corrective task is queried by its own `touches`.

- [x] **Step 1: Write failing tests** that verify the planning request contains no graph payload and coder brief includes only the bounded current-task slice.
- [x] **Step 2: Run** `python3 -m unittest discover -s skills/two-model-sdd-pipeline/tests -p test_brief_scaffold.py -v`; confirm the graph-context assertions fail.
- [x] **Step 3: Implement** run-start preparation before brief dispatch and append `Graph context (script-derived)` to generated coder briefs.
- [x] **Step 4: Add failing-then-passing tests** for correction tasks, plan refresh, absent context diagnostics, and proving per-task brief creation performs no Graphify subprocess or full-graph load.
- [x] **Step 5: Run** the focused brief and graph-context tests.

### Task 3: Reuse graph mapping for affected selection and avoid redundant Green tests

**Files:**
- Modify: `skills/two-model-sdd-pipeline/scripts/gate_evidence.py`
- Modify: `skills/two-model-sdd-pipeline/scripts/test_impact.py`
- Modify: `skills/two-model-sdd-pipeline/scripts/coder-gate`
- Modify: `skills/two-model-sdd-pipeline/scripts/run-gates`
- Modify: `skills/two-model-sdd-pipeline/scripts/ledger-append` (only if required by the existing evidence schema)
- Test: `skills/two-model-sdd-pipeline/tests/test_r4_impact_gate_wiring.py`
- Test: `skills/two-model-sdd-pipeline/tests/test_r4_final_suite.py`

**Interfaces:**
- Gate manifest records run-start graph provenance and actual base/head diff identity; it does not run Graphify.
- Green evidence records the exact task test paths, command identity, candidate/tree identity, and relevant input hashes.
- The integration selector subtracts a Green test only while its evidence still matches; otherwise it remains affected.

- [x] **Step 1: Write failing tests** for selected affected tests coming from the run cache without Graphify calls, and a valid Green test omitted from the later task integration command.
- [x] **Step 2: Run** the focused R4 gate tests; verify they fail at manifest graph acquisition and test subtraction assertions.
- [x] **Step 3: Implement** cache-backed manifest selection, Green evidence validation, and conservative full-suite fallback for graph/cache uncertainty.
- [x] **Step 4: Add failing-then-passing tests** for stale test hashes, changed relevant imports/files, missing cache, and full-suite closing remaining unchanged.
- [x] **Step 5: Run** the R4 graph, impact, and full-suite tests.

### Task 4: Refresh publishable Graphify output before closing approval

**Files:**
- Modify: `skills/two-model-sdd-pipeline/scripts/run-pipeline`
- Modify: `skills/two-model-sdd-pipeline/scripts/publication.py` (expected-head verification only; no graph refresh)
- Test: `skills/two-model-sdd-pipeline/tests/test_codex_publication.py`
- Test: `skills/two-model-sdd-pipeline/tests/test_r4_final_suite.py`

**Interfaces:**
- Publication preflight refreshes tracked Graphify output only for push-and-PR policy and runs before closing full-suite evidence and final review.
- Publication refuses a candidate whose HEAD differs from the closing/final-review approved commit.
- `publication.py` pushes only; it does not update or commit graph files.

- [x] **Step 1: Write failing tests** proving graph refresh is before closing verification/review and is skipped for local-only publication.
- [x] **Step 2: Run** `python3 -m unittest discover -s skills/two-model-sdd-pipeline/tests -p test_codex_publication.py -v`; verify ordering/publication assertions fail.
- [x] **Step 3: Implement** deterministic graph-refresh preflight, refuse pre-existing user changes under `graphify-out/`, stage/commit only refreshed tracked Graphify files before closing, and preserve push-only behavior in publication.
- [x] **Step 4: Add failing-then-passing tests** for refresh failure blocking push, graph refresh after review being rejected, and push using the approved exact HEAD.
- [x] **Step 5: Run** `python3 -m unittest discover -s skills/two-model-sdd-pipeline/tests -p test_r4_final_suite.py -v` and review the ADR amendment and spec links.

### Task 5: Verify integrated pipeline contracts and documentation

**Files:**
- Modify: `skills/two-model-sdd-pipeline/SKILL.md`
- Modify: `README-LLM.md`
- Modify: `README.txt`
- Test: `skills/two-model-sdd-pipeline/tests/test_skill_docs.py`
- Test: `skills/two-model-sdd-pipeline/tests/test_skill_content.py`

**Interfaces:**
- Documentation describes script-owned graph preparation, bounded coder-only graph context, cache reuse, Green test de-duplication, full-suite closing, and publication ordering.

- [x] **Step 1: Write failing documentation-contract tests** for the new graph stage and publication order.
- [x] **Step 2: Run** the focused documentation tests and verify they identify stale R4 guidance.
- [x] **Step 3: Update** skill and README references without restoring graph-reading responsibility to the planning agent.
- [x] **Step 4: Run** documentation-contract tests and the complete shared + Flutter suites on the final candidate.
- [x] **Step 5: Commit** only the files in this plan, leaving pre-existing user changes untouched.

## Plan self-review

- Spec coverage: graph preparation, one-time complete-graph read, task-level brief slices, runtime derived metadata, resume/correction behavior, Green evidence, full-suite closure, and pre-publication graph refresh each have an owning task.
- Step scan: each task begins with executable failing tests and has focused verification before moving on.
- Type/interface consistency: `prepare` and `load_task_context` are defined in Task 1 and consumed by Tasks 2–3.
- Review focus: all five high-risk cases above have explicit regression checks.
- Proportion: five separable implementation tasks; publication ordering is isolated from cache/brief changes and can be reviewed independently.
