# R4 Graphify Impact Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Use a trusted, ephemeral Graphify AST graph to select affected Python and Flutter/Dart tests at task and integration gates, with full-suite fallback whenever graph evidence is uncertain.

**Architecture:** A project-owned adapter invokes only the allowlisted Graphify CLI `extract <snapshot> --code-only --no-cluster --out <isolated-output>`, validates its version/raw schema, and converts AST import edges into the existing selector's `reverse_edges`. Gate evidence builds clean baseline and candidate snapshots, binds graph evidence to exact source identities, and passes the validated selection to test execution. Graph artifacts stay in temporary directories; analysis, formatting, baseline, and closing remain full scope.

**Tech Stack:** Python 3 standard library, Git CLI, Graphify CLI 0.9.50 (allowlisted), existing `unittest` suite and shell gate entry points.

**Spec:** `docs/superpowers/specs/2026-09-30-r4-trusted-impact-gates-design.md`; decision amendment: `docs/superpowers/adr/0004-graphify-post-commit-subgraph.md`.

## Global Constraints

- Only validated Graphify version/schema and AST-origin `imports`/`imports_from` edges contribute dependency paths.
- No `update`, semantic/LLM extraction, clustering, labeling, `affected`, `explain`, or global graph command is used.
- Graphify absence, unvalidated output, failed sources, unresolved/dynamic/ambiguous dependencies, and candidate drift select full suites or reject PASS.
- No generated graph artifact is written to or committed from the user's checkout.
- Task and integration tests may be selective; baseline and closing verification always run complete configured suites.
- Preserve existing ledger-owned toolchain commands, R3 candidate identity, and analysis/format scope.

## Review Focus

- Graphify's Dart `package:` nodes may have no `source_file`; pin URI-to-`lib/` resolution and full-suite fallback for unknown package or missing file in Task 1.
- Graphify may return exit 0 with incomplete evidence; pin `failed_sources`, AST origin, expected node/link schema, and empty/unsupported edge handling in Task 1.
- Baseline and candidate import graphs can differ after deletion/rename; pin deterministic edge union and exact base/candidate identities in Task 2.
- A valid selection can still be ignored by the runtime gate; prove the executed test argv equals the validated manifest command in Task 3.
- User `graphify-out/` state must remain untouched; prove all CLI output paths are inside disposable snapshots in Task 1 and Task 3.

---

### Task 1: Add the isolated Graphify AST adapter

**Files:**
- Create: `skills/two-model-sdd-pipeline/scripts/test_dependency_graph.py`
- Create: `skills/two-model-sdd-pipeline/tests/test_r4_dependency_graph.py`
- Modify: `skills/two-model-sdd-pipeline/toolchains/test-impact-rules.json`

**Interfaces:**
- Produces: `test_dependency_graph.build(snapshot: pathlib.Path, expected_version: str) -> dict`
- Returns extractor evidence: sorted repository-relative `reverse_edges`, `graphify_version`, `graph_digest`, `source_inventory_hash`, and completeness diagnostics. It does not claim Git identity; Task 2 attaches commit/tree identity from its trusted snapshot manifest.
- Consumes raw Graphify JSON v0.9.50 fields `nodes`, `edges`, and `hyperedges`; accepts only nodes and edges whose `_origin` is `ast`, and only `imports`/`imports_from` relations. If `failed_sources` is present, it must be an empty list.

- [ ] **Step 1: Write failing adapter tests** for Python transitive imports, standard-library and declared external imports, missing local Python modules, Dart relative and `package:` imports, declared external packages, unknown package names, mismatched edge-source identity, deterministic output, exact raw-extract CLI arguments, and output confinement to a temporary snapshot. Assert `--code-only` and `--no-cluster` are present; no `update` or LLM command runs.
- [ ] **Step 2: Verify RED** with `python -m unittest discover -s skills/two-model-sdd-pipeline/tests -p test_r4_dependency_graph.py -v`; expected failure because the adapter does not exist.
- [ ] **Step 3: Write failing safety tests** for missing binary, wrong version, nonzero exit, malformed JSON, nonempty optional `failed_sources`, unsupported raw schema, inferred edges, mismatched edge-source identity, unresolved/ambiguous relative paths, unknown Dart package names, absent target paths, and dynamic import relations. Assert result marks graph incomplete, never returns partial `reverse_edges` as trusted evidence.
- [ ] **Step 4: Implement `build`** using `subprocess.run` with argv (never shell), invoke only `graphify --version` and `graphify extract <snapshot> --code-only --no-cluster --out <snapshot>/.r4-graphify-output`, read `<snapshot>/.r4-graphify-output/graphify-out/graph.json`, map raw `edges` to repository paths using the complete source inventory, require source-node/source-file agreement, ignore only Python standard-library/verified declared third-party imports and Dart packages declared as external dependencies, and resolve Dart URI-only local nodes by the declared package name plus `lib/` or a unique relative path. Any unknown or unresolved local input returns incomplete evidence.
- [ ] **Step 5: Add policy allowlist** for the validated Graphify version, JSON schema contract, accepted relations, and AST origin in `test-impact-rules.json`; do not silently allow unknown future versions.
- [ ] **Step 6: Run adapter tests**; expected all pass and the disposable fixtures are removed by test cleanup.
- [ ] **Step 7: Commit** adapter, tests, and policy as `feat(r4): add isolated Graphify dependency adapter`.

### Task 2: Bind baseline and candidate graphs to gate evidence

**Files:**
- Modify: `skills/two-model-sdd-pipeline/scripts/gate_evidence.py`
- Modify: `skills/two-model-sdd-pipeline/scripts/test_impact.py`
- Modify: `skills/two-model-sdd-pipeline/tests/test_r4_impact_gate_wiring.py`
- Create: `skills/two-model-sdd-pipeline/tests/test_r4_graphify_gate_evidence.py`

**Interfaces:**
- Consumes: `test_dependency_graph.build(snapshot, expected_version) -> graph evidence`.
- Produces: a selector graph v1 (`version`, `base_commit`, `base_tree_hash`, `reverse_edges`) plus `gate_evidence.create_workspace_manifest(workspace, selection, mode) -> manifest` with graph digest/provenance bound to the exact baseline/candidate snapshot identities.

- [ ] **Step 1: Write failing tests** proving a task gate builds graphs from separate baseline and candidate snapshots, unions normalized import edges deterministically, passes the trusted graph to `test_impact.select`, and records graph/tool/version/source-inventory identity in evidence.
- [ ] **Step 2: Verify RED** with the focused graph evidence tests; expected selector receives `None` or lacks graph provenance under the current implementation.
- [ ] **Step 3: Add failing fallback tests** for Graphify absent/unknown version, extraction failure, changed `pubspec.yaml`, deleted or renamed source/test, incomplete inventory, base mismatch, and snapshot drift. Assert each selects full suites and records reasons/gaps; never preserve a partial graph.
- [ ] **Step 4: Implement snapshot building** from the Git base tree and the exact current candidate (including staged, unstaged, and untracked files already captured by the manifest's diff); exclude `.git`, all ignored graph output, and unrelated external workspaces. Ensure all Graphify output remains below disposable snapshot roots.
- [ ] **Step 5: Implement graph union and provenance** in `gate_evidence.py`; retain the current full-suite fallback if either side is incomplete. Extend `test_impact` only as needed to validate graph schema/provenance without relaxing path safety or candidate identity.
- [ ] **Step 6: Run focused graph evidence and selector tests**; expected selected graph hash and selector result remain deterministic across repeated builds.
- [ ] **Step 7: Commit** as `feat(r4): bind Graphify impact graphs to gate snapshots`.

### Task 3: Execute only the verified test command at task/integration gates

**Files:**
- Modify: `skills/two-model-sdd-pipeline/scripts/run-gates`
- Modify: `skills/two-model-sdd-pipeline/scripts/toolchain_gate.py`
- Modify: `skills/two-model-sdd-pipeline/tests/test_r4_impact_gate_wiring.py`
- Create: `skills/two-model-sdd-pipeline/tests/test_r4_graphify_gate_execution.py`
- Modify: `skills/two-model-sdd-pipeline/SKILL.md`
- Modify: `skills/flutter-app-pipeline/SKILL.md`

**Interfaces:**
- Consumes: candidate-bound impact manifest from Task 2 and the supervisor-owned toolchain descriptor.
- Produces: task/integration test invocations using only the validated manifest argv; baseline/closing and uncertainty invoke the original complete-suite argv.

- [ ] **Step 1: Write failing execution tests** with a fake test executable that records argv/cwd/env. Prove a selected manifest executes the affected selector paths, while the original full command executes for closing and uncertainty. Prove analysis/format argv is unchanged.
- [ ] **Step 2: Verify RED**; expected the current code invokes the original complete test argv despite a valid selector result.
- [ ] **Step 3: Add failing integrity tests** for manifest tampering, wrong toolchain ID, unsafe argv/path, candidate drift after the test, and Graphify artifact leakage; assert no selected test command runs and PASS is impossible.
- [ ] **Step 4: Implement gate consumption** by validating the persisted manifest immediately before execution, deriving test argv solely from the ledgered descriptor plus safe selected paths, preserving the existing command runner and non-test commands, and forcing full argv in `baseline`/`closing` phases.
- [ ] **Step 5: Recompute candidate/graph identity after execution** and reject PASS on any drift; ledger the executed argv and impact-selection hash.
- [ ] **Step 6: Update operator guidance** to describe candidate-bound Graphify AST evidence and full-suite fallback without adding a worker/reviewer graph-context stage.
- [ ] **Step 7: Run focused wiring/runner tests and then both complete suites**: `python -m unittest discover -s skills/two-model-sdd-pipeline/tests -v` and `python -m unittest discover -s skills/flutter-app-pipeline/tests -v`. Expected: no new failures; preserve and investigate every failure before reporting.
- [ ] **Step 8: Commit** as `feat(r4): execute candidate-bound affected test gates`.

## Self-review

- Spec coverage: isolated CLI, version/schema/AST validation, Python/Dart resolution, exact baseline and candidate identity, graph uncertainty fallback, task/integration wiring, full closing suites, and no user graph artifact mutation are assigned to Tasks 1–3.
- Step scan: every implementation step names an owner, input, or testable result. Expected RED failures are at the missing adapter or ignored manifest command.
- Type consistency: Task 1's graph evidence is consumed by Task 2; Task 2's validated impact manifest is consumed by Task 3. All use repository-relative paths and the existing selector graph v1 contract.
- Review focus: all five risk classes are pinned to focused tests in their owning task.
- Proportion: three deliverables align with the graph adapter, candidate evidence, and gate execution boundaries; each ends in its own test cycle and commit.
