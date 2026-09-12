# Design: Decouple brainstorming from the pipeline; script-owned RED form; punctual task ownership

Date: 2026-09-12. Brainstormed (architectural path) with the developer.

Supersedes: ADR-0006 (Agente diretor expands tasks; estrategista persists across
the branch). Amends ADR-0001 (the interactive session stays out of the dispatch
chain — the principle holds; the executor identity changes). Amends ADR-0007
(the RED-evidence check becomes a deterministic form classifier; the semantic
guarantee moves wholly to the revisor).

Actor names (display): Script CEO (= Script A), Agente estratégico (= B),
Agente diretor (= task owner), Agente operador (= coder), Agente revisor
(= reviewer). Machine identifiers (`two-model-coder`, `coder_round`, flags,
paths) are unchanged.

## 1. Problem

Three costs and risks in the current design:

1. Brainstorming and the pipeline share one interactive session, and the design
   then asks that session to stay available as the exception owner
   (corrective/arbitrate/closing). That couples pipeline reliability to a warm
   provider cache: after the cache TTL expires, every exception turn re-bills
   the accumulated prefix (spec + plan + run stdout).
2. `expected_red` is authored at planning time. It duplicates the coder's test
   planning, and it is only a lexical proxy — the coder can satisfy it by
   construction, so it never was an independent semantic guarantee.
3. The Agente diretor expands the plan shell, so the plan is only complete after
   an extra LLM hop; planning and execution are not cleanly separated.

## 2. Session model (two sessions, one file interface)

- **Brainstorming session (prior).** Produces the design spec and a COMPLETE
  `plan.json`. Then DONE. It never launches the pipeline and never sits in the
  dispatch chain.
- **Pipeline session (clean).** Launches `scripts/run-pipeline PLAN_FILE` and
  observes. It is not the exception owner; corrective/arbitrate/closing are
  headless dispatch (section 5).

The script is stateless with respect to the calling session: it reads only the
plan file passed as an argument and the ledger. This was already true; it is now
an explicit contract, because the separation is the point.

## 3. Plan schema (complete at brainstorming time)

Brainstorming / writing-plans authors every task in full:

```json
{
  "id": 1,
  "title": "short imperative title",
  "summary": "2-3 sentences: what and why",
  "spec_refs": ["§4"],
  "touches": ["path/to/implementation/file"],
  "depends_on": [],
  "acceptance": ["observable behavior that must hold"]
}
```

No `expected_red`. RED tests are still authored just-in-time per task by the
Agente operador (unchanged: one work unit is one plan task, including a
same-shape batch). `touches` lists implementation paths only — test paths are
the RED (`changed − touches`) and never appear in `touches`.

## 4. RED integrity

RED integrity is split into three roles with one guarantee each:

- **Form — script, deterministic.** The Agente operador saves the RED run in the
  runner's machine-readable format. `red-form-check WORKSPACE TASK LANG` reads
  it and requires: the suite loaded (no compile/load error), at least one test
  executed, and it failed as an assertion or runtime error. A compile/load red
  is a FAIL round with a fix prompt ("strengthen or re-run the RED"), never a
  TEST_DEFECT. Unsupported language → exit 2, caller falls back to a presence
  check.
- **Reason — Agente operador, self-check.** Before implementing, the operador
  declares the expected reason and confirms the observed RED is that reason; it
  saves the declaration beside the evidence. This is a fast pre-filter that
  avoids wasting implementation on a bad RED, and the artifact the reviewer
  consumes. It is NOT a guarantee.
- **Semantics — Agente revisor, sole guarantee.** The revisor independently
  judges whether the tests encode the task's acceptance. Weak or vacuous tests
  are SEND_BACK findings. No other actor provides an independent semantic check.

Per-language machine formats:

| Lang | Command | Valid red | Compile/load red |
|---|---|---|---|
| flutter/dart | `flutter test --machine` | `testDone result=failure` (assertion) or `result=error` after a `testStart` | no test event; suite-level error |
| python | `pytest --json-report` (or exit code) | exit 1 with a failed test | exit 2 (collection/compile error) |
| go | `go test -json` | `Action=fail` with test events | `[build failed]` |

## 5. Task ownership

- **No EXPAND.** The plan arrives complete; `tasks_usable` checks `acceptance`
  only. The expand dispatch is removed.
- **Corrective / Arbitrate — Agente diretor, punctual.** On SEND_BACK or
  ARBITRATE the script dispatches `two-model-task-generator` with
  script-controlled context: the findings + the FULL `plan.json` + the target
  task + the cited spec_refs. `--continue` resumes only within the same
  episode (multiple rounds on one task); between tasks the dispatch is fresh.
  No cross-branch persistent session.
- **Closing — headless, curated package (unchanged in shape).** `plan` + `spec`
  + consolidated diff + full ledger, one dispatch. The holistic review runs on
  the artifact set, never on the interactive session and never by reopening the
  brainstorming session.

## 6. Cost / cache rationale

A persistent interactive session re-bills its whole accumulated prefix every
turn after the provider cache TTL expires; on a long branch the exception turns
re-charge spec + plan + run stdout. A script dispatch bills only the context the
script chose. Therefore every reasoning call (operador, revisor, task-generator)
is script-dispatched with curated context, and the interactive session is never
the exception owner. Correctness and economy do not depend on cache warmth.

The Agente diretor needs the full `plan.json` (not a reduced slice) because the
coordination map — `spec_refs`, `touches`, `depends_on` — is what prevents a
corrective task from conflicting with existing tasks and interfaces. The plan is
compact metadata, so passing it whole is cheap.

## 7. Bootstrap constraint

This change is executed by the pre-change pipeline, so this branch's own plan
tasks still carry `expected_red` and are run by the old `brief-scaffold` /
`coder-gate` until the respective task lands. The task order is chosen so the
transition never breaks:

1. **Add the form checker** (`red-form-check`) — additive, changes nothing.
2. **Switch `coder-gate`** to the form checker — old briefs still carry
   `expected_red`, now ignored; the plan may still carry it harmlessly.
3. **Stop emitting `expected_red` in `brief-scaffold`** — safe because
   `coder-gate` no longer reads it.

Reversing 1 and 3 would break every brief scaffolded between them.

## 8. Running this plan

`scripts/run-pipeline <plan>` resolves the toolchain with `resolve-toolchain`.
This repo carries only `package.json` (no `test` script), so auto-detection
resolves `node` / `npm test` and fails. Prerequisite for a clean run:

- ledger a manual gate entry once (`detected=manual`) pointing `TEST_CMD` /
  `ANALYZE_CMD` at the pipeline suites (`python3 -m unittest discover` per
  `skills/*/tests`, or the `run-tests.sh` wrappers), **and**
- ensure the Agente operador's bash allowlist permits that command (the mirrored
  definition in `agent/two-model-coder.md` is Flutter/Dart-only).

Alternatively, add a `test` script to `package.json`. These are operational
prerequisites, not part of the design.

## 9. Test plan

- `red-form-check`: assertion-failure fixture → 0; compile/load-error fixture →
  1; missing evidence → 1; unsupported language → 2.
- `coder-gate`: a form-valid RED with no `expected_red` in the plan passes;
  form-invalid produces a FAIL round (not TEST_DEFECT); TEST_DEFECT stays
  terminal.
- `brief-scaffold`: task without `expected_red` scaffolds; no "Expected failure"
  section; reason-declaration and machine-readable-evidence instructions
  present; test-like `touches` still exit 2.
- `run-pipeline`: a plan without `expected_red` runs with no expand dispatch;
  corrective dispatch passes the plan and target task.
- Content tests: skills and READMEs describe the decoupled pipeline, the
  punctual task-generator, the form check, and the absence of `expected_red`.
- Full suites green.

## 10. Out of scope

- Changing the revisor's verdict schema.
- Making the interactive session the exception owner (rejected in section 6).
- Reopening the brainstorming session for the holistic closing review (rejected
  in section 5; improve the spec instead).
- Redesigning the ledger or the `route-next` state machine.
