---
name: skill-scripter
description: Use when auditing a skill or pipeline stage for determinism — "what here could be a script", "audit this stage", "why does this step cost a Strategic dispatch", or before adding a stage to the per-task loop. Finds prose decisions, dead or duplicated scripts, and unbounded loops, and writes a scriptization plan that write-script implements.
---

# skill-scripter

Audits a stage of this pipeline and produces a **scriptization plan**: which decisions are still made by an LLM reading prose but are mechanically decidable, and what the deterministic replacement looks like. `write-script` implements each approved item.

## Pipeline Integration (writing-skills → skill-scripter → write-script)

This is the fork's skill-authoring chain. When `writing-skills` drafts or edits a skill:

1. `skill-scripter` audits that skill (and the stage it governs) for steps that are mechanical but still prose.
2. Each approved candidate is implemented with `write-script` (exit-code family, ledger entry, resource header, unit test).
3. The skill is then rewritten to *reference the script* rather than restate the procedure, and `doc-check` requires `README.txt` / `README-LLM.md` to change in the same branch.

The plan is always a file, approved before implementation — never delivered in conversation.

This fork is already heavily scripted, so the yield is rarely "here is a new gate". It is usually one of three other things, and the audit must look for all four:

1. **Prose decisions** — a step where an agent reads output and concludes pass/fail.
2. **Dead scripts** — a deterministic gate exists but nothing calls it (`interface-check` and `keep-discard` were in exactly this state until the 2026-09-14 review wired them; `red-integrity` and `token-kill` were unreachable and have since been deleted). A gate that is never called is not determinism, it is documentation.
3. **Drifted duplicates** — two implementations of the same decision that have diverged. The historical cases were `orchestrator` vs `run-pipeline`'s dispatch table, the generic vs Flutter `red-gate`, and task counting in `route-next` vs `run-pipeline` — all collapsed in that review. The live case to watch is the "unresolved task" predicate, currently written three times: `wave-next`, `run-pipeline`'s `failed_ids`, and `final-gate`.
4. **Unbounded loops** — a retry or escalation path with no terminal state. In a pipeline that dispatches paid models from inside `while true`, this is the highest-severity class there is. The canonical example is `ARBITRATE` (an action shipped without a ledger entry that resolved it → infinite Strategic dispatches); it was fixed by ledgering `arbitrate_resolved` and adding a router rule — the template for every future action.

## The test

For each step, ask:

1. **Reproducible?** Same ledger state, same plan, same tree → same decision?
2. **Enumerable criterion?** Can the rule be written with no "use your judgment" in it?
3. **Mechanically verifiable?** Exit code, diff, hash, schema, count, timestamp, field comparison — without understanding meaning?

Three yes → script candidate. Any no → stays semantic, and the plan says which criterion failed and why.

Where the line actually falls here:

- **Script:** routing on ledger state; verifying RED evidence form; comparing `touches` against a diff or against another task's `touches`; checking a plan for required fields; counting tasks; detecting an interface file another task consumes; deciding whether the tree changed since the last green commit; parsing a verdict out of a JSONL stream; allocating/releasing a worktree; merging task branches in id order.
- **Semantic (revisor/diretor keeps it):** whether the tests genuinely encode the acceptance; whether the design is sound; whether a task is viable or must be re-planned; triaging parked minors at closing; the Intent Gate classification in `flutter-pipeline` (intent is not derivable from a marker file — the agent file says so explicitly, and it is right).

A useful sharpening question for this fork: **does this step currently cost a dispatch, and of which tier?** A Strategic (muse-spark) dispatch that only reads a field and picks a branch is the highest-value scriptization target in the repo, regardless of how simple the script is.

## Analysis process

1. **Read the actual files.** `SKILL.md`, every script under `scripts/`, the agent definitions under `agent/`, the prompts (`coder-prompt.md`, `reviewer-prompt.md`, `task-generator-prompt.md`), and the relevant ADRs. Never audit from the README — in this repo the README and the code have drifted before.
2. **Map the steps in ledger order.** For each: who decides today (Script CEO, operador, revisor, diretor, developer), what ledger entry records the outcome, and what `route-next` does with it. A step that produces no ledger entry is already a finding.
3. **Grep for callers.** For every script in `scripts/`, confirm something calls it. Exclude its own file, its tests, and doc mentions. Uncalled → finding, with a keep-or-delete recommendation.
4. **Diff the near-duplicates.** Any two scripts with the same role (generic vs Flutter mirror) get a line-level comparison. Report every divergence, not just the intentional ones. When you find a predicate written in three places, that is one finding, not three.
5. **Trace every loop to its terminal state.** For each `while`/retry/escalation path, name the condition that ends it and the ledger entry that proves it ended. If no ledger entry changes the router's view, the loop is infinite — Critical. (Beware the subtler "bounded but inert" loop: recovery that re-runs a step which cannot change its input terminates, but does no work.)
6. **Apply the test** to each LLM- or human-decided step.
7. **Specify each candidate** (see below).
8. **Justify each semantic keeper** in one line, so it does not look forgotten.
9. **Prioritise** by implementation cost against *recurring* execution cost, where execution cost is measured in tier dispatches first, context tokens second, wall-clock third. A step that fires once per branch weighs far less than one inside the coder retry loop.

## Per-candidate specification

Each script candidate needs:

- **Name and position in the chain** — what calls it, what it chains into. (If it is a new action, say what `route-next` must emit and what ledger entry resolves it.)
- **Inputs** — workspace, task id, plan fields, ledger entry types read. Say whether it reads the per-task partition or the global ledger.
- **Exact decision criterion** — the rule, not "check if it's ok".
- **Exit-code table** — matching the family conventions in `write-script`.
- **Ledger entries written** — type, and what `route-next` does with each.
- **Fallback** — missing binary, unknown language, absent artifact. `red-form-check`'s exit-2-means-no-opinion pattern is the reference.
- **Idempotency** — what a re-run after a crash does.
- **Mis-scriptization risk** — the false positive and the false negative, and how each is mitigated. Be concrete: `final-gate`'s old severity check grepped prose for "Important" and blocked on a minor that said "not important"; it is now a structured `PARKED_SEVERITY` field.
- **Resource profile** — dispatches (and tier), context tokens, ledger read scope, subprocess count, git operations, and whether it blocks the serial chain.
- **Cross-platform notes** — anything touching paths, encodings, or pipes on Windows git-bash.

## Output plan format

One `.md` under `docs/superpowers/specs/<date>-<slug>-scriptization.md`, structure fixed:

```
# Scriptization Plan — <stage / skill>

## Summary
<3-5 lines: steps analysed, candidates found, dead/duplicated scripts found,
 unbounded loops found, expected gain in dispatches per branch>

## Unbounded loops (fix first)
### <path>
- Loop: <where>
- Missing terminal state: <what the router never sees change>
- Fix: <entry to ledger + router rule>

## Dead or duplicated scripts
- <script> — no caller / duplicate of <other> — keep and wire | delete | merge

## Script candidates (priority order)
### 1. <script-name>
- Replaces: <what an LLM decides today, and at which tier>
- Position: called by <X>, chains into <Y>
- Criterion: <exact rule>
- Exit codes: 0=<...>, 1=<...>, 2=<...>
- Ledger: writes <type>; route-next reacts by <action>
- Fallback: <...>
- Idempotency: <...>
- Risk: <false positive> / <false negative>
- Resource profile: <dispatches, tokens, I/O, wall-clock>
- Effort: low | medium | high

## Stays semantic
- <step> — fails criterion <n>: <one line>

## Implementation order
1. ...
```

## Rules of conduct

- Do not propose scripts for steps that are already scripted. The goal is finding prose disguised as a decision — and gates disguised as wiring.
- Do not scriptize genuine judgment because it looks tractable. Breaking the revisor's semantic role is how the pipeline loses its only independent guarantee that the tests encode the acceptance.
- Every candidate that adds a new `route-next` action must specify the ledger entry that *resolves* it. The `ARBITRATE` loop existed because a new action shipped without one.
- The plan is always a file, reviewed and approved before any implementation. It is not delivered in conversation.
- After approval, each script is implemented with `write-script`, and `doc-check` will require `README.txt` and `README-LLM.md` to change in the same branch.
