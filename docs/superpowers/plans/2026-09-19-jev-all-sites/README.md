# Jev integration planning handoff

The complete machine-readable implementation plan is `plan.json`. It contains eight tasks; the shared Jev foundation, template foundation, Site 5 fusion, and Sites 1–4 are implemented and reviewed. The task acceptance recorded in `plan.json` remains immutable.

| Task | Deliverable |
| --- | --- |
| 1 | Choice adapter, isolated cache/circuit, policies, advisory records and offline evaluation |
| 2 | Site 5 recommendations and explicit selected fusion |
| 3 | Template catalog and complete scoring evidence |
| 4 | Site 1 shortlist triage |
| 5 | Deterministic recall, optional embeddings and refresh |
| 6 | Site 2 suitability assessment |
| 7 | Site 3 director prompt selection, mandatory director dispatch |
| 8 | Site 4 review guidance, mandatory reviewer dispatch and all-site verification |

Read both specs under docs/superpowers/specs: `2026-09-19-jev-all-sites-design.md` and `2026-09-19-jev-task-fusion-design.md`.

## Compatibility correction

The current serial router uses task+1 and compares IDs with task count. Fusion must therefore produce consecutive IDs through a stable topological ordering, while preserving original source IDs and rewriting dependencies. The companion spec was corrected during plan authoring. No runtime routing change is required.

## Verification performed

The saved plan parsed as JSON. All eight tasks have required fields, consecutive IDs and acyclic ordered dependencies. All sixteen spec references resolve to existing headings. No test-like paths appear in touches; repeated documentation paths are deliberately ordered. No TODO/TBD placeholders were found. The existing brief-scaffold successfully generated all eight briefs in a disposable workspace and preserved every acceptance item.

These are planning-artifact checks, not implementation tests or evidence of Jev accuracy. Implementation and review were completed in the tracked checkout with mocked provider tests; live inference remains disabled in tests and default shadow-mode paths.

## Implementation and review status

Implementation and review were performed in the tracked checkout after rechecking interfaces against its baseline. The shared foundation, template foundation, Site 5 fusion, and Sites 1–4 retain the delivery order and constraints recorded in the plan. Use a stable external controller for any future self-hosted pipeline run and resolve actual Python/Bash gates rather than assuming Flutter commands for the pipeline repository.

The current pipeline-workspace derives identity from the plan basename. This artifact is named plan.json; for any future execution, use a uniquely named tracked plan copy such as `2026-09-19-jev-all-sites-plan.json`, and establish a fresh matching workspace. Do not reuse a ledger from another plan named plan.json.

The user selected all five sites, Site 5 first, and mandatory Site 4 reviewer dispatch. Sites 1–4 default to shadow. Runtime active modes require explicit policy and calibration evidence. Site 5 remains explicit selected application. This handoff records the completed implementation and review; publication remains outside the artifact.
