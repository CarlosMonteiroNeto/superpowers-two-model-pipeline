# ADR-0010: Wave scheduling is plan-derived, not runtime-inferred

- **Status:** Accepted
- **Date:** 2026-09-15
- **Related:** ADR-0011 (worktree-per-task isolation), ADR-0012 (script-owned
  integration gate)

## Context

`run-pipeline` is strictly serial: it picks the lowest-id task without a
`task_complete` and drives that one task alone. Nothing in the engine exploits
the fact that many plan tasks are mutually independent.

The fork's founding rule is *LLMs reason; scripts decide*. Parallelism is
therefore a scheduling decision, and the only trustworthy inputs are the ones
the plan already declares: `depends_on` (task ids, binding) and `touches` (the
exclusive file set). Letting a model decide "these two tasks look independent"
would reintroduce exactly the runtime judgment the engine exists to remove, and
would make concurrency non-reproducible and non-resumable.

Gates for recording a decision (all three, per the brainstorming skill):
reversal cost — high; reach — project-level; a rejected alternative exists.

## Decision

- A **wave** is a maximal set of **ready** tasks whose `touches` sets are
  pairwise disjoint, capped by `--max-parallel` (default 2).
- A task is **ready** when every id in `depends_on` is complete and it is not
  itself complete; **complete** means a `task_complete` (or `integrated`) entry
  with no newer `integration_failed`.
- The scheduler is scripts, not prompts: `wave-next` computes the ready set from
  `plan.json` + the merged ledger and emits one `RUN <id>` per selected task;
  `touches-overlap` is the exact pairwise disjointness comparison. `route-next`
  remains the per-task router, unchanged.
- A contract-producing task (a shared type/interface/model consumed by ≥2 tasks)
  is a wave of its own; the disjointness rule already defers its consumers.
- Corrective work (`corrects: N`) and any task with an open review episode are
  never given a parallel slot: `wave-next` emits exactly that task, alone.
- Every loop iteration recomputes waves from plan + ledger; no state is carried
  in process memory.

## Consequences

- Concurrency is reproducible and resumable: a re-run re-derives the same waves
  from the same files.
- `depends_on`/`touches` become load-bearing. An inaccurate plan costs more than
  ordering noise — it can serialize real work, or (if `touches` lies) let two
  tasks edit one file. The plan-authoring rules and the advisory
  `interface-check` are the mitigating controls.
- `--max-parallel 1` degenerates to the historic serial path (no worktrees, no
  `integrate`); this is the explicit regression contract.
- The scheduler binds to two scripts with one unit test each, not to prompt
  wording.

## Alternatives rejected

- **LLM-inferred readiness** (ask a model which tasks can run together):
  rejected — reintroduces runtime judgment, breaks reproducibility and resume,
  and violates "LLMs reason; scripts decide".
- **Runtime heuristic for `--max-parallel`** (e.g. scale with machine load):
  rejected — the plan, not the machine, owns the disjointness contract; a
  variable default would make waves non-reproducible.
- **Hand-authored wave labels in the plan**: rejected — duplicates
  `depends_on`/`touches`, drifts immediately, and cannot react to a corrective
  task appended mid-run.
