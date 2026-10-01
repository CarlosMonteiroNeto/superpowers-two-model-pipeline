# Local template repository and promotion

Reusable assets are staged only in an already existing local repository. The
configured shared destination is `CarlosMonteiroNeto/code-templates`; this
workflow does not create it, clone it, or publish to it. Repository ownership
and visibility must be checked as a separate explicitly authorized operation.

A project binding records an immutable asset version and source identity. Use
`template-repository BINDING.json CANDIDATE.json` to preview added, changed,
and removed paths. Local edits are preserved in the preview. A conflict means
both the local project and candidate changed the same path from the bound base;
resolve it with an explicit merge before rebinding.

`promote-template REQUEST.json CATALOG.json` stages reviewed material under
`.staging/<stage-id>`. It requires matching provenance, known license, API and
test verification, and versioned compatible dependencies with known licenses.
The staging manifest pins asset, version, source identity, license,
dependencies, and included files. Credentials, SQLite databases, embeddings,
private project material, and evidence files are excluded. Repeated identical
promotion is idempotent only when the manifest, exact regular-file inventory,
and every staged UTF-8 payload byte still match. A missing, extra, changed, or
symlinked file causes `overwrite_refused`; the existing stage is left intact
for investigation. The root `release.json` path is reserved for staging
metadata, case-insensitively. Paths that alias after normalization, collide by
case, or make a file both a parent and a child are blocked before writes.

Staging is local and is not publication. Remote creation, visibility changes,
commits to a shared repository, tags, and releases remain separate explicit
operations. Never package TODO or floating dependency versions.
