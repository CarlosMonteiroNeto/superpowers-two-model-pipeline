### Task 3: Resolve pinned task skills and adapted upstream prompt headers

**Summary:** Preserve upstream role practices through versioned adaptation and deterministic prompt assembly.

**Dependencies:** 1, 2

**Files:**
- Production: `skills/two-model-sdd-pipeline/scripts/skill_manifest.py`
- Production: `skills/two-model-sdd-pipeline/scripts/prompt_headers.py`
- Production: `skills/two-model-sdd-pipeline/prompts/upstream-lock.json`
- Production: `skills/two-model-sdd-pipeline/prompts/adaptation-map.json`
- Production: `skills/two-model-sdd-pipeline/prompts/core-operator.md`
- Production: `skills/two-model-sdd-pipeline/prompts/core-reviewer.md`
- Production: `skills/two-model-sdd-pipeline/prompts/core-director.md`
- Test (controller-owned RED): `skills/two-model-sdd-pipeline/tests/test_r2_skill_manifest.py`
- Test (controller-owned RED): `skills/two-model-sdd-pipeline/tests/test_r2_prompt_headers.py`

**Interfaces:**
- Produces: skill_manifest.resolve(selection: dict, bundle: str) -> dict
- Produces: prompt_headers.build(role: str, context: dict, skills: dict, policy: str) -> dict containing text/hash/provenance
- Consumes: R1 bundle resolution; R2 task 1 context; R2 task 2 source registry; explicit planning skill selection

**Acceptance:**
- Pin a verified upstream revision, source hashes and license notices; record each retained/replaced section. Never fetch mutable upstream prompts during task dispatch.
- Resolve installed skills by ID/revision and applicable role/sections from planner selection. Required missing skills block; optional omissions are recorded. No per-task paid skill-selector dispatch or automatic installation.
- Compose role/protocol, authority, adapted core guidance, backend policy, domain skills, task acceptance and output contract in stable order. Preserve mandatory sections under budget pressure; reject oversized required context instead of silently truncating.
- Retain meaningful RED, self-review, independent review, focused scope and structured escalation. Replace worker commits/delegation and interactive approvals with Script CEO contracts. Do not introduce a separate RED approver.
- Record prompt hash and skill/source versions; changed prompt inputs invalidate reuse. Cover conflicts, absent sections, stale hashes, license provenance and backend-independent content.
- Consume the cached skill-source registry from the dedicated discovery task. Search installed skills first, external sources only for missing coverage; user approval is required before installing external skills. Adapt concise relevant upstream guidance rather than pasting every prompt.
- Prompt budget conflicts or ambiguous skill instructions are surfaced before dispatch; source registry discovery does not imply installation or trust.

**Verification command:**

```text
python3 -m unittest discover -s skills/two-model-sdd-pipeline/tests -p 'test_r2_*.py' -v
```

**Additional checks:**
- Capture meaningful failing RED before implementation; retain raw output and final candidate identity.
- Use disposable repositories, fake provider responses and isolated configuration; live inference is opt-in with confirmed models.
- Run affected checks and complete configured suites at closure. New regressions block; proven baseline failures require the explicit waiver contract and must not be reported green.
- Validate both backend paths for shared behavior; mock tests do not certify live capability. Bind round acceptance to the final source commit and declared runtime versions.

**TDD sequence:** Write the named tests before implementation, run them and verify a behavior-specific RED, then implement only the brief, run its verification command and checks, review, and commit. The controller owns RED test files; the implementer must not edit them.

## Controller rulings for the R2.3 interface

- `selection` is a JSON object with `role`, `skills`, and optional `discovery`. Each selected skill carries `id`, immutable content `revision` (`sha256:<hex>`), `required`, applicable `roles`, requested heading names in `sections`, and optional discovery `topics`. Resolve installed files only from `<bundle>/skills/<id>/SKILL.md`; do not fetch or install skills.
- `discovery` carries the R2.2 query and registry path. Pass the installed skill inventory to the existing discovery API first. Keep external candidates advisory, include the R2.2 approval flags, and never add them to resolved prompt content. A required skill missing for the selected role raises `SkillManifestError`; optional missing and role-inapplicable entries are returned in `omissions`. A selected revision that differs from the installed bytes or a requested heading that is absent also blocks resolution.
- Resolved skill entries contain `id`, `revision`, `source_sha256`, `roles`, selected `sections` (`heading` and exact section `content`), and combined selected `content`. Return discovery output and omissions in the same manifest.
- Prompt `context` requires `role_protocol`, `authority`, `task_acceptance`, and `output_contract`; optional `budget_chars` bounds the complete rendered prompt. `skills` is the manifest returned above. Compose these required parts in the accepted order: role/protocol, authority, adapted role core, backend policy, domain skills, task acceptance, output contract.
- `prompt_headers.build` hashes the full UTF-8 prompt as `sha256:<hex>` and reports core/source and selected-skill revisions in `provenance`. It raises `PromptHeaderError` for invalid roles, missing mandatory context, conflicting revisions, or required context beyond budget; it never truncates.
- Source pin ruling: use upstream `obra/superpowers` release tag `v6.3.0` at verified commit `b36e0829c6d0140e93cfef2ca599b1b07d4a7797`, not the locally cached modified fork. The lock must hold raw-source SHA-256 values and the MIT license notice/hash; dispatch is fully offline.

---
