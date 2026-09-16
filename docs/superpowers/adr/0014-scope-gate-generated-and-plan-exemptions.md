# ADR-0014: Scope gate exempts build output and the tracked plan

- **Status:** Accepted
- **Date:** 2026-09-15
- **Related:** ADR-0012 (script-owned integration gate), ADR-0013 (integrate suite skip)

## Context

`keep-discard` (the C2 scope gate) DISCARDs a task when any changed file falls
outside its plan `touches`, with exactly two exemptions: a newly authored test
file (H3) and nothing else. `touches` is authored at planning time and cannot
name every file a task legitimately produces.

Two classes of legitimate change are therefore flagged as violations:

1. **Code-generated output.** A task that changes a `@freezed`/`@JsonSerializable`
   source must regenerate its output. Worse, the committed generated files on
   this project drifted from the installed generator version, so a single
   `build_runner` run rewrote **54** files — only the one or two
   corresponding to the edited model are foreseeable at planning time.
2. **The tracked plan.** During arbitration the Agente diretor corrects the
   plan (`docs/superpowers/plans/*.json`) — the pipeline's own documented
   corrective mechanism. The plan is pipeline state, yet it is never a task's
   `touches` entry.

Observed consequence (2026-09-15, design-system phase, task 3): a correct
implementation was DISCARDed twice, the diretor's own plan correction was
itself counted as out-of-scope, and the resulting re-escalation hit the C1
human block.

The alternative — adding the generated files to each task's `touches` — was
tried (the diretor added `store_settings.freezed.dart`/`.g.dart`); it is
fragile, per-task, and cannot anticipate a whole-project regeneration.

## Decision

`keep-discard` exempts, in addition to the newly-authored-test rule:

- **build output** by path suffix: `.freezed.dart`, `.g.dart`, `.gr.dart`,
  `.gen.dart`, `.mocks.dart` (`pathclass.is_generated_path`, shared like
  `is_test_path`);
- **the tracked plan**: any `docs/superpowers/plans/*.json`.

Both are recorded in the gate's docstring. A modified *committed test* file
stays a violation — it remains the tampering signal the exemption list must
not erode.

## Consequences

- Codegen tasks are no longer structurally doomed: a task may change a
  generated source and let the generator rewrite its outputs. The revisor
  still reviews the regenerated diff, so the exemption does not hide content.
- The diretor's plan corrections no longer self-block; the plan change rides
  into the task's commit or is committed branch-level.
- The gate is slightly more permissive: a hand-edit hidden inside a `.g.dart`
  or the plan would not be caught by `keep-discard`. Accepted — generated
  files are regenerated and reviewed, and the plan is a reviewed artifact.
- The tracked-test rule is untouched, preserving the original anti-tampering
  guarantee.

## Alternatives considered

- **Add generated files to each task's `touches` per task:** rejected — the
  drift set is unknowable at planning time and the fix would need repeating
  for every codegen task.
- **Regenerate generated files outside the task (a pipeline step before the
  gate), so they are never part of the task's diff:** rejected — it moves the
  change into an unreviewed side channel and still needs the files to be
  committed somewhere.
- **Let the diretor rule every scope violation caused by codegen:** rejected —
  a mechanical, deterministic situation must be resolved by the script, not by
  a Strategic-tier dispatch (the pipeline's core rule).
