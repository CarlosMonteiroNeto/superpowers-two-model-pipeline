# Jev integration across all five decision sites

Date: 2026-09-19
Status: Implemented and reviewed for the shared Jev foundation, template foundation, and Sites 1–4. Site 5 selected fusion is implemented and reviewed as part of the same rollout. The requirements below remain authoritative.

## 1. Confirmed scope and implementation order

The developer expanded the original Site 5-only request to all five sites. Site 5 remains first. Its selected mode is shadow recommendations plus explicit strategist-selected fusion. For Site 4, the developer explicitly selected review-depth selection with the reviewer always running.

Deliver in this order:

1. Shared Jev Choice adapter and Site 5 task fusion.
2. Template research foundation required by Sites 1 and 2, using the supplied ZIP as implementation reference.
3. Site 1 catalog triage, then Site 2 recall validation.
4. Site 3 director prompt selection using Option A.
5. Site 4 reviewer depth selection without bypass.

The full implementation plan must describe every stage before execution; this ordering is not runtime plan expansion. Independent testable deliverables may have separate tasks and appropriate dependency edges.

Do not implement Site 3 Option B, automatic task fusion, Jev-generated review approval, or an alternative runtime router. Package promotion is not a prerequisite of any Jev site and is excluded from the template foundation. Implementation and review are complete in the tracked checkout; live TypeSafe calls remain disabled for tests and default shadow-mode paths, and installation, publication, and pipeline launch remain outside this artifact.

## 2. Evidence and design deltas

Sources are the attached jev-integration-spec.md, flutter-template-graph.zip, TypeSafe's live documentation, and the available App pipeline source copy. The local copy has no Git metadata, so its revision is unverified.

The archive includes code for catalog, embeddings, recall, refresh, and promotion, but its integration instructions are stale. Treat code and instructions as reference material, not authorization to install or run them. Existing test-success claims in the archive have not been verified here.

The original Jev document leaves Site 2 unspecified beyond its freshness/HIT boundary and excludes Site 4 pre-approval. Section 7 below is a new proposed contract for Site 2. Section 9 implements the developer-confirmed Site 4 alternative, not pre-approval.

Inspection places Site 3's actionable integration point in task-run, where CORRECTIVE and ARBITRATE construct prompts and dispatch the director. The current prompts are already short, mostly referring to artifacts. Do not promise token savings from shortening these strings; measure the director's full usage and preserve its evidence requirements.

Reviewer dispatch exists in both generic coder-gate and Flutter green-gate. A shared review-package preparation boundary should serve Site 4 so the two paths cannot diverge. Preserve the existing mandatory review coverage and verdict parser.

## 3. Shared boundaries and trust

Jev supplies semantic judgments only. Scripts enforce rules, thresholds, artifact validity, and routing. The director continues to rule on all corrective/arbitration episodes; the reviewer remains the sole independent semantic approval authority. Jev cannot write authoritative review, task_complete, corrective-resolution, or gate-success entries.

Implement Choice only initially; no site here requires a general framework for every TypeSafe primitive. Typed responses establish shape, not truth. The API adapter returns each selected option, its full distribution, confidence, returned model identity, and usage when available. The returned model identity must exactly match the requested schema model for both live responses and cached envelopes; a mismatch is a provider/config/setup failure and yields no selectable recommendation. Questions explicitly identify the state they concern; IDs alone do not convey context to Jev.

Every site has a versioned question schema and independent policy. Support off, shadow, and active modes for Sites 1–4. Default all four to shadow: compute observations while preserving existing decisions. Off makes no API calls. Active mode requires an explicit policy configuration bound to the evaluated model, question version, and a calibration report. That report records labeled cases, false-positive errors, coverage, latency, and cost; it does not claim a universal sample count proves safety. No observed-data threshold automatically activates a site.

Site 5 has shadow and selected-apply modes only. It never enables automatic fusion, regardless of confidence or calibration. Its numerical limits and transformation contract are in the companion specification.

Provisional active recommendation confidence is 0.9 for Sites 1–4 as well as Site 5. This is an initial policy value for evaluation, not a measured accuracy guarantee. Shadow records the complete response even below threshold. An active site uses only its own relevant question's valid answer; low confidence elsewhere in the batch does not invalidate it. Local deterministic exclusions always override a model recommendation.

## 4. Shared transport, persistence, and degradation

Use the companion's classifier exit table, strict response validation, content-addressed cache, and explicit workspace argument. Add mandatory --site to isolate caches, schemas, and circuit state. Cache identity includes model, endpoint, question semantics, and complete state; caller keys never override that identity. Store raw responses privately in workspace artifacts, never API keys or Authorization headers. Reject a live or cached response whose model identity differs from the requested schema model, and treat it as unavailable setup/provider data. Do not transmit code, catalog text, or planning material until inference is actually invoked during the authorized implementation/use phase.

Planning calls use the companion's bounded retry policy. Runtime Sites 3 and 4 use one attempt with a ten-second timeout and no inline retry, so an optional optimization does not create a minute-long delay before a mandatory dispatch. Timeouts and payload budgets are local defaults to be tested, not claims about provider limits.

Maintain the three-failed-invocation circuit per site and workspace, with explicit reset. Runtime worktree workspaces naturally isolate task execution; no unsynchronized shared branch-wide counter. Persist updates atomically and serialize writes within a namespace. Interrupted/corrupt cache records are never trusted as valid answers. No changes to the runtime ledger writer are needed for advisory telemetry.

Usage errors in a directly invoked research/planning command return a nonzero exit with a clear diagnostic. When an optional Jev hook fails inside an existing runtime path, record its failure in advisory artifacts and proceed with the original full prompt/package. A successful fallback never claims Jev succeeded. Failure to construct the original required package remains an existing pipeline error, not a Jev fallback success.

Advisory records contain site, schema/policy version, state identity, cache status, decision, confidence, actual action, fallback reason, duration, and usage where supplied. They are not routing state and must not be interpreted by route-next. Use task/episode/content identities, not one mutable shared latest file, so worktree concurrency and retries remain auditable.

## 5. Site 5 — plan-authoring task fusion

Apply the companion specification, 2026-09-19-jev-task-fusion-design.md. Key constraints: mechanical overlap and transitive dependency filtering before inference; explicit strategist selection; two-task fusion; six-file and twelve-acceptance-item proposed limits; source-plan identity; complete dependency rewrite and post-merge DAG validation; preserved spec_refs and acceptance; fused_from provenance.

No runtime fusion hook. Reject stale selections. Do not infer successful fused review outcomes from tasks that ran separately. Keep shadow agreement and actual fusion outcomes as different measurements. Existing runtime consumers must accept the resulting plan without changes to routing invariants.

## 6. Template foundation and Site 1 — catalog triage

Integrate catalog, embedding, recall, and refresh capabilities needed by Sites 1 and 2. First repair their contracts against the current scoring script: the inspected template_score.py has no --with-text interface, while the Jev attachment assumes one. Provide a tested evidence collection boundary yielding score report, README, pubspec, and tree data; preserve existing scoring outputs for existing callers. Do not assume the ZIP can be copied into the pipeline unchanged.

Catalog stores the scoring verdict separately from the Jev triage decision, confidence, evidence identity, policy version, and decision actor. Its update path must preserve existing database contents and invalidate stale derived judgments when source evidence changes. An add-time decided-by field must not masquerade as a scoring verdict or user adoption.

Trigger Site 1 only for a deterministic DEVELOPER_DECISION result. AUTO_REJECT is never promoted by Jev; AUTO_APPROVE retains its existing path. State includes the full score report, evidence text, all Category Skeleton fields, and mechanically derived constraints such as SDK/license status. Missing required evidence or failed explicit constraints prevents automatic positive triage.

Choice options: adopt, reject, needs_review. Define adopt narrowly as accept into the research shortlist/catalog, not select a template for a project or clone/install it. Developer template selection at Phase 2b remains required. The original attachment's language conflates catalog acceptance and adoption; this design separates them.

In active mode, confident adopt/reject records that triage outcome, tagged decided_by=jev. Keep rejected candidates with their reason/provenance for audit, excluding them from the default shortlist. needs_review, low confidence, unavailable inference, or unmet calibration policy uses existing developer/strategist triage. In shadow mode record both the Jev proposal and the actual existing-path decision; Jev does not hide or adopt candidates.

Validate catalog schema migration, idempotent upserts, stale triage invalidation, missing Category Skeleton/evidence, and unchanged Phase 2b selection behavior. No runtime ledger writes or automatic code downloads.

## 7. Site 2 — recall suitability after deterministic freshness checks

This is a proposed definition because the attachment does not include its original detailed Site 2 design.

Keep freshness authoritative and deterministic. Only fresh, currently AUTO_APPROVE-scored candidates may support RECALL_HIT. A Site 1 accept into the shortlist is not AUTO_APPROVE. Jev must never make a stale row fresh, relax a timestamp limit, or manufacture missing upstream evidence.

Mechanically validate the catalog and rank eligible candidates before taking top-N. This corrects the archive's order, which truncates first and can hide fresh eligible rows behind stale ones. With embeddings enabled, use package overlap as the primary ordering and similarity as the secondary ordering, then a stable repository tie-breaker. The archived vector reranking can otherwise replace the package-overlap order. Version embeddings by model and source-content identity; a text update or model change invalidates stale vectors. Without query text, embeddings remain optional.

For each eligible recalled candidate, Jev receives the current Category Skeleton, intended use, declared dependencies, and stored evidence used in scoring. Choice options: suitable, unsuitable, needs_review. The semantic question is whether this candidate fits the present project, not whether it is fresh. Evaluate candidates together under the shared request budget.

In active mode, keep confident suitable candidates. Confident unsuitable candidates do not support a HIT for this query but are not deleted from the catalog. If at least one suitable candidate remains, return HIT with that shortlist. If no suitable candidate remains, run the existing live-search fallback; annotate uncertainty separately from confident rejection. In shadow/off modes, preserve the deterministic recall outcome. Provider failure falls back to the deterministic recall outcome with explicit unavailable telemetry, not a failed pipeline. A broken catalog or missing required embedding setup remains a distinct setup error, not a fabricated MISS.

Refresh operates against real scoring data; it runs on explicit stale-entry refresh before recall as a planning operation, not inside the runtime task loop. Jev does not decide whether upstream quality changed. Preserve documented recall exit meanings: 0 HIT, 2 MISS, 1 setup/domain failure.

Validate stale/fresh boundaries, eligibility-before-truncation, optional embeddings, incompatible/stale vectors, stable ranking, all-unsuitable fallback, uncertain cases, and provider unavailability.

## 8. Site 3 — director prompt selection, Option A

Hook before dispatch_task_generator at the existing CORRECTIVE and ARBITRATE sites in task-run. State is the actual target task, structured findings/escalation reason, cited spec constraints, and evidence identifying the episode. Read authoritative artifacts; never classify raw log fragments alone when the structured evidence exists.

Choice options: local_mechanical_correction, architectural_disagreement, test_noise_or_unclear. Jev's label does not close an episode or determine a verdict. For CORRECTIVE, a calibrated, confident local_mechanical_correction may select a focused prompt; every other result selects the standard prompt. ARBITRATE always retains the full viability context and director ruling; a semantic label may add a focus hint but cannot shrink its mandatory evidence.

Both prompts require access to the full plan, target task, original findings, and cited spec material. A focused prompt narrows the question and removes duplicated instructions, never facts needed to detect that the correction is unsafe. The director can reject Jev's characterization. Do not add automatic retries of the operator in place of a director dispatch.

In shadow mode dispatch the existing prompt and record the hypothetical selection. In active mode build the selected prompt deterministically and still use the existing dispatch tool, agent, and episode lifecycle. Failure uses the original prompt. Existing corrective creation, scope checks, reconciliation, and arbitration boundaries are unchanged.

Measure full director usage and outcome, not just prompt-file size. The current prompts are already concise; ship correctness without claiming savings until measured. Test all labels, threshold boundaries, shadow/off paths, provider failure, mandatory dispatch counts, and unchanged authoritative ledger transitions.

## 9. Site 4 — reviewer depth selection, never pre-approval

The developer explicitly confirmed that the reviewer always runs. Implement a shared preparation step around the existing review-package boundary, used by generic and Flutter paths after their existing gates. Do not introduce a second reviewer-dispatch implementation.

State contains the complete task brief and full review diff, including tests, along with available interface-touch and corrective context. Apply a local 64 KiB request budget. If complete evidence cannot fit, skip inference and select standard review; never truncate evidence to make a compact review eligible.

Choice options: focused_review, standard_review. Focused review is eligible only for a calibrated, confident focused_review answer and no deterministic exclusion. Corrective tasks, tasks with fused_from, and tasks with a recorded interface_touched advisory always use standard review in this first release.

Both paths deliver the unchanged full brief and diff to the same reviewer and require all four existing duties: spec compliance, architecture, interface discipline, and tests versus acceptance. Focused review changes instruction verbosity and attention guidance, not mandatory coverage, evidence, output schema, or approval criteria. The reviewer can deepen inspection when it identifies a named risk. No model/agent substitution or reduced reasoning setting is implied.

Do not present Jev's prediction as evidence that the code is correct. Avoid reviewer anchoring: give procedural focus guidance, not an approval probability or predicted verdict. Keep the raw classification in the advisory artifact for evaluation.

Shadow uses standard review and records the hypothetical depth. Active may select focused instructions; errors or uncertainty select standard review. Mandatory dispatch and parsed reviewer verdict remain authoritative. Test both dispatch paths, full-evidence preservation, exclusions, missing/oversized input, failures, and unchanged review_outcome/task_complete semantics.

## 10. Verification and documentation

All provider tests use mocked responses, with no credentials or live calls required. Exercise response validation, four classifier exits, bounded retry/timeout, site-isolated circuit state, concurrent artifact writes, cache invalidation, and per-question confidence handling.

Integration tests cover all-site off mode matching current behavior, shadow mode leaving decisions unchanged, calibrated active policies, and unavailable service fallback. Verify generic and Flutter review paths share the same mandatory-review behavior. Test Windows paths with spaces and existing command-runner conventions. Separate measured model quality from passing mocked contract tests.

Update the pipeline skills, README-LLM.md, README.txt, and relevant prompt documentation in the same implementation tasks as their behavior changes. Apply skill-authoring verification to skill edits. Record the trust-tier and no-bypass design as a proposed ADR for review without inventing an available ADR number or marking it accepted prematurely.

Existing runtime verdicts and ledger routing types remain unchanged. Advisory telemetry is separate. Plan acceptance must explicitly cover these invariants rather than rely on a prose promise.

## 11. Implementation and review status

The expanded design was reviewed before authoring the executable plan.json. The Site 2 suitability contract and Site 1 definition of adopt as shortlist acceptance were carried into the implementation and review. Site 3 uses Option A. Site 4 reviewer preservation and Site 5 selected fusion remain confirmed requirements.

The complete plan covers all stages with tasks, acceptance, spec_refs, exclusive implementation touches, and depends_on; no expected_red. Tests remain verification requirements rather than test-like touches, following brief-scaffold's current contract. The shared foundation, template foundation, and Sites 1–4 are implemented and reviewed in the tracked checkout, with Site 5 selected fusion reviewed alongside them.

## Sources

- Companion: 2026-09-19-jev-task-fusion-design.md.
- Attached inputs: C:/Users/CARLOS/Downloads/jev-integration-spec.md and C:/Users/CARLOS/Downloads/flutter-template-graph.zip.
- TypeSafe API: https://docs.typesafe.ai/api
- Choice and confidence: https://docs.typesafe.ai/primitives/choice and https://docs.typesafe.ai/confidence
- Batch independent questions: https://docs.typesafe.ai/patterns/fan-out
- Mechanical filtering before inference: https://docs.typesafe.ai/cookbooks/citation_check
- Local integration points: skills/two-model-sdd-pipeline/scripts/task-run, coder-gate, review-package; skills/flutter-app-pipeline/scripts/green-gate and template_score.py.
