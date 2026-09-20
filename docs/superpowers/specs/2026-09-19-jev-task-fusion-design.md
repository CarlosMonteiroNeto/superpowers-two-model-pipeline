# Jev-assisted task fusion during plan authoring

Date: 2026-09-19
Status: Implemented and reviewed as part of the Jev all-sites rollout. The requirements below remain authoritative. Companion to 2026-09-19-jev-all-sites-design.md following the expanded scope request.

## 1. Objective and scope

Help the strategist combine small, independent, same-shape tasks before finalizing a complete pipeline plan. The intended benefit is fewer task-level full-suite, analysis, and review cycles. Measure the net effect; fewer tasks alone does not establish lower elapsed time or cost, since fusion can reduce parallelism and increase correction scope.

The developer selected shadow recommendations plus manually selected fusion. Here, manual selection means an explicit decision by the interactive strategist during plan authoring, with normal developer design review; it does not introduce a developer approval prompt for every pair or any runtime approval gate.

This companion specifies Site 5 and its initial Choice-capable `jev-classify` foundation. The overall initiative now includes Sites 1–4 under 2026-09-19-jev-all-sites-design.md. The implementation and review are complete in the tracked checkout. Automatic fusion remains outside Site 5's first release, and this companion does not authorize automatic fusion or runtime plan mutation.

## 2. Evidence and current baseline

Inputs: `C:/Users/CARLOS/Downloads/jev-integration-spec.md` and `C:/Users/CARLOS/Downloads/flutter-template-graph.zip`.

The ZIP includes five tool implementations and tests; its newer design reports integration pending. Its older WIRING.md disagrees about whether promotion exists and whether one or two successful adoptions qualify. None of that work is a prerequisite for Site 5. Test pass claims in the archive have not been independently verified in this analysis.

The available pipeline source copy is `C:/Users/CARLOS/Documents/App pipeline`. It contains `touches-overlap`, `brief-scaffold`, scheduling, and routing scripts, but no Git metadata was found. The eventual implementation checkout and baseline revision must be established at execution handoff; this document does not claim the copy is the latest upstream revision.

`touches-overlap WORKSPACE ID [ID...]` reads WORKSPACE/plan.json and checks exact path equality. Its exit codes are 0 disjoint, 1 overlap, 2 invalid input. It does not establish semantic independence or transitive dependency independence. `brief-scaffold` consumes title, summary, acceptance, spec_refs, touches, and depends_on, and rejects test paths in touches.

## 3. Responsibilities and flow

1. The strategist authors a complete draft plan with source references and observable acceptance.
2. A deterministic candidate builder validates the draft and removes mechanically ineligible pairs.
3. `jev-classify` evaluates eligible pairs, returning typed recommendations and raw probabilities.
4. A report records all exclusions and judgments. Shadow operation never modifies the plan.
5. The strategist explicitly selects recommended pairs and supplies their combined title and summary in a selection file.
6. A deterministic applicator validates the selection against the exact source plan and report, rewrites the plan, validates the complete result, and writes a separate output file.
7. Normal design review and plan finalization follow. Phase 3 consumes the finished plan without invoking Jev.

Jev never authors code, summaries, acceptance, dependency edges, review verdicts, or ledger transitions. The strategist owns semantic selection; scripts own structural validation and transformation. No model answer alone authorizes a merge.

## 4. Candidate eligibility

Validate before any network request: unique positive integer task IDs; nonempty title, summary, acceptance, and spec_refs; string arrays for acceptance, spec_refs, and touches; integer dependency IDs; no unknown dependencies, self-dependencies, or dependency cycles. Reject malformed plans instead of treating them as plans with no candidates.

Require canonical repository-relative forward-slash paths without absolute paths, parent traversal, glob patterns, or ambiguous aliases. Fail on noncanonical input rather than silently rewriting task scope. Reject test-like touches using the existing path classification convention.

A pair is eligible only when both tasks have nonempty touches, touches-overlap returns 0, neither transitively depends on the other, and both fit the limits below. Exit 2 from touches-overlap is an input error, never permission to proceed. Exclude corrective tasks (`corrects`) and already-fused tasks (`fused_from`) in this first release.

Proposed initial limits: exactly two source tasks per fusion; at most six distinct implementation paths; at most twelve acceptance entries, counted before deduplication. Shared upstream dependencies are allowed. Reject oversized pairs before inference to avoid unnecessary calls. These are engineering defaults, not measured Jev capabilities.

## 5. Jev judgment and request construction

Retain Choice with options `same_shape_fuse` and `keep_separate`. Define the former as two edits with the same concrete transformation pattern that remain independently testable and can be reviewed coherently together. Different architectural concerns, unclear relationships, or insufficient evidence belong in keep_separate.

State contains each participating task once, including IDs, titles, summaries, touches, acceptance, and spec_refs. Include relevant interface constraints from the plan when present. Each question explicitly names the task state paths in its instructions: question IDs are application bookkeeping and are not visible to the model.

Evaluate independent pair questions together. Proposed local request limits are 32 pairs and 64 KiB of serialized request JSON per request; these are local resource budgets, not provider limits. Split in deterministic pair-ID order. Never truncate task evidence. Report an individual oversized pair as unevaluated and retain its tasks separately. A plan with zero eligible pairs makes zero requests.

The initial recommendation rule is choice=same_shape_fuse and confidence >=0.9. Store the complete distribution as well as confidence. Confidence is distribution concentration, not a measured probability that fusion will succeed. Low-confidence results and service errors preserve the existing separate tasks. In this release the applicator accepts only explicit selections of qualifying recommendations; independent manual plan editing remains the strategist's normal workflow outside this tool.

## 6. Classifier transport, cache, and fallback

Implement a narrow Choice-only adapter against the documented TypeSafe HTTP endpoint. Keep it behind a mockable transport boundary. Use TYPESAFE_API_KEY from the environment, never files committed with the plan or logged headers. No live inference is needed for implementation tests.

Proposed CLI: `jev-classify SCHEMA_FILE STATE_FILE --workspace DIR --site SITE [--threshold N] [--cache-key KEY]`. Workspace is explicit because pre-runtime planning cannot rely on a runtime ledger or branch lookup. SITE isolates per-site cache and circuit state. The schema file contains a model and questions map. Validate threshold as finite and within [0,1].

Exit codes: 0 = valid response and all question confidences meet threshold; 1 = valid response with at least one below threshold, or documented circuit-open fallback; 2 = invalid local invocation/schema/state; 3 = missing setup, transport, timeout, or invalid remote response. Structured output distinguishes answered, unavailable, and circuit-open states. Never fabricate keep_separate model answers for failures.

The Site 5 caller evaluates valid answers individually even when the aggregate exit is 1: an uncertain unrelated pair must not invalidate a confident pair. This deliberately refines the attachment's all-questions confidence contract and must be documented consistently in both CLI and caller tests. Unavailable batches contribute no selectable pairs; local input errors stop the command.

Validate response question identity, Choice types, exact option sets, selected option membership and maximal probability, finite probabilities/confidence in [0,1], probability sums within 1e-6 of 1, and exact returned-model identity against the requested schema model. Reject malformed or model-mismatched responses as unavailable; never partially trust a malformed batch or expose it as a selectable recommendation.

Cache only validated answers. Identity includes canonical state, questions/criteria, requested model, endpoint, and adapter version; a caller-provided key is an additional namespace, not a replacement for content identity. Store the returned model and timestamp. Cached model identity must still match the requested schema model; mismatched cached records are discarded and never selected. Re-evaluate thresholds locally from cached judgments. Cache is confined to a planning workspace, with explicit refresh for new measurements or mutable model aliases.

Proposed timeout: 30 seconds per attempt, at most two attempts per invocation. Retry only transport failures and transient 429/529/5xx responses, with a bounded delay of at most two seconds before the second attempt. Do not retry authentication or request-validation errors. Persist a consecutive failed-invocation count atomically in the planning workspace's Site 5 namespace. On the third unavailable invocation return circuit-open fallback; later calls make no network request until explicit reset. A successful network response resets the count. Cache hits do not prove service recovery. This replaces the attachment's ambiguous branch-scoped fallback with an explicit pre-runtime scope. Runtime sites use the shorter timeout policy in the parent design.

## 7. Selection and deterministic plan transformation

Proposed command surface: `plan-fusion propose DRAFT --workspace DIR --report REPORT` and `plan-fusion apply DRAFT --report REPORT --selection SELECTION --output OUTPUT`.

The report records a canonical draft hash, policy version, candidate pairs, exclusions, request identities, raw judgments, recommendation eligibility, and usage when returned. The selection records that draft hash and report hash, plus selected pairs with strategist-written merged titles, summaries, and short selection rationales.

Reject stale hashes, repeated source tasks across selected pairs, absent/nonqualifying recommendations, changed policies, and duplicate pair selections. Apply is offline; it never performs inference. An empty selection is a valid unchanged-plan result.

For each selected pair, retain the lower source ID and remove the other. Set fused_from to both original IDs. Preserve an immutable source draft in the planning workspace, identified by its hash, so those IDs remain interpretable. Join touches and spec_refs by stable union, concatenate acceptance in source-ID order without deleting entries, and use the explicitly supplied title and summary. Rewrite every downstream dependency through the complete old-to-retained-ID mapping, then deduplicate edges. Preserve unrelated tasks and top-level plan fields. Reject unsupported additional fields on selected tasks unless an explicit merge rule exists; never silently discard interface or task metadata.

Compatibility correction during plan authoring: the inspected route-next uses task+1 and compares task IDs to task count. Sparse IDs are therefore unsupported on the serial path. After contraction, perform a stable topological sort (source ID breaks ties), assign consecutive IDs 1..N, and rewrite all dependency references through the final mapping. Preserve original draft IDs in fused_from and in a report source_id_map for every task, together with the immutable source-draft hash. This renumbers unrelated tasks only in the new, pre-runtime output; no existing runtime state may be reused with it. Verify brief-scaffold, serial advancement, and wave scheduling against the resulting consecutive IDs. Do not modify route-next to accommodate fusion.

Validate the entire transformed DAG after all pairs are contracted. Individually independent pairs may collectively form a cycle: with A->B and C->D dependencies, merging A with D and B with C creates a cycle. Reject the complete selection without a partial write.

Write OUTPUT atomically and only when distinct from the input and runtime workspace plan. Refuse overwrite unless an explicit flag is supplied. The input stays byte-identical. Applying the same selection to the same source produces identical plan bytes. No recursive/group fusion in this release.

## 8. Audit and evaluation

Store planning reports separately from the runtime ledger. fused_from in the finalized plan is provenance, not an authorization or verdict. Reports record whether a pair was merely suggested, selected, or actually executed as a fused task.

Shadow evidence measures recommendation agreement with strategist decisions. It cannot establish the counterfactual review outcome of an unexecuted fusion. For executed fusions, collect observed review outcomes and corrective episodes in an offline evaluation report with references to existing runtime evidence; do not change runtime logging or automatically attribute every SEND_BACK to fusion.

Track evaluated pairs, positive recommendations, selections, observed fused executions, attributed fusion failures, model/request versions, token usage, and timings where evidence exists. Report missing evidence explicitly. Runtime cost comparisons must account for parallelism and integration batching already present. No sample count or confidence threshold automatically enables autonomous application in this release.

## 9. Proposed implementation boundaries and verification

Keep provider handling (`jev-classify` plus a Python module), plan validation/candidate construction, and plan transformation as separate modules under skills/two-model-sdd-pipeline/scripts. Reuse touches-overlap and existing path classification rather than changing their semantics. Add the planning entry points to writing-plans and the Flutter Phase 2c documentation, plus README-LLM.md and README.txt. No template-graph installation or runtime dispatcher changes.

Verification must cover classifier exits, malformed responses, partial confidence, content-addressed caching, circuit persistence, no-network cache/zero-candidate paths, exact overlap, indirect dependency exclusion, caps, stale selection rejection, stable provenance, spec_refs/acceptance preservation, global cycle creation, sparse IDs, unknown metadata rejection, atomic failure behavior, and Windows paths with spaces. Use mocked TypeSafe responses; genuine calibration is a separate measured activity and must never be claimed from fixtures.

Existing brief-scaffold and scheduling consumers must accept the resulting plan unchanged. New tests must prove observable behavior rather than mirror implementation. Follow the current pipeline's convention that newly authored tests are not listed in task touches. Skill edits require the skill-authoring verification workflow at implementation time.

## 10. Implementation and review status

The selected approach and detailed defaults above were reviewed and implemented: pair/file/acceptance caps, per-answer handling of aggregate exit 1, explicit planning-workspace scope, retry/circuit policy, and strategist selection semantics.

The complete plan.json records title, summary, acceptance, spec_refs, touches, and depends_on for every task; it contains no expected_red. Its task acceptance and the immutable requirements above remain unchanged by this status update.

## References

- TypeSafe API: https://docs.typesafe.ai/api
- Choice: https://docs.typesafe.ai/primitives/choice
- Confidence: https://docs.typesafe.ai/confidence
- Parallel questions: https://docs.typesafe.ai/patterns/fan-out
- Mechanical filtering before semantic evaluation: https://docs.typesafe.ai/cookbooks/citation_check
- Local pipeline: README-LLM.md; skills/two-model-sdd-pipeline/scripts/touches-overlap; skills/two-model-sdd-pipeline/scripts/brief-scaffold.
