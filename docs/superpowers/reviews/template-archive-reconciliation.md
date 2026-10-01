# Archived reusable-asset behavior reconciliation

This review records what the earlier Flutter template lifecycle contributes to
R5 and why each responsibility remains shared or ecosystem-specific. The
archive is a behavior reference only; its implementation is not copied as a
new shared implementation.

| Archived/current behavior | R5 owner | Disposition and preserved contract |
|---|---|---|
| Flutter template SQLite catalog and evidence migration | `asset_catalog.py` plus `template_catalog.py` adapter | Shared identity/provenance/outcomes; legacy table, CLI, and missing-hash recall ineligibility remain compatible. Migration is versioned, backed up, transactional, and rollback-tested. |
| Fresh deterministic template recall and optional vectors | `asset_recall.py` plus `template_recall.py` adapter | Shared read-only filtering, freshness, compatibility, dependency overlap, vector identity, and MISS/SETUP_ERROR distinction. Flutter package overlap/vector records and CLI exits remain adapter behavior. Recall never downloads or adopts source. |
| Explicit evidence refresh | Shared `asset_recall.refresh` plus Flutter evidence collection | Validate complete fresh evidence before one atomic generic/legacy update. Collection/validation failure preserves existing rows. |
| GitHub/pub.dev candidate search and numeric scores | `template_score.py` / `pkg_score.py` | Remain provider-specific, preserve formulas and stop rules; append normalized provenance/evidence records without using Flutter scores as generic policy. |
| Flutter package manifest and lock writes | `dependency_policy.py` called by `pub-sync` | Keep existing Flutter commands; require the shared exclusive manifest lock. Policy API separately enforces explicit path grants and compatibility/license/version evidence. |
| Optional Jev suitability | `recall_suitability.py` | Stays an advisory Flutter hook over deterministic eligible candidates; cannot write catalog state, select assets, or approve adoption. |
| RTK-compressed Flutter commands | `rtk-run` through shared `cmd` | Keep the existing Flutter mode allowlist and output files; no added inference or dispatch stage. |
| Project/template update behavior | `template_repository.py` | Replace in-place mutation with immutable version binding and a read-only diff preview. Local edits survive; overlapping changes are surfaced for explicit merge. |
| Shared template promotion | `template_promotion.py` | Stage only in an existing local repository; verify provenance/license/API/tests/dependencies; exclude private evidence and caches; duplicate identity is idempotent and changed payload overwrite is refused. Publication remains separate. |
| Brainstorming/planning task context | R5 planning reference and skills | Resolve installed skills and applicable profiles first; summarize immutable assets and exceptions. Cached external sources fill gaps; installing an external skill still requires explicit approval. |

No external repository was created, no shared asset was published, and no new
language ecosystem is declared production-supported by the Python fixtures.
