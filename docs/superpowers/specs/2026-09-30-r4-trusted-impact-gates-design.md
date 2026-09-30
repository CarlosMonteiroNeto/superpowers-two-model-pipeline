# R4 trusted impact gates design

## Goal and status

Reduce repeated tests per task, add no graph-selection work or graph context to the agent creating `plan.json`, and avoid unnecessary graph extraction/loading. Preserve candidate-bound evidence and full suites whenever impact is uncertain. Baseline and closing remain full-suite; analysis and formatting retain their scope.

Documentation revision authorized on 2026-09-30 for implementation in another session. The original adapter, snapshot binding, and selected-command execution exist in commits `5d3f000`, `64ed077`, and `638f9c1`. The optimizations below remain pending.

## Evidence and decision

The existing `run-gates` creates a manifest before commands and recreates it afterward. Each task/integration manifest builds base and candidate graphs: normally four extractions per gate. Extraction also precedes selector rules that can already require full suites. There is no reuse between attempts.

Keep the deterministic Graphify adapter and selector. Add graph-independent classification, a supervisor-owned cache of validated normalized dependency evidence, and identity-only post-run verification. Replacing Graphify with language-specific parsers is a separate decision requiring comparative measurements. No latency improvement is claimed without measurement.

## Extractor contract retained

Graphify remains an optional AST extractor for supported Python and Flutter/Dart adapters. Only allowlisted version `0.9.50` and `extract <snapshot> --code-only --no-cluster --out <isolated-output>` are accepted. Raw output uses `nodes`, `edges`, and `hyperedges`; dependencies must have AST origin and `imports`/`imports_from` relations, with source-node/source-file agreement. Require complete source inventory and empty `failed_sources` when present.

Resolve local Python imports against the supported inventory and local Dart `package:` URIs through the owning `pubspec.yaml` and `lib/`. Ignore only verified standard-library or declared external dependencies. Missing, dynamic, unsupported, ambiguous, or unresolved dependencies remain uncertain and force full suites. Never trust partial graphs.

Do not use `update`, `affected`, `explain`, semantic/LLM extraction, clustering, labeling, or global knowledge graphs. Raw graphs and extraction snapshots remain disposable. Only normalized validated dependency evidence may survive in the private cache. No generated graph/cache artifact enters the checkout or commits.

## Gate flow

1. Capture actual Git base/candidate diff, test inventory, ledgered toolchains, policy, and environment. Task gates use the committed baseline plus current candidate changes; integration uses the exact pre-wave integration commit. Preserve staged, unstaged, untracked, renamed, and deleted paths under the existing identity contract.
2. Classify before constructing snapshots, reading cache entries, or invoking Graphify. Baseline/closing, unsupported adapters, configuration/shared-infrastructure changes, deleted tests, and unclassified changes retain existing full-suite decisions. If every selected toolchain requires full suites, perform zero graph reads or extractions. For mixed decisions, extract only if some toolchain still needs graph evidence, preserving the complete dependency inventory and cross-toolchain dependencies.
3. Obtain normalized evidence independently for base and candidate using the cache. Union reverse edges deterministically so deleted/renamed sources retain old consumers and new imports retain new consumers. Bind the union to this gate's exact identities; a cache hit is not a prior gate approval.
4. Run the existing selector. Missing test mappings and other uncertainty select full suites. Commands come only from ledgered descriptors plus validated test arguments. This revision introduces no documentation-only or empty-selection skip policy and no reuse of previous test PASS results.
5. Immediately before execution, validate the sealed manifest and current input identities. Execute selected test argv and record actual argv/cwd/env and selection hash.
6. After execution, recapture input identities and validate the same sealed evidence without calling the extractor or rebuilding the manifest/selection. Candidate, base, plan, toolchain, command, policy, extractor/adapter, environment, or manifest drift prevents PASS. Do not overwrite original evidence with evidence for a different candidate.

## Cache identity, ownership, and lifecycle

Add `test_dependency_cache.py` to own cache keys, storage, and validation. Use a supervisor-owned temporary directory outside all source checkouts, shared across gates/attempts of one pipeline run. Pass its absolute location through supervisor state to gate processes; workers and the planning agent do not supply entries. Reuse an established runtime-directory mechanism where available. Without a safe shared location, use a disposable per-gate cache and report that cross-gate reuse is unavailable. Delete the shared cache at run teardown; never delete an arbitrary caller-supplied path.

Cache each snapshot independently. Its canonical key includes repository namespace, sorted repository-relative paths and content digests for the complete extractor input inventory (including resolution manifests), extraction flags/schema, verified extractor installation identity/version, adapter implementation identity, and resolution-policy identity. Include file modes/link treatment where they affect extraction. File counts, mtimes, branch names, or commit IDs alone are insufficient. A conservative whole-snapshot content key is acceptable initially; incremental parsing and long-lived cross-run caches are out of scope.

On a hit, validate key, schema, complete status, normalized paths/edges, provenance, and payload digest. A digest detects corruption; supervisor ownership supplies the trust boundary. Do not trust worker-supplied evidence merely because its checksum is consistent. Write complete entries atomically; concurrent readers must never see partial writes. Missing, invalid, incompatible, or corrupt entries are misses followed by extraction or safe full-suite fallback. Cache write failures must not discard valid in-memory evidence. Do not persist incomplete evidence as a successful entry.

Materialize a snapshot only on a miss and verify that its content matches the key before publishing evidence. Retain a sealed in-memory or gate-owned copy/digest of the evidence used for selection. Post-run verification checks retained evidence rather than relying on an evictable cache entry. Unchanged base and candidate content may share one entry; attach Git provenance separately for each gate.

## Planning and agent token contract

The strategic agent continues to write scope, acceptance, task dependencies, and existing plan fields. It does not enumerate affected tests, load graph files, construct cache keys, or maintain dependency edges. No graph fields are added to `plan.json`. Workers/reviewers receive no graph context or extra graph dispatch stage. Scripts own selection and emit compact reasons; raw graphs remain outside prompts. This prevents additional planning cost; it does not eliminate context needed to understand and plan a feature.

## Ownership and interfaces

- `test_impact.preflight(diff, toolchains, policy, phase) -> dict` returns `requires_graph: bool` and per-toolchain full-suite reasons using the same classification rules as `select`. It never reads graphs or changes fallback semantics.
- `test_dependency_graph.build(snapshot, expected_version) -> dict` retains extraction/normalization ownership.
- `test_dependency_cache.get_or_build(cache_root, key, builder) -> dict` validates/reuses complete evidence or invokes a zero-argument builder on a miss. The builder materializes/verifies the snapshot. Diagnostics/timings are separate from deterministic evidence hashes.
- `gate_evidence.capture_workspace_inputs(workspace, selection, mode) -> dict` captures graph-independent inputs/identity without writing a manifest. `create_workspace_manifest` composes capture, preflight, cache, and selection.
- `gate_evidence.verify_workspace_manifest(workspace, selection, mode, manifest) -> None` validates retained evidence and recaptured inputs; raises on drift and never extracts, selects again, or rewrites the manifest.
- `run-gates` and `toolchain_gate` retain ledger-owned execution. Supervisor runtime lifecycle owns shared cache creation and teardown.

## Acceptance and proportionate verification

Use focused regressions per changed boundary; preserve existing adapter safety tests. Run relevant shared and Flutter complete suites once on the final candidate, repeating only when later changes or failures justify it. Investigate unexpected failures. This development policy does not relax runtime baseline/closing gates or task RED/GREEN evidence.

Required checks:

- Known full-suite decisions: zero snapshot materializations, cache graph reads, or extraction calls.
- Cold eligible gate: at most one extraction per distinct base/candidate content identity (normally two); warm identical gate: zero. Cached base plus changed candidate: at most one new extraction.
- Post-run verification: zero extractions, with candidate/configuration/environment/manifest drift still rejected.
- Corruption, incompatible extractor/adapter/policy, and changed resolution inputs never reuse stale evidence. Concurrent writes never expose partial entries. Missing cache after selection does not invalidate retained evidence.
- Rename/delete union and exact executed argv remain correct. No graph context or required graph fields enter planning, briefs, or review packages.

Record snapshot, extraction, selection/identity-validation, and test elapsed times, extraction counts, cache hits/misses, selected/total test counts, and fallback reasons outside deterministic hashes. Compare cold and warm representative Python and Flutter gates against configured full-suite executions and, where practical, the pre-optimization implementation on the same candidate/environment. Report unavailable real toolchains honestly. Fixtures prove call-count bounds, not real-world speed. Measure net gate time before claiming improvement.

## Limits

Static imports cannot prove arbitrary runtime behavior; uncertainty retains full suites. Hashing and filesystem scans still cost time on cache hits. This revision does not add languages, expand graph scope into planning, skip required tests, cache PASS results, or claim Graphify is fastest. ADR-0004's removed knowledge/context workflow remains removed.
