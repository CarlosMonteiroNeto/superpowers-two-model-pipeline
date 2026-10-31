# User-selected subagent models

This protocol governs every Superpowers subagent dispatch. It applies only to
subagents; a skill does not change the model of the main session. Read the
package's [persistent registry](subagent-models.json) before preparing dispatches.
User choices override model-tier recommendations, complexity-based selection,
automatic escalation, and model defaults elsewhere in the package.

## Roles

Select the role from the skill, prompt, and work actually assigned to the child.
The controller's current skill alone does not determine the child's role.

| Role key | Assigned work |
| --- | --- |
| `design-reviewer` | Brainstorming's builder check of a written design |
| `implementer` | Implement a plan task, including a batch of related edits |
| `task-reviewer` | Per-task spec compliance and code quality review |
| `fix-reviewer` | Scoped re-review after fixes, including the final fix wave |
| `final-reviewer` | Whole-branch or standalone broad code review |
| `fix-implementer` | Fix review findings or take over a stuck implementation |
| `parallel-investigator` | Independent debugging, research, or session analysis |
| `skill-evaluator` | Skill-behavior scenarios, wording tests, or skill evaluation |
| `orchestrator` | Delegate coordination of an entire workflow when authorized |

Other roles, including diagnostic scrub/audit workers, use the confirmed default.
Do not create a subagent merely because its role appears in this table.

## Confirm once before the first dispatch

A run is one user-requested workflow for one deliverable or plan. Moving from
brainstorming to planning, execution, fixes, and final review is the same run.
Compaction, resumption, and entering another skill do not start a new run.
A distinct deliverable or plan starts a new run, even in the same chat.

1. Read the registry and identify all foreseeable roles for this run, including
   fix roles and the default for unanticipated work. Validate the exact model IDs
   and efforts against the current dispatch tool's supported values.
2. Present one compact table (stage/role, model, effort), including the default,
   and ask your human partner to confirm or modify it. Wait for their answer
   before spawning any child. Explicit choices already supplied by the user
   for this run count as confirmation; do not ask them to repeat those choices.
3. A reply modifying rows of the proposed table accepts the unchanged rows too,
   unless the user explicitly leaves their decision pending. Save every user
   change to the shared registry before dispatch. Serialize writers with an
   exclusive OS file lock on a shared `subagent-models.json.lock` sidecar; hold
   it across re-reading the registry, merging only the user's specified changes,
   and atomically replacing the JSON. Release the lock after verifying the save.
   This preserves unrelated concurrent edits and prevents partial JSON reads.
   A partial answer updates only the specified roles. A changed default
   applies to unlisted roles; explicit role entries remain unchanged. These are
   persistent preferences for later runs, not temporary overrides. Verify the
   saved values. If saving fails, report the cause and do not claim persistence.
4. Record a run receipt in the existing plan/progress ledger: run identity,
   confirmation evidence, and the complete resolved snapshot of all confirmed
   table rows plus the default. Roles not in that table use the confirmed default
   for this run, even if a separate preference exists in the registry.
   Without a ledger, record it in the existing task scratch workspace. Keep its
   path in the handoff/compaction summary. A receipt is run state, not a new
   confirmation on every dispatch. Never mark confirmation merely from file
   existence or a prior run's receipt.

Use the confirmed snapshot throughout the run, not a later change another chat
made to the registry. New roles use the already-confirmed default without an
extra question. Nested controllers receive the receipt path and resolved
snapshot, inherit this approval, and do not ask again. Do not delegate workers
that the workflow or current environment forbids.

## Dispatch and recovery

Set the exact confirmed `model` and `reasoning_effort` (or equivalent supported
parameters) explicitly on every spawn. On tools requiring a fresh context for
overrides, use one and provide the task context. Check actual tool instructions;
do not assume a prompt or role name changes runtime settings. If the tool reports
effective settings, verify them; do not describe requested settings as verified
effective settings when the tool does not expose them.

Resume an existing child only when its recorded model/effort matches the role
now assigned. Otherwise spawn a fresh child with the confirmed role settings.
Rounds 4-5 and blocked tasks may get fresh context, better evidence, a revised
hypothesis, or smaller tasks, but do not automatically increase model or effort.
Preserve the workflow's retry limits and evidence requirements.

On resumption, recover the matching run receipt and snapshot before dispatch;
do not ask again when confirmed evidence is recoverable. If the receipt location
is lost, investigate existing task artifacts and the conversation first. If
approval genuinely cannot be recovered, pause delegation rather than invent it.

If a confirmed model/effort is unsupported or unavailable, stop only affected
delegation, explain the concrete limitation, and request a replacement once for
all affected roles. Do not silently inherit, substitute, lower, or raise settings.
This is recovery from a failed choice, not routine per-agent confirmation.
This concrete dispatch limitation also applies to workflows that otherwise
permit stopping only for their named execution blockers; continuing does not
authorize a different model or effort.
When the user explicitly changes a choice during a run, update both the registry
and that run's receipt before the next affected dispatch. Running agents keep
their settings; apply the new choice to future spawns and report this limit.
