# R5.1 — Flutter capability ownership audit

**Status:** Source-backed inventory completed against the accepted R4 baseline `817da04e7d92983bb33cecdc38115b4babeceb7a`.
**Machine-readable detail:** [`stage-capabilities.json`](../../../skills/two-model-sdd-pipeline/stage-capabilities.json)
**Schema:** [`stage-capability.schema.json`](../../../skills/two-model-sdd-pipeline/schemas/stage-capability.schema.json)
**Coverage test:** [`test_r5_stage_inventory.py`](../../../skills/two-model-sdd-pipeline/tests/test_r5_stage_inventory.py)

## Scope and method

The audit read the Flutter specialization, its current command wrappers and
Python implementations, test callers, the shared skill entrypoints, and the
confirmed decisions for R5. The inventory records all nine stages (phase 0
through phase 8, IDs `phase-0` to `phase-8`) and all 24 scripts (24 files) in
`skills/flutter-app-pipeline/scripts/`. Each capability names its source,
current and target owner, disposition, R5 task or accepted-round owner, evidence,
and callers. The focused test checks stage coverage, script-file coverage,
source existence, task ownership, scope claims, and the inventory's schema
contract and internal references.

## Disposition summary

| Stage | Current responsibility | Ownership decision | Plan mapping |
|---|---|---|---|
| Phase 0 | Flutter specialization entry over the shared harness | Adapt planning entry; retain a Flutter specialization | R5.7 |
| Phase 1 | Commercial/technical requirements and UI guidance | Resolve applicable requirements generically; keep Flutter UI rules as an overlay | R5.4 |
| Phase 2 | Package/template research, catalog, evidence, recall, scoring and selection | Generalize asset identity, recall, and evidence lifecycle; preserve provider and ecosystem scoring adapters | R5.2, R5.3, R5.6 |
| Phase 3 | Dependency resolution, RED/GREEN, review and command evidence | Keep accepted shared gates/review ownership; add shared dependency policy and retain Flutter command adapters | R3.2, R4.4, R5.6 |
| Phase 4 | Project-wide gates and review | Keep accepted shared closing gate; apply Flutter UI acceptance as a specialization | R3.4 |
| Phase 5 | Deterministic script entrypoints | Generalize reusable lifecycle contracts and preserve existing Flutter CLI behavior | R5.2, R5.3, R5.6, R5.7 |
| Phase 6 | pub.dev/GitHub data and score formulas | Keep provider metrics and Flutter/Dart readiness scoring in Flutter adapters | R5.6 |
| Phase 7 | GitHub token setup and use | Share secret-safe policy; keep provider-specific authentication handling in adapters | R5.6 |
| Phase 8 | End-to-end Flutter flow summary | Compose generic research, profiles, adoption and planning with the Flutter overlay | R5.7 |

## Findings that constrain implementation

- `template_catalog.py` and `template_evidence.py` own ecosystem-specific
  compatibility and evidence mapping today. R5.2 should move generic asset
  identity, provenance and outcome storage into the shared catalog while
  migrating existing SQLite state transactionally and preserving the Flutter
  command contract.
- Recall, refresh, embedding identity and suitability are separate concerns.
  R5.3 owns deterministic shared eligibility and atomic refresh; Flutter
  provider evidence, scoring filters, and the optional Jev suitability boundary
  remain adapters. Recall must stay read-only and offline.
- `pkg_score.py` and `template_score.py` encode pub.dev/GitHub metrics and
  Flutter/Dart readiness. Those formulas remain Flutter-specific; shared
  research consumes normalized evidence rather than embedding provider scores
  into generic ranking.
- `red-gate` delegates to the accepted shared gate. `green-gate` and `rtk-run`
  are Flutter command/evidence adapters over the shared gate and runner. R5
  should preserve those entrypoints rather than fork gate or review policy.
- `pub-sync` mutates Flutter dependency manifests and the lockfile. R5.6 adds
  shared compatibility/license/resource policy around ecosystem execution;
  it does not move Dart tooling into the shared engine or bypass existing write
  ownership.
- R5.4 profiles apply only when product context supports them. The Flutter
  forms overlay cannot add UI, locale, country, authentication, payment, or
  analytics requirements to unrelated products.

The inventory maps each disposition to R5 tasks 2–7 or accepted R1–R4 owners.
It does not authorize an unplanned material scope change. This review does not
claim new ecosystem support; generic fixtures verify contract behavior only.
