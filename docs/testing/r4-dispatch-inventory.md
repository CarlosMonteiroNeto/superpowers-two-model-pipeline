# R4 semantic dispatch inventory

Each row identifies the script that owns one external semantic invocation. A
RED/GREEN test run, formatter, route calculation, or transport retry is not an
additional semantic dispatch.

| Site | Semantic invocation | Owner | Budget and termination |
| --- | --- | --- | --- |
| Generic or Flutter initial task | Operator on the scaffolded brief | Shared `red-gate` dispatches through `dispatch-retry`; Flutter has its own language gate but the same operator adapter | One external operator reservation; `coder-gate` then validates RED/GREEN |
| Failed RED/GREEN gate | Operator correction in the recorded task family | Shared `coder-gate` through `dispatch-retry` | Each new external invocation reserves once; exhaustion returns to the director |
| In-scope reviewer SEND_BACK | Same task-family operator | `route-next` applies `correction_policy`; `task-run` dispatches the direct correction | No director invocation; same family budget; independent review follows the next committed candidate |
| Structural or uncertain SEND_BACK | Director, then corrective operator when approved | `task-run` invokes the director and validates the canonical plan transaction; the child dispatch uses `dispatch-retry` | Corrective child inherits the family budget and operator session only when its recorded family matches |
| ESCALATE, TEST_DEFECT or exhausted coder cycle | Director assessment | `task-run` owns the director dispatch | A cycle assessment permits the next configured cycle; after the third exhausted cycle, unresolved work pauses |
| Generic or Flutter committed candidate | Independent reviewer | Shared `review-dispatch` owns the candidate-bound review; `orchestrator` owns the Codex normalization call | Reviewer transport failure preserves the pending candidate and never requests new coding |
| Whole branch | Independent closing director | Existing `final-gate` closing path | Runs after task review and full-suite verification; no operator budget charge |

`dispatch_budget` counts external operator identities, not internal operator
turns. The Codex adapter reserves at dispatch with the configured
`coder_cycle_limits`; OpenCode reads `run-manifest.json` or the explicit
`PIPELINE_CODER_CYCLE_LIMITS` JSON launch setting (default `[5,3,3]`) and its
retry seam reserves once for each operator
call and reuses that reservation across transport retries. A confirmed Codex
pre-start failure releases its reservation and increments transport attempts.
Ambiguous post-start failures retain their reservation for reconciliation.
The registry is keyed by run and task family, so corrective children and scope
revisions do not reset counts.

Scope extensions require a supervisor-issued registry record signed with the
controller-only `PIPELINE_SCOPE_GRANT_KEY` (at least 32 random bytes encoded as
hex). The key is supplied to controller scripts before grant issuance and
routing; neither worker adapter passes it to its model process. Without the
key, or with an unsigned, altered, stale, or wrong-attempt record, the router
does not extend the task scope. The legacy candidate state remains durable
after review dispatch so routing can bind the grant to the reviewed commit.

An interrupted direct correction remains at `DIRECT_FIX_RECONCILE`; task-run
does not start another operator. The controller can recover a completed result
by writing a supervisor disposition with the exact fields from
`task-N-direct-fix-intent.json`, plus `issuer=supervisor`, a `decision_id`,
`outcome=completed`, and an `evidence_path`/`evidence_sha256` pair. It then runs
`python3 scripts/direct_fix_reconcile.py reconcile WORKSPACE TASK DISPOSITION.json`.
The command verifies identity and evidence and appends the dispatch boundary
once; the next route enters the coder gate without a new operator invocation.
An uncertain result stays blocked until the supervisor can establish its
outcome. The operator reservation is retained throughout.

Legacy OpenCode review uses a candidate/package-bound claim before launch. An
ambiguous claim blocks duplicate review. To recover a completed reviewer
result, the supervisor supplies the fields from the claim plus the same
issuer, decision, outcome, and evidence fields to
`python3 scripts/legacy_review_claim.py reconcile WORKSPACE TASK CANDIDATE DISPOSITION.json`.
The next `review-dispatch --legacy` call records completion without launching
another reviewer.
