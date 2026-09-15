---
name: write-script
description: Use when writing, reviewing, or refactoring a deterministic script for the two-model-sdd-pipeline or flutter-app-pipeline — gates, routers, dispatchers, ledger writers, compressors, or any step between Script CEO and a mechanical outcome. Trigger on "write a script for X", "review this gate", "should this be a script or should the revisor decide", or when a new deterministic step is added to the per-task loop.
---

# write-script

In this pipeline a script is not utility code — it is the thing that takes a mechanical decision out of an LLM's hands. "LLMs reason; scripts decide" is the fork's first principle. Any place where an agent would read output and conclude "pass or fail", "continue or stop", "next task or corrective" is a script, and this skill is how to write it so it fits the existing chain.

Read the closest existing sibling before writing anything: `coder-gate` for loop-owning gates, `route-next` for pure deciders, `red-form-check` / `keep-discard` for Python classifiers, `cmd` for command wrappers, `dispatch` for anything that spawns an LLM.

## Pipeline Integration (skill-scripter)

`skill-scripter` audits a skill or stage and decides *what* should become a script; this skill implements each approved item. When it hands you a candidate, follow the per-candidate specification it produced (position, inputs, criterion, exit codes, ledger entries, fallback, idempotency, risk, resource profile) and do not silently widen the scope.

## Conventions this fork already has — match them, don't reinvent

### 1. Verdict is an exit code, and the code table is fixed per family

Document the table in the file header. The established meanings:

| Family | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| Deciders (`route-next`, `final-gate`, `interface-check`, `touches-overlap`, `wave-next`, `doc-check`) | clean / routed | domain failure, blockers listed | usage / missing artifact / no opinion | — |
| Loop gates (`coder-gate`) | green, committed, revisor dispatched | internal error — nothing is claimed green on doubt | TEST_DEFECT escalated | usage / missing gate or brief |
| `green-gate` | all gates passed | tests failed | analyze failed | scope violation (4) |
| `dispatch` | dispatched | — | usage / missing prompt file | wrong agent mode (`mode: all` required) |
| `run-pipeline` | branch closed | blocked, blocker printed, re-runnable | usage | — |

Never invent a fourth meaning for an existing family. If you need a new outcome, add a code and update the header table in the same commit.

`red-form-check` establishes the "unsupported → exit 2 → caller falls back" pattern. Use it whenever a classifier can legitimately not know: exit 2 means *I have no opinion*, not *failure*. `touches-overlap`'s malformed-plan path follows the same rule.

### 2. State lives in the ledger, never in a variable

`ledger-append` is the only writer. It escapes JSON, stamps UTC, appends to the global `ledger.jsonl`, and mirrors numeric-task entries to `ledger-task-<N>.jsonl`. Never `echo '{...}' >>` a ledger by hand — the partition mirror will be missed and `route-next`'s hot path silently falls back to the global grep. A second writer also means a second escaping path: `ledger-merge` re-emits shard entries *through* `ledger-append` for exactly this reason.

Every terminal outcome gets an entry, including failures. The rule that produced `dispatch_interrupted` in the generic `red-gate`: *a task must never be left with only its kickoff entry and no reason*. If your script can exit non-zero after a side effect, ledger why first.

If you add a new entry `type`, check whether `route-next` needs to read it. An entry nothing routes on is a comment with extra steps.

### 3. Compression: full to file, compressed to stdout, verdict from the raw run

`cmd --full-file FILE -- CMD...` is the wrapper. It runs the command once, writes the complete output to `FILE`, prints the RTK-compressed view on stdout, and returns the **command's** exit code. RTK wrappers (`rtk test`, `rtk err`) mask child exit codes — that is why `cmd` derives the compressed view from the saved file rather than piping through the wrapper. Preserve that ordering in anything you add.

Gates read the full file. LLMs read stdout. Nothing a verdict depends on is ever compressed: `red-form-check`'s machine-readable evidence, escalation packages, and byte-compare snapshots always read the file.

New command in the pipeline → add its filter or wrapper mapping to `cmd`'s `case`, do not shell out directly. (`green-gate` used to bypass this; M6 routed it through `cmd` — the fix, not the old bypass, is the precedent.)

### 4. Anything that spawns an LLM goes through `dispatch`

`dispatch` owns: `opencode run --agent`, the JSON event stream, the tee to the workspace log, the live digest, the `mode: all` fallback guard, and the session-id record for `--continue --session`.

Two hard constraints, both verified against this OpenCode version:
- The brief is passed as a **positional**, never `--file` — `--file` makes OpenCode treat the positional message as a path and every run breaks (ADR-0009).
- The target agent must be `mode: all`. `mode: subagent` silently falls back to the default agent and exits 0, which is why the guard exists.

Never add a second code path that calls `opencode` directly. If `dispatch` lacks something (a permission allowlist, a timeout), add the flag to `dispatch`.

### 5. Idempotency and resume, because the ledger is the only memory

Every script must be safe to re-run after a crash, a compaction, or a killed session. `coder-gate` reuses fixed workspace paths and re-derives its state from the log and evidence file, with no round counter. `ledger-migrate` rebuilds partitions from scratch on every run instead of appending. Follow both patterns: **re-derive, don't accumulate.**

Concretely: no counters in variables, no "second run does something different", no state that exists only while the process lives. A re-run of `run-pipeline` on the same plan must continue exactly where it stopped.

### 6. Fail fast, and fail loudly under `set -euo pipefail`

Validate arguments and required artifacts at the top, before any side effect. Usage errors get their own code, distinct from domain failure.

The `set -e` trap that has already bitten this repo three times: a bare failing command aborts the script before your error handler can run. Always capture:

```bash
rc=0
"$SOME_GATE" "$ws" "$task" || rc=$?
case "$rc" in
  0|2) ;;
  *) block "gate exit $rc on task $task - inspect logs" ;;
esac
```

Never `cmd; rc=$?` — under `set -e` you never reach the second statement. The same trap applies to a bare `git commit`: capture `commit_rc` and ledger the failure instead of dying mid-merge with a staged index.

### 7. Never mutate destructively by default

`session-clean` is never auto-run — sessions are kept for resume and debugging. `worktree-release` must not auto-remove on failure, for the same reason; it refuses unless the task branch is genuinely merged. Commits happen only on a proven-green gate, and only after a scope check against `touches`. If your script deletes, overwrites, or commits, it needs an explicit flag, a dry-run default, or a gate that already proved the precondition.

### 8. Ask once, ledger it, never ask again

`resolve-toolchain` is the model: one-time-per-branch detection, writes `gate` with `lang` / `test_cmd` / `analyze_cmd`, exit 1/2 means "a human must answer once, then it is ledgered". After that, every gate reads the ledger entry. No script asks the developer anything mid-branch — approval happens at the gate and at solution selection, never after Phase 2c.

### 9. Observability without polluting the main session

Full agent streams go to `task-N-<role>.log` via `tee`. The interactive session sees only the digest lines and `OUTCOME:`. Script CEO reads only curated outputs — `OUTCOME` lines, the ledger, parsed verdict JSON — never raw dispatch logs or full gate reports. A new script that prints a gate report to stdout has broken this; write the report to a file and print the verdict.

### 10. Cross-platform: Windows git-bash is a supported target

Constraints that already cost debugging time here:
- `export PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8` at the top of anything that pipes to Python, so a latin-1 byte never poisons the ledger.
- `cygpath -w` any path handed to native Windows Python (`pipeline-workspace` prints POSIX form on git-bash).
- Tolerate CRLF when reading files a Python step wrote (`line=${line%$'\r'}`).
- Inside a pipe, use `python3 -c '...'` — **never** a heredoc. A heredoc steals stdin and the reader parses its own program instead of the piped data. Both `run-pipeline` and `dispatch` carry this comment for a reason.
- Avoid `awk -v` with Windows paths; `ledger-migrate` `cd`s into the workspace and uses relative names instead.
- Compare literal paths with `grep -Fqx`: a worktree path can contain `.`, `[`, or `+` (git prints a `+` for a branch checked out in a worktree).

### 11. Declare the resource profile in the header

Whoever assembles the chain needs to know where the cost is without profiling:

| Resource | The question, in this pipeline |
|---|---|
| Dispatch | Does it spawn an LLM? Which tier — Operational (deepseek-v4-flash) or Strategic (muse-spark)? Fresh or `--continue` (prefix-cached)? |
| Context tokens | Does its stdout reach an LLM? Compressed via `cmd`, or raw? |
| Ledger I/O | Does it read the per-task partition (O(task)) or the global ledger (O(branch))? |
| Subprocess | One `awk`/`python3` pass, or a loop spawning per task? (`ledger-migrate`'s header explains why this matters on git-bash.) |
| Wall-clock | Blocking in the serial chain, or parallelizable across independent tasks? |
| Git | Does it read the index, diff a range, or write commits? |

A Strategic dispatch inside a retry loop is the single most expensive thing you can write here. If your script can loop, state the terminal condition in the header — `coder-gate` is unbounded *by design* and says so; `ARBITRATE` was unbounded *by accident* and did not (C1 added the terminal state).

### 12. Every script gets a unit test, and the README must change with it

Tests live in `skills/<skill>/tests/test_<script>.py`, run by `run-tests.sh`. They fake the workspace and ledger; they never need the whole pipeline. Test the exit codes, not the prose.

`doc-check` blocks the branch if pipeline files changed and `README.txt` / `README-LLM.md` did not. Budget for it — the doc edit is part of the task, not a follow-up.

## Using this skill

**Writing a new script.** Walk the sections as questions: which exit-code family? what does it ledger, and does `route-next` read it? does its stdout reach an LLM (→ `cmd`)? does it spawn one (→ `dispatch`)? is it safe to re-run? what happens under `set -e` when its callee fails? Then write the header table before the body.

**Reviewing one.** Name the convention it breaks and give the minimal diff, not a rewrite. The common breaks in this repo, in frequency order: a decision inferred from prose instead of an exit code; a terminal path with no ledger entry; a `sed` where the neighbouring code parses JSON; a second copy of logic that already exists in a sibling script.

**Deciding whether it should be a script at all.** Mechanical and reproducible → script. Genuine judgment — architecture, whether the tests encode the acceptance, whether a requirement is ambiguous — stays with the revisor or the diretor. Do not force determinism where there is none; that is how you get a gate that false-positives on the word "important". `skill-scripter` owns that call at the skill/stage level.
