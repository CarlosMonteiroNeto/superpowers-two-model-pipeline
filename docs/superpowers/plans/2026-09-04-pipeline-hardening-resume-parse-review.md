# Pipeline Hardening: Corrective-Resume Reliability + Permanent Verdict Parsing

Date: 2026-09-04
Status: Approved (post-hoc, from post-merge investigation)
Branch context: two-model-sdd-pipeline fork

## Problem

Two defects surfaced after the category-skeleton branch merged:

1. **Corrective resume silently no-ops.** B writes a corrective brief by
   overwriting `task-N-brief.md` — the exact file path the resumed C session
   already read in round 1. The resumed model keeps the stale brief content in
   its cached context and, receiving the same generic dispatch prompt
   ("Read the attached file and execute per its instructions"), concludes
   "already implemented" instead of re-reading the changed file. Result: the
   corrective requirements never enter the model; B must fall back to a fresh
   dispatch (observed in task 4 and preemptively in task 6).

2. **The Reviewer verdict is parsed by an ad-hoc script, not the pipeline.**
   `two-model-sdd-pipeline/SKILL.md` claims "Script A parses [D's verdict] to
   `<workspace>/task-N-review.json`", but no script implements that parsing.
   During the final review an uncommitted `extract-review.py` had to be written
   in the workspace to unescape the JSONL event stream, locate the verdict
   object, and tolerate the reviewer's malformed trailing comma. That logic must
   be a permanent, tested pipeline script.

## Fixes

### 1. Resume reliability (`dispatch` + B-side brief convention)

- `skills/two-model-sdd-pipeline/scripts/dispatch`: when `--continue SESSION`
  is present, use a **corrective-round prompt** instead of the generic one —
  explicitly telling the resumed model the brief has changed, to re-read it
  fully, and not to assume prior work is complete.
- B-side convention (documented, enforced by prose in the skill):
  corrective briefs are written to a **distinct path** `task-N-corrective.md`;
  `task-N-brief.md` is never overwritten. `route-next`'s CORRECTIVE emission
  already hands control to B; B creates the corrective file and dispatches with
  `--continue --prompt-file task-N-corrective.md`.

### 2. Permanent verdict parsing (`parse-review`)

- New `skills/two-model-sdd-pipeline/scripts/parse_review.py` (pure python,
  importable + testable) and `scripts/parse-review` (bash wrapper, mirrors
  `template-score`/`pkg-score`):
  - Usage: `parse-review LOGFILE OUTFILE`
  - Reads the opencode JSON event stream (`--format json`) that `dispatch`
    tees to `<ws>/task-N-reviewer.log`.
  - Locates `text` events containing a verdict JSON object; unescapes the
    embedded text; extracts the object with balanced-brace parsing that
    tolerates prose before/after, trailing commas, newlines inside strings,
    and unicode escapes.
  - Writes pretty JSON to OUTFILE.
  - Exit codes: 0 = verdict written; 1 = no verdict found; 2 = usage.
- Wiring: B (or the orchestrator) runs `parse-review
  <ws>/task-N-reviewer.log <ws>/task-N-review.json` after D's log lands. The
  SKILL.md and README script tables document it, making the existing
  "parses it to task-N-review.json" claim true.
- The ad-hoc `extract-review.py` in the previous workspace is retired.

## Files

- `skills/two-model-sdd-pipeline/scripts/dispatch` (MODIFY — resume prompt)
- `skills/two-model-sdd-pipeline/scripts/parse_review.py` (NEW)
- `skills/two-model-sdd-pipeline/scripts/parse-review` (NEW)
- `skills/two-model-sdd-pipeline/controller-brief-prompt.md` (MODIFY —
  corrective path convention)
- `skills/two-model-sdd-pipeline/SKILL.md` (MODIFY — resume prompt, corrective
  path, parse-review wiring)
- `skills/two-model-sdd-pipeline/tests/test_dispatch.py` (MODIFY — resume
  prompt assertion)
- `skills/two-model-sdd-pipeline/tests/test_parse_review.py` (NEW)
- `README-LLM.md`, `README.txt` (MODIFY — doc-check gate)

## Tests

- `test_parse_review.py`: well-formed verdict extracted; prose + trailing
  comma + unicode tolerated; no-verdict → exit 1; usage → exit 2.
- `test_dispatch.py`: resume (`--continue`) prompt differs from fresh prompt
  and tells the model the brief changed.
- Both suites stay green; `scripts/doc-check` passes (READMEs updated).

## Verification

- `bash skills/two-model-sdd-pipeline/tests/run-tests.sh`
- `bash skills/flutter-app-pipeline/tests/run-tests.sh`
- `scripts/doc-check`
- Push to origin/main; the deleted plugin cache re-fetches on next start.