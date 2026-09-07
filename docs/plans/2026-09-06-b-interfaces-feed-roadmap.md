# B Does Not Read the Graphify Interfaces Feed Before Writing Briefs

**Date:** 2026-09-06
**Status:** Draft (problem report + roadmap)
**Source:** perfume-pos POS sale screen session (`feat/perfume-pos-pos-sale`), Tasks 1-6
**Authoring environment:** OpenCode, model deepseek-v4-flash, plugin
`superpowers-two-model-pipeline` (agent-generated report, written for the
project maintainer)

---

## Executive Summary

During the perfume-pos POS sale screen branch (Tasks 1-6 of 9), the
interactive strategist session (**B**) wrote task briefs **without reading the
`task-N-interfaces.md` files** that `graphify-subgraph` produces after each
task's green-gate. The intended mechanism — per the skill docs and
`README-LLM.md` — is that B reads the affected-dependency subgraph feed
`<ws>/task-N-interfaces.md` **before** writing brief `N+1`. Instead, B relied
on the JSON plan, direct source reads, and the review packages. The
interfaces files were written by the script correctly (update-before-commit +
read-immediately-after, ADR-0004, all 6 written) but were **consumed only by
the Reviewer (D)** — not by B.

This is not a script failure. Script A did everything right. This is a
**B-behavior gap**: the feed existed and was ignored for brief-writing.

---

## Problem Report

### What happened

1. Task 1 green → `graphify-subgraph` wrote `task-1-interfaces.md`.
2. B read `task-1-interfaces.md` before writing the Task 2 brief (the one
   correct use in the session).
3. For Tasks 3, 4, 5, and 6, B wrote the brief **from the plan.json + direct
   source inspection** (model files, repositories, providers) and did not read
   the immediately-preceding `task-(N-1)-interfaces.md`.
4. The Reviewer (D) received the interfaces file via the review package on
   every task (correct per Item 2 / ADR-0004), so code quality was not
   affected.
5. No test/code defect resulted — the plan's verbatim interface blocks were
   sufficient. But the mechanism's **context-compression purpose** was
   bypassed: B pulled whole source files into context instead of the curated
   affected-dependency slice, inflating the session context and defeating the
   "B reads only what the scripts hand it" design intent.

### Evidence

- `task-1-interfaces.md` (1042 B) — read before brief 2. ✓
- `task-2-interfaces.md` (2404 B) — NOT read before brief 3.
- `task-3-interfaces.md` (957 B) — NOT read before brief 4.
- `task-4-interfaces.md` (1631 B) — NOT read before brief 5.
- `task-5-interfaces.md` (2799 B) — NOT read before brief 6.
- `task-6-interfaces.md` (1407 B) — exists; brief 7 pending.

All files were written by `graphify-subgraph` immediately before their task's
commit (green-gate lines `GRAPHIFY-SUBGRAPH: wrote .../task-N-interfaces.md`),
and `git log --stat` shows `graphify-out/` entering each task's commit. The
ordering invariant held mechanically.

### Why it matters

The two-model pipeline's entire context strategy rests on B receiving curated
artifacts only: `OUTCOME:` lines, the ledger, parsed review verdicts, and the
interfaces file. The docs are explicit:

- two-model-sdd-pipeline: *"B reads only what the scripts hand it — ... the
  interfaces file (`graphify-subgraph` → `task-N-interfaces.md`) for the next
  brief. B never reads raw coder/reviewer dispatch logs or full gate reports
  into context."*
- controller-brief-prompt: *"Query the graph subgraph first (via
  `scripts/cmd --full-file <ws>/task-N-graphify.txt -- graphify explain
  "Node"`) for the interfaces earlier tasks established; write from the
  subgraph + the plan entry, never whole files."*
- flutter-app-pipeline: *"graphify-subgraph ... extracts the
  affected-dependency slice ... into `<ws>/task-N-interfaces.md` for B's next
  brief and D's review."*

When B ignores the feed, it re-reads whole files into the interactive session,
which is exactly the context inflation the design removes. On a longer branch
this degrades to compaction churn and drift between what B "remembers" and
what the graph/plan actually say.

### Root cause

The skill documents describe the feed but provide **no enforced cue** that
forces B to read it before the next brief. B's brief-writing step is a free
LLM action; nothing in `route-next`/`orchestrator` output or in the brief
template says "read `task-(N-1)-interfaces.md` first." The instruction is
prose in three docs — easy to skip when the plan's verbatim blocks make the
brief self-sufficient. Rationalization observed: *"the plan.json and source
reads already carry the signatures, so the interfaces file is redundant."*

---

## Roadmap — candidate fixes (evaluation needed)

Each candidate below targets the gap from a different layer. They are NOT all
needed; the maintainer should pick per philosophy (deterministic script gate
vs. behavior-shaping skill text). Ordered from strongest to weakest
enforcement.

### Candidate 1 (strongest): hard gate — brief cannot reference a next-task interfaces file that exists unread

Deterministic, fits the "script decides" ethos:

- Add to the script layer a check that runs before red-gate dispatches C (or
  in `orchestrator` on the `BRIEF` action): when `task-N-brief.md` is being
  prepared, if `task-(N-1)-interfaces.md` exists AND `task-N-brief.md` does
  not yet mention it (no `interfaces:` line / no read marker), refuse to route
  `BRIEF` — emit a `BRIEF_NEEDS_INTERFACES` outcome instead.
- Concretely: extend the brief's `RED-TESTS:` block convention with a
  mandatory `INTERFACES:` line that names the file B read:
  `INTERFACES: task-3-interfaces.md`. red-gate (or a new `brief-gate`) exits 1
  when task N > 1 and the brief lacks that line.
- Pros: unmissable; deterministic; keeps B's freedom (it can read any subset,
  but must attest to having read the feed).
- Cons: adds a script + a convention; brief template changes; one more
  failure mode to test.

### Candidate 2: brief template — make the interfaces read a structural header

Behavior-shaping, no new gate:

- Update `controller-brief-prompt.md` to open every brief with a
  **"Subgraph feed (from task N-1)"** section that must be filled from
  `task-(N-1)-interfaces.md` — listing the consumed symbols and their files —
  BEFORE the Task statement. A brief that starts with the task statement and
  skips the feed section is structurally incomplete.
- Add the same requirement to the checklist in `two-model-sdd-pipeline`'s
  per-task loop (step 1: "read `task-(N-1)-interfaces.md`, restate its
  consumed symbols, then write the brief").
- Pros: no code; aligns with the "brief is behavioral encoding of exact
  values" philosophy; cheap.
- Cons: depends on B following a text instruction (the very thing that failed);
  needs eval to confirm it changes behavior.

### Candidate 3: feed the interfaces file into B's context automatically

Harness-level, strongest context guarantee:

- Have `graphify-subgraph` (or `orchestrator` after it) append the interfaces
  content into the artifact B is handed — e.g. the `route-next` `BRIEF`
  output line includes the path, or the orchestrator copies
  `task-(N-1)-interfaces.md` to `task-N-interfaces-feed.md` and prints its
  head on stdout so the next brief-write step sees it without a separate read.
- Pros: removes the "B forgot to read" class entirely for the common path.
- Cons: re-introduces curated-context-in-stdout, which the pipeline currently
  keeps in files; the interactive session still has to open the file.

### Candidate 4: reviewer-side signal

Let D's review package mark, in the verdict, whether the brief B wrote
referred to the interfaces file (`INTERFACES:` line). If absent, D logs a
process finding (not a code finding). Tracks recurrence over branches so the
maintainer can measure whether the text fix (Candidate 2) works.
- Pros: observability; no enforcement.
- Cons: adds a review-package concern; only reports, never prevents.

### Candidate 5 (weakest): documentation only

Expand `README-LLM.md` + the two skills with a bullet: *"Before writing brief
N+1, B MUST read `<ws>/task-N-interfaces.md` and must not pull whole source
files into context for symbols it lists."*
- Pros: zero code.
- Cons: pure prose — the exact layer that already failed once.

---

## Recommended path

1. **Ship Candidate 2 now** (brief template + skill checklist) — zero-code,
   aligns with the fork's behavior-shaping philosophy.
2. **Add Candidate 4** (reviewer notes absence) to get measurement.
3. After one or two branches of data, if the gap persists, **escalate to
   Candidate 1** (hard gate) — deterministic enforcement is the fork's
   strongest tool and the gap is exactly the kind of "LLM forgot a step" a
   gate exists to close.
4. Evaluate Candidate 3 only if the file-read latency/cost is the real
   blocker (unlikely here — the failure was omission, not expense).

## Acceptance criteria for the fix

- A brief for task N > 1 that does not engage the `task-(N-1)-interfaces.md`
  feed is either (a) rejected before C is dispatched, or (b) structurally
  incomplete by the template and flagged by D — never silently accepted.
- B's session context no longer re-reads whole source files for symbols that
  the interfaces feed already names.
- Pipeline test suite stays green; `doc-check` passes if skill/script text
  changed.