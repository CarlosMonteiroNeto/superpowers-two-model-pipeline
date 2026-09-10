# Design: Agente diretor architecture (Agente estratégico ends at plan+spec)

Date: 2026-09-10. Brainstormed (architectural path) with the developer.
Supersedes: estrategista-authored briefs/RED (controller-brief-prompt.md
era), corrective briefs by Agente estratégico, fresh-session holistic
review by Agente estratégico.

Actor names (display): Script CEO (= Script A), Agente estratégico (= B),
Agente diretor (= task creator), Agente operador (= coder),
Agente revisor (= reviewer). Machine identifiers (`two-model-coder`,
`coder_round`, flags, paths) are unchanged.

## Roles after this change

- **Agente estratégico:** writes plan shell + spec, then DONE. No briefs,
  no RED tests, no corrective briefs, no arbitration, no reviews.
- **Agente diretor** (new agent, `two-model-task-generator`, Strategic
  tier): dispatched once per branch by Script CEO. Expands the plan shell
  into full tasks (all at once), appends corrective tasks on demand,
  performs branch closing. Session id recorded; resumed (`--continue`)
  only for corrective tasks and closing — zero cost in between. Receives
  task text + findings only, never diffs/logs/gate output.
- **Agente operador** (Operational, write-only): receives scaffolded brief,
  writes RED tests AND implementation in one session. Never runs commands.
- **Agente revisor** (Strategic): reviews diff + judges whether the tests
  encode the task's acceptance (new scope item). Returns JSON verdict.
- **Script CEO:** owns every transition and every verification, receives
  every operator/revisor output, scaffolds briefs, routes next task until
  done. Invokable anywhere as `scripts/run-pipeline PLAN_FILE [TOTAL]`.

## plan.json (enriched, permanent)

Agente estratégico writes the shell (`feature`, `spec_doc`,
`global_constraints`, empty `tasks`). Agente diretor fills `tasks[]`:

```json
{
  "id": 3, "title": "short imperative title",
  "summary": "2-3 sentences: what and why",
  "spec_refs": ["spec section ids the task implements"],
  "touches": ["src/foo.ts"],
  "depends_on": [1, 2],
  "acceptance": ["observable behavior that must hold"],
  "expected_red": "verbatim substring the failing output must contain",
  "corrects": null
}
```

Corrective tasks append with the next integer id and `"corrects": <id>`.
No `task-N-task.md` files — the plan is the only task record (permanent,
tracked under `docs/superpowers/plans/`).

## Brief scaffolding (script, transient)

New script `brief-scaffold WS TASK` reads the task from `<ws>/plan.json`
and writes `<ws>/task-N-brief.md` mechanically: statement (title+summary),
exact-values placeholder (from `touches`/acceptance — no LLM), acceptance
list, `EXPECTED-RED:` (from task), out-of-scope fence, plus the
RED-authorship order for the operador (tests first, per
writing-good-tests.md). Usage error (exit 2) when the task lacks required
fields. Briefs stay workspace-transient by decision.

## RED authorship by Agente operador (single dispatch, script-proved)

Per task: dispatch operador with the scaffolded brief. Operador writes
tests + code, reports DONE. Then coder-gate, on first green of the task,
runs the **RED-proof** before committing:

1. Snapshot hashes of the new test files (changed files NOT in `touches`).
2. `git stash push -- <touches>` (implementation aside), run the new tests
   → must FAIL with the task's `expected_red` substring. Restore stash.
3. Compare test hashes (unchanged since the fail-run) → commit.

RED-proof failure (tests pass without implementation) = gate FAIL with a
dedicated report; operador iterates (strengthen tests). red-gate keeps
the ledger `red_check` + dispatch + coder-gate chain (materialization of
pre-written tests removed). `red-integrity` is redefined as "tests
identical between RED-proof fail-run and commit" (no post-green
weakening).

Gaming residual: operador writes test+code, so vacuous tests are
possible. Three independent mitigations: (a) RED-proof (fail-first proven
by execution), (b) `expected_red` substring authored by Agente diretor,
not operador, (c) Agente revisor judges test-vs-acceptance fit (verdict
SEND_BACK on weak tests). Accepted residual per developer decision.

## Spec alignment (no loose plans)

A plan untethered from the spec passes no alignment check: the revisor
verifies diff-vs-brief, but brief-vs-spec was only a pointer. Every task
carries `spec_refs` (filled by Agente diretor, at least one per task);
`brief-scaffold` copies them into the brief; the revisor verifies the
diff covers the cited sections, and a task with no spec anchor is itself
a SEND_BACK finding.

## Corrective loop

`SEND_BACK` → Script CEO resumes Agente diretor (`--continue`) with the
revisor's findings → appends corrective task (`corrects: N`) to plan.json
(tracked) → `brief-scaffold` builds the corrective brief → dispatch the
SAME operador session (`task-N-session.txt`, mapped via `corrects`) until
green → same gates + RED-proof → commit → re-review. TEST_DEFECT →
Agente diretor rules: fix the task's acceptance/expected_red in plan.json,
re-scaffold, same operador resumes. No Agente estratégico anywhere.

## Runner + live digest + closing

- `scripts/run-pipeline PLAN_FILE [TOTAL]`: loops route-next → executes
  each action (BRIEF=scaffold, RED=red-gate chain, CODER=coder-gate resume,
  REVIEW=record outcome, CORRECTIVE=corrective path, ARBITRATE=resume
  Agente diretor, NEXT=advance, FINAL_REVIEW=closing) until done, then
  push+PR default and reports the URL.
- `dispatch` prints a live progress digest (short lines from the JSON
  event stream) to stdout while the full stream still lands in the log —
  the calling session (usually Agente estratégico) watches
  operador/revisor/diretor work without opening logs. Long runs: ledger
  resume (re-run continues) + `--progress-log` for background mode.
- Closing by Agente diretor: `final-gate` (with short-circuit: clean tree
  + HEAD == last ledger green commit ⇒ skip test/analyze re-run),
  `review-package MERGE_BASE HEAD`, closing assessment (spec coverage:
  every spec requirement maps to a completed task — the mirror of
  spec_refs; gaps become tasks or explicit follow-ups).

## What is removed/replaced

- Estrategista-authored briefs/RED/correctives/arbitration/holistic review.
- red-gate materialization of pre-written tests.
- red-integrity old definition (brief-vs-commit byte compare).

## Test plan

- `brief-scaffold`: usage/missing-field exits, scaffold content from a
  fixture plan, idempotent overwrite.
- `run-pipeline`: routes a stubbed branch to FINAL_REVIEW (stub dispatch
  + gates), progress log written.
- RED-proof: new-tests detection (touches exclusion), fail-run gating on
  substring, hash-compare redefinition of red-integrity.
- route-next/coder-gate: unchanged actions; corrective tasks route as
  normal tasks (integer ids).
- Skill-content tests: estrategista-ends-at-plan, diretor referenced,
  operador-authors-RED documented, new display names present.
- Full suites green.
