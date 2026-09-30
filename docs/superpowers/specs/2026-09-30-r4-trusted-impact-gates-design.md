# R4 trusted impact gates design

## Goal

Wire R4 affected-test selection into task and integration gates so a verified manifest determines the test command that actually runs. Preserve full-suite verification whenever dependency coverage, source identity, or command selection is uncertain. Closing verification always runs every configured full suite.

## Current gap

`test_impact.select` can emit deterministic affected test paths and argv, but `gate_evidence.create_workspace_manifest` always passes a missing graph. This makes every runtime manifest select full suites. `run-gates` then invokes the original toolchain descriptor commands, without consuming the manifest's selected argv. Existing tests therefore prove the selector in isolation but not selective gate execution.

## Graphify decision

Use Graphify only as an optional, ephemeral AST dependency extractor for R4 affected-test selection. The user explicitly authorized revising ADR-0004 if Graphify is more viable. Disposable probes with Graphify 0.9.50 showed that `extract <snapshot> --code-only --no-cluster --out <isolated-output>` emits raw AST `edges` with source/target import orientation and makes no LLM calls. Do not use `update`: it writes `directed: false` for raw updates, risking orientation loss in its graph merge. External Python modules and some Dart `package:` imports may have no repository-file nodes. The adapter must match local imports against the complete supported source inventory, require each edge's source node to match the import's `source_file`, resolve a Dart project's own `package:` URIs against its `pubspec.yaml`, and ignore only imports verified as standard-library or declared external dependencies. Missing local source nodes, undeclared external modules/packages, or ambiguous paths fail closed.

This does not restore Graphify as a knowledge/context stage: do not run `affected`, `explain`, `update`, semantic extraction, clustering, labeling, or global-graph commands; do not persist or commit generated graph artifacts; and do not pass graph context to workers or reviewers. Build a fresh raw graph under a temporary source snapshot for the exact candidate, accept only the tested Graphify version/schema and AST-origin import relations, and convert those relations into the existing selector's repository-relative `reverse_edges`. Require successful extraction, no failed sources if that field appears, complete node/path resolution, and candidate/base identity binding. A missing binary, unsupported version/schema, unresolved/dynamic/ambiguous import, or incomplete source inventory selects full suites.

ADR-0004's 2026-09-10 removal remains correct for the old knowledge/context graph workflow. This is a narrow, newly authorized R4 decision that amends its scope; R5 must not broaden it into another pipeline stage.

## Design

1. Add a deterministic Graphify adapter for the already-supported Python and Flutter/Dart test adapters. It builds a fresh raw AST graph from isolated Git source snapshots using the allowlisted Graphify CLI with `extract --code-only --no-cluster --out`, accepts only raw `edges` with AST-origin `imports`/`imports_from` relations, verifies that each edge's source node identifies its `source_file`, and maps those edges to repository-relative files. It does not execute project code, invoke external providers, call Graphify's LLM modes, or mutate the user's checkout. Record Graphify binary/version, graph digest, source inventory, and exact source commit/tree identity.
2. Build the graph from both sides of the gate diff so renamed and deleted source paths retain their old consumers while additions and changed imports use candidate consumers. The graph is accepted only when its baseline identity matches the selected diff base.
3. Treat Graphify extraction errors/failed sources, unrecognized version/schema, unresolved or dynamic local imports, ambiguous module resolution, unsupported constructs, stale graph identity, missing test inventory, and missing source-to-test coverage as uncertain. These conditions select each toolchain's configured full-suite command. Never use a partial result from an uncertain graph. Python imports resolve against the full supported source inventory; unresolved names are ignored only when they are standard-library names or verified declared dependencies. Dart `package:` URIs resolve only when their package name matches the snapshot's declared package and the target exists below `lib/`; imports of verified external dependencies are ignored; relative imports resolve only when the target is unique relative to the importing file.
4. Have `gate_evidence` derive the actual changed paths for task gates and integration gates. For a clean merged candidate, integration uses the exact pre-wave integration commit as the diff base; task gates use the current committed baseline plus the candidate worktree changes. Bind this base, head tree, environment, toolchain commands, and impact policy into the manifest.
5. Make `run-gates` validate the manifest immediately before execution and pass its test argv only for the exact selected toolchain when the manifest proves a complete affected selection. The selected argv must originate from the ledgered descriptor and differ only by safe test-path arguments. Configured analysis and formatting commands retain their existing full scope. Baseline capture and closing verification always execute full configured suites.
6. Recompute and validate the same candidate-bound impact identity after commands finish. Any source, graph, command, or environment drift prevents a passing gate record. Ledger evidence records the selected command and manifest hash.

## Ownership and interfaces

- `test_dependency_graph` owns isolated Graphify invocation, version/schema validation, source/path resolution, graph identity, and completeness diagnostics for Python and Dart/Flutter.
- `gate_evidence` owns the baseline/candidate diff, graph identity, and validated manifest creation.
- `run-gates` and `toolchain_gate` own execution of manifest-selected test argv. Callers cannot submit arbitrary test paths or commands.
- `test_impact` remains the deterministic selector and continues to fail closed to full suites for unsupported or incomplete evidence.

## Verification

- Unit fixtures cover Graphify invocation without LLM modes, version/schema and failed-source rejection, AST relation filtering, Python imports, Dart package/relative imports, URI/path resolution, cycles, rename/delete/add changes, ambiguous or dynamic imports, missing tests, stale identities, and conservative fallback. Disposable CLI probes verify the pinned Graphify behavior without reading or changing user graph artifacts.
- Gate integration tests prove a selected test argv is the command executed, full suite runs for uncertain impact and during closing, analysis remains unchanged, and post-run candidate drift records FAIL rather than PASS.
- Existing shared and Flutter suites must pass on the final candidate. Acceptance remains bound to the final source commit and declared runtime.

## Risks and limits

Static dependency extraction cannot prove arbitrary runtime behavior, and Graphify's AST graph is only as complete as the extractor/version contract. Dynamic and ambiguous dependencies therefore force full suites. Graphify is optional: absent or unvalidated installations retain safe full-suite behavior. This design does not add language or test-framework support beyond the current Python and Flutter/Dart adapters, and does not make closing verification selective.
