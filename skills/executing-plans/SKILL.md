---
name: executing-plans
description: Use when you have a written implementation plan to execute in a separate session with review checkpoints
---

# Executing Plans

## Overview

## Pipeline Integration (two-model-sdd-pipeline)

- **The router decides "what's next," not the LLM.** This skill's manual "work through tasks in order" loop is replaced, per task, by `route-next WORKSPACE TASK [TOTAL]`: it reads the ledger and deterministically emits the next action (BRIEF / RED / CODER N ROUND / REVIEW / CORRECTIVE / ARBITRATE / NEXT / FINAL_REVIEW). `orchestrator` executes the emitted action and prints `OUTCOME:` back to B.
- **Every command line is compressed and logged.** Task/test/analyze runs go through `scripts/cmd --full-file FILE -- CMD...`, which saves full output to FILE and prints an RTK-compressed view to context — the plan's execution trail is never lost, but the LLM never pays full token cost for it.
- **Resume is structural.** Because state is the ledger (not conversation memory), an interrupted or compacted session resumes correctly just by re-running `route-next` against the same workspace/task.


Load plan, review critically, execute all tasks, report when complete.

**Announce at start:** "I'm using the executing-plans skill to implement this plan."

**Note:** Tell your human partner that Superpowers works much better with access to subagents (Claude Code, Codex CLI, Codex App, Copilot CLI, and Gemini CLI all qualify; see the per-platform tool refs in `../using-superpowers/references/`). If subagents are available, use superpowers:subagent-driven-development instead of this skill.

## The Process

### Step 1: Load and Review Plan
1. Ensure an isolated workspace: use superpowers:using-git-worktrees to create one or verify the existing one
2. Read plan file
3. Review critically - identify any questions or concerns about the plan
4. If concerns: Raise them with your human partner before starting
5. If no concerns: Create todos for the plan items and proceed

### Step 2: Execute Tasks

For each task:
1. Mark as in_progress
2. Follow each step exactly (plan has bite-sized steps)
3. Run verifications as specified
4. Mark as completed

### Step 3: Complete Development

After all tasks complete and verified:
- Announce: "I'm using the finishing-a-development-branch skill to complete this work."
- **REQUIRED SUB-SKILL:** Use superpowers:finishing-a-development-branch
- Follow that skill to verify tests, present options, execute choice

## When to Stop and Ask for Help

**STOP executing immediately when:**
- Hit a blocker (missing dependency, test fails, instruction unclear)
- Plan has critical gaps preventing starting
- You don't understand an instruction
- Verification fails repeatedly

**Ask for clarification rather than guessing.**

## When to Revisit Earlier Steps

**Return to Review (Step 1) when:**
- Partner updates the plan based on your feedback
- Fundamental approach needs rethinking

**Don't force through blockers** - stop and ask.

## Remember
- Review plan critically first
- Follow plan steps exactly
- Don't skip verifications
- Reference skills when plan says to
- Stop when blocked, don't guess
- Never start implementation on main/master branch without explicit user consent
