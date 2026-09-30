# R4 trusted impact gates design

## Goal

Wire R4 affected-test selection into task and integration gates so a verified manifest determines the test command that actually runs. Preserve full-suite verification whenever dependency coverage, source identity, or command selection is uncertain. Closing verification always runs every configured full suite.

## Current gap

`test_impact.select` can emit deterministic affected test paths and argv, but `gate_evidence.create_workspace_manifest` always passes a missing graph. This makes every runtime manifest select full suites. `run-gates` then invokes the original toolchain descriptor commands, without consuming the manifest's selected argv. Existing tests therefore prove the selector in isolation but not selective gate execution.

## Graphify decision

Graphify was considered and is not part of this design. ADR-0004 was superseded on 2026-09-10 and explicitly removed code-graph stages from the pipeline; the R5 plan also says not to reinstate a Graphify dependency. R4 nevertheless requires dependency reverse edges for test selection. The graph here is limited to ephemeral, deterministic source-to-test dependency evidence for supported adapters; it does not query or maintain a general code knowledge graph, expose interface summaries, require a Graphify CLI, or add a new language capability.

## Design

1. Add a deterministic dependency graph builder for the already-supported Python and Flutter/Dart test adapters. It reads source files from Git snapshots, records reverse dependency edges to consumers, and binds graph metadata to the exact source commits and trees used to build it. It does not execute project code or invoke external providers.
2. Build the graph from both sides of the gate diff so renamed and deleted source paths retain their old consumers while additions and changed imports use candidate consumers. The graph is accepted only when its baseline identity matches the selected diff base.
3. Treat unresolved or dynamic imports, ambiguous module resolution, unsupported constructs, stale graph identity, missing test inventory, and missing source-to-test coverage as uncertain. These conditions select each toolchain's configured full-suite command. Never use a partial result from an uncertain graph.
4. Have `gate_evidence` derive the actual changed paths for task gates and integration gates. For a clean merged candidate, integration uses the exact pre-wave integration commit as the diff base; task gates use the current committed baseline plus the candidate worktree changes. Bind this base, head tree, environment, toolchain commands, and impact policy into the manifest.
5. Make `run-gates` validate the manifest immediately before execution and pass its test argv only for the exact selected toolchain when the manifest proves a complete affected selection. The selected argv must originate from the ledgered descriptor and differ only by safe test-path arguments. Configured analysis and formatting commands retain their existing full scope. Baseline capture and closing verification always execute full configured suites.
6. Recompute and validate the same candidate-bound impact identity after commands finish. Any source, graph, command, or environment drift prevents a passing gate record. Ledger evidence records the selected command and manifest hash.

## Ownership and interfaces

- `test_dependency_graph` owns source-backed graph extraction and completeness diagnostics for Python and Dart/Flutter.
- `gate_evidence` owns the baseline/candidate diff, graph identity, and validated manifest creation.
- `run-gates` and `toolchain_gate` own execution of manifest-selected test argv. Callers cannot submit arbitrary test paths or commands.
- `test_impact` remains the deterministic selector and continues to fail closed to full suites for unsupported or incomplete evidence.

## Verification

- Unit fixtures cover Python imports, Dart package/relative imports, cycles, rename/delete/add changes, ambiguous or dynamic imports, missing tests, stale identities, and conservative fallback.
- Gate integration tests prove a selected test argv is the command executed, full suite runs for uncertain impact and during closing, analysis remains unchanged, and post-run candidate drift records FAIL rather than PASS.
- Existing shared and Flutter suites must pass on the final candidate. Acceptance remains bound to the final source commit and declared runtime.

## Risks and limits

Static dependency extraction cannot prove arbitrary runtime behavior. Dynamic and ambiguous dependencies therefore force full suites. This design does not add language or test-framework support beyond the current Python and Flutter/Dart adapters, and does not make closing verification selective.
