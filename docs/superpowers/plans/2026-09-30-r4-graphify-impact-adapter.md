# R4 Graphify Impact Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce repeated tests and graph overhead without adding work or context to the agent creating `plan.json`.

**Architecture:** Keep the existing Graphify AST adapter, base/candidate edge union, and verified test-command execution. Classify full-suite decisions before graph access, cache normalized evidence by exact content and extractor identity outside the checkout, and verify unchanged gate inputs after tests without re-extraction.

**Tech Stack:** Python 3 standard library, Git CLI, allowlisted Graphify 0.9.50, existing unittest suites and shell gates.

**Spec:** [R4 trusted impact gates](../specs/2026-09-30-r4-trusted-impact-gates-design.md); [ADR-0004](../adr/0004-graphify-post-commit-subgraph.md).

## Implementation status and handoff

This revision was requested on 2026-09-30 for another session to implement. Read the spec and current code before editing. Preserve unrelated working-tree changes. The extracted ADR under `.work/r3-extracted-package-final-after-probe/` is historical package content; do not edit or use it as the current contract.

The original three deliverables already exist:

| Original task | Implementation commit | Treatment |
| --- | --- | --- |
| Isolated Graphify adapter | `5d3f000` | Retain extractor safety contract |
| Base/candidate graph binding | `64ed077` | Refactor orchestration and add cache |
| Selected command execution | `638f9c1` | Preserve execution and replace post-run rebuild |

These references establish implementation presence, not fresh test certification. Do not repeat the old plan's missing-adapter RED steps. All remaining work is listed below; no runtime optimization has been implemented by this documentation revision.

## Global constraints

- Only validated Graphify 0.9.50 schema and AST `imports`/`imports_from` relations contribute dependencies; retain existing resolution and uncertainty fallback.
- No `update`, semantic/LLM extraction, clustering, labeling, global graph queries, or graph context in prompts.
- Raw graphs/snapshots remain temporary. Only complete normalized evidence may be cached, under supervisor ownership outside checkouts.
- No graph fields or affected-test authoring requirement in `plan.json`; no cache of test PASS results and no new test-skip policy.
- Preserve exact base/candidate binding, ledger-owned argv/cwd/env, full baseline/closing suites, and analysis/format scope.
- Use focused checks per task; complete shared and Flutter suites once on the final candidate. Repeat broader checks only after relevant changes/failures; investigate every unexpected failure.

## Review focus

- Mixed toolchains: preflight must preserve independent full-suite reasons without losing cross-toolchain dependencies (Task 1).
- Same filenames with changed bytes/configuration/extractor: cache must miss; commit identity alone is insufficient (Task 2).
- Corrupt/concurrently written cache and path ownership: invalid entries cannot become trusted evidence or unsafe cleanup targets (Task 2).
- Warm cache or deleted cache after selection: neither may bypass source drift checks or require post-run extraction (Task 3).
- Performance claims: graph call counts and measured net gate time must distinguish fixture results from real Python/Flutter workloads (Task 3).

---

### Task 1: Separate input capture and graph-independent decisions

**Files:** Modify `skills/two-model-sdd-pipeline/scripts/gate_evidence.py`, `skills/two-model-sdd-pipeline/scripts/test_impact.py`, and `skills/two-model-sdd-pipeline/tests/test_r4_graphify_gate_evidence.py`. Create `skills/two-model-sdd-pipeline/tests/test_r4_impact_preflight.py`.

**Interfaces:**

- `capture_workspace_inputs(workspace: str, selection: list[str], mode: str) -> dict`: graph-independent diff, descriptors, policy, phase, and identity; no manifest write.
- `preflight(diff: dict, toolchains: list, policy: dict, phase: str) -> dict`: `requires_graph: bool` plus per-toolchain full-suite reasons; share classification with `select`.
- Preserve `create_workspace_manifest(workspace, selection, mode) -> dict` and existing manifest validation for callers.

- [ ] **Step 1: Add focused regressions.** Parameterize baseline/closing, changed dependency/build configuration, shared infrastructure, unsupported adapters, deleted tests, and unclassified files. Assert existing full argv/reasons and zero graph builds/snapshot materializations. Add mixed-toolchain coverage and an eligible source edit that still requires graph evidence; prove preflight and selector reasons agree.
- [ ] **Step 2: Verify intended RED.** Run `python -m unittest discover -s skills/two-model-sdd-pipeline/tests -p test_r4_impact_preflight.py -v`. Confirm failure is the missing preflight contract or unnecessary graph calls, not fixture setup.
- [ ] **Step 3: Implement capture and preflight.** Factor current graph-independent input collection and common full-suite rules; invoke preflight before `_graph_evidence`. Carry per-toolchain reasons into selection without using missing-graph diagnostics to overwrite known reasons. If all require full suites, skip graph acquisition entirely. Do not add skip semantics for empty or documentation-only diffs.
- [ ] **Step 4: Verify the changed boundary.** Run the new preflight module and `test_r4_graphify_gate_evidence.py` with unittest discovery. Investigate failures; adjust tests whose old unconditional-extraction expectations are intentionally superseded.
- [ ] **Step 5: Commit the deliverable** as `perf(r4): classify full-suite gates before graph extraction` after focused checks pass.

### Task 2: Cache normalized evidence per exact snapshot identity

**Files:** Create `skills/two-model-sdd-pipeline/scripts/test_dependency_cache.py` and `skills/two-model-sdd-pipeline/tests/test_r4_dependency_cache.py`. Modify `gate_evidence.py`, `test_dependency_graph.py` only for necessary extractor identity/normalization interfaces, and `test_r4_graphify_gate_evidence.py` under the same script/test directories. Inspect `scripts/run-pipeline`, `scripts/codex_launcher.py`, and `scripts/run_control.py` to wire lifecycle at the actual supervisor owner, preserving supported entry points.

**Interfaces:**

- `test_dependency_cache.make_key(inputs: dict) -> str`: canonical hash of repository namespace, complete snapshot path/content inventory and relevant modes, resolution inputs, extractor installation/version/schema/flags, adapter identity, and policy identity.
- `test_dependency_cache.get_or_build(cache_root: pathlib.Path, key: str, builder: Callable[[], dict]) -> dict`: validated normalized graph evidence; invokes builder only on a miss. Builder materializes/verifies snapshot content before `test_dependency_graph.build`.
- Supervisor supplies one private external cache directory per run through owned runtime state; direct gates fall back to a disposable local-to-gate external cache. Diagnostics stay outside deterministic evidence hashes.

- [ ] **Step 1: Add cache regressions.** Assert one build for repeated identical keys; changed source bytes, resolution manifest, extractor, adapter, policy, or repository namespace cause misses. Cover corrupt payload/schema, incomplete results, atomic concurrent publication, unwritable cache, and safe cleanup ownership. Assert no cache/raw output under source checkouts and no worker-supplied graph acceptance.
- [ ] **Step 2: Verify intended RED.** Run `python -m unittest discover -s skills/two-model-sdd-pipeline/tests -p test_r4_dependency_cache.py -v`; confirm failure concerns the missing cache behavior.
- [ ] **Step 3: Implement cache and supervisor lifecycle.** Use canonical JSON, validated complete entries, atomic replacement, and an owned temporary root. Validate paths/provenance and digest on hits. Cache write failure retains valid fresh evidence; corrupt/missing entries rebuild or fall back. Keep raw graphs disposable and cleanup restricted to roots created by this run. A conservative whole-snapshot content key is acceptable; do not add incremental parsing.
- [ ] **Step 4: Integrate independent base/candidate acquisition.** Compute keys before materialization; reuse validated evidence and preserve deterministic union. Reattach current Git provenance on every gate. Retain sealed gate-owned evidence for later verification, independent of cache eviction.
- [ ] **Step 5: Add orchestration assertions.** A cold gate builds at most once per distinct identity; unchanged warm inputs build zero times; a cached base plus changed candidate builds once. Assert snapshots are not materialized on hits, old/new rename consumers remain covered, and identical content can reuse evidence across commits without reusing gate approval.
- [ ] **Step 6: Verify the boundary.** Run `test_r4_dependency_cache.py` and `test_r4_graphify_gate_evidence.py` with unittest discovery. Run `test_r4_dependency_graph.py` only if adapter code changed. Investigate any failures before committing.
- [ ] **Step 7: Commit the deliverable** as `perf(r4): reuse validated dependency evidence by content`.

### Task 3: Verify retained evidence without rebuilding and measure net cost

**Files:** Modify `skills/two-model-sdd-pipeline/scripts/gate_evidence.py`, `scripts/run-gates`, `scripts/toolchain_gate.py` if needed for pre-execution identity checks, `tests/test_r4_graphify_gate_execution.py`, and `tests/test_r4_impact_gate_wiring.py` under the same skill. Update `skills/two-model-sdd-pipeline/SKILL.md` and `skills/flutter-app-pipeline/SKILL.md` to describe implemented behavior. Save measured results to `docs/superpowers/plans/2026-09-30-r4-impact-efficiency-results.md`.

**Interfaces:**

- `verify_workspace_manifest(workspace: str, selection: list[str], mode: str, manifest: dict) -> None`: recaptures inputs via Task 1, validates retained evidence, and raises on drift. No extraction, reselection, manifest rewrite, or requirement that the cache still exists.
- `run-gates` invokes verification immediately before commands and after commands, preserving executed argv and the original selection hash in the ledger.

- [ ] **Step 1: Add regressions.** Assert successful gates call graph construction only during preparation, never during post-run checks. Parameterize candidate bytes, base, plan, descriptor/argv, environment, policy, extractor/adapter identity, and manifest tampering; each must reject PASS. Removing the cache after selection must still permit unchanged retained evidence. Preserve selected/full argv and unchanged analysis/format behavior.
- [ ] **Step 2: Verify intended RED.** Run `python -m unittest discover -s skills/two-model-sdd-pipeline/tests -p test_r4_graphify_gate_execution.py -v`; classify failures at the new verification/count assertions before changing runtime behavior.
- [ ] **Step 3: Implement identity-only verification.** Replace the post-run `create_workspace_manifest` call. Check current inputs and the original sealed manifest/evidence; never repair drift by constructing a new manifest. Keep diagnostics/timing outside selection hashes. Maintain existing failure ledger behavior.
- [ ] **Step 4: Verify focused execution.** Run execution and wiring modules with unittest discovery. Confirm zero extraction calls for known full-suite gates, warm eligible gates, and post-run verification; distinguish warm preparation from post-run checks.
- [ ] **Step 5: Measure and record.** Use disposable representative Python and Flutter workloads with real tools where available. Record cold/warm extraction counts, cache hits/misses, snapshot/extraction/selection/validation/test times, selected/total test counts, and fallback reasons. Compare net time against configured full suites and, where practical, the original R4 lifecycle on the same candidate/environment. Label unavailable toolchains and fixture-only evidence; do not claim speed from mocks. Avoid adding a general benchmark subsystem.
- [ ] **Step 6: Update operator guidance.** Remove contradictory guidance prescribing unconditional per-task full suites or graph rebuilds. Document private evidence reuse, conservative fallback, unchanged planning contract, and the limits of the measurements. Preserve historical ADR sections.
- [ ] **Step 7: Verify the final candidate.** Run `python -m unittest discover -s skills/two-model-sdd-pipeline/tests -v` and `python -m unittest discover -s skills/flutter-app-pipeline/tests -v` once after final code changes. Investigate failures before reporting; rerun affected checks after fixes. Do not claim unavailable verification passed.
- [ ] **Step 8: Commit and hand off** as `perf(r4): verify gate identity without graph reconstruction`, with focused/full verification results and measured limitations.

## Self-review and execution boundary

Preflight waste maps to Task 1; identity-safe reuse/lifecycle maps to Task 2; drift checks, guidance, and performance evidence map to Task 3. The interfaces compose without moving selection into the planning agent. Safety fallbacks and closing verification remain intact. Full suites are concentrated on the final implementation candidate, not each optimization task.

This session changes documentation only. The next implementation session should start at Task 1 after confirming repository state and reading the revised spec; the original three implementation commits must not be recreated.
