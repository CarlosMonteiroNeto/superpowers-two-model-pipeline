# Two-model pipeline vs standard TDD — full run record

All runs implement the same ten-task fixture plan
(`benchmarks/plans/2026-09-16-parallelism-benchmark-plan.json`) in a pure-Dart
package, verified by `flutter test`. Every run used
`opencode-go/deepseek-v4.1-flash` for every agent role.

Metrics are derived from the pipeline's own artifacts: each `opencode run --format json`
event stream (`task-N-coder.log`, `task-N-reviewer.log`, or the single `tdd.log`) and the
JSONL ledger. One `step_finish` event counts as one LLM request.

## Metric definitions

| Metric | Definition |
|---|---|
| Requests | number of `step_finish` events = LLM API calls |
| Uncached tokens | `input + output + reasoning` (the non-cache-hit portion) |
| Cache read / write | tokens served from, and written to, the provider prompt cache |
| Cache-hit % | `cache_read / (cache_read + input)` |
| Cost (US$) | sum of the `cost` field the provider reports per step |
| Wall-clock | measured around the whole run (dispatch to completion) |
| **Latency-equalised time** | `wall - Σspans + R × L̄`, where `Σspans` is the sum of all dispatch durations and `L̄` is the request-weighted mean latency across every run below. This replaces each run's own provider latency with the global mean, so runs can be compared without a fast/slow provider window dominating. |

### L̄ (global mean latency)

`Σspans / Σrequests` over all nine runs = **6.126 s/request**.

## Run specifications

| # | Run | Engine ref | Lanes | Brief (RED order) | Agent definitions | Allowlist |
|---|---|---|---|---|---|---|
| 1 | serial | pre-parallel `d5c0868` | 1 | old (no runner mandate) | stale generation | old |
| 2 | parallel | `dda0b0a` | 2 | **mandates** `rtk-run`; forbids full suite | stale generation | old |
| 3 | serial-best | `dda0b0a` | 1 | mandates `rtk-run` | corrected (no cmdlets) | old |
| 4 | parallel-best | `dda0b0a` | 2 | mandates `rtk-run` | corrected (no cmdlets) | old |
| 5 | serial-1lane | `dda0b0a` | 1 | mandates `rtk-run` | corrected + read-only | cmdlets |
| 6 | parallel-5lane | `dda0b0a` | 5 | mandates `rtk-run` | corrected + read-only | cmdlets |
| 7 | serial-olddef | `dda0b0a` | 1 | mandates `rtk-run` | stale generation | old |
| 8 | par2-final | `HEAD` | 2 | **offers** `rtk-run`; coder-gate owns suite | new semantics, flexible | flex (cmdlets + bash/python) |
| 9 | plain-tdd | none (raw agent dispatch) | 1 session | inline acceptance list, plain TDD | live definition | flex |

The eight pipeline runs differ from each other only in the columns above. `par2-final`
additionally carries the relaxed brief text and the relaxed coder prose (commits
`ae5edce`, `faa2a2b`); everything else in the engine (`run-pipeline`, `wave-next`,
`worktree-*`, `integrate`, `task-run`, `coder-gate`, `dispatch`) is byte-identical to
`dda0b0a`.

## Results — all runs

| Run | Lanes | Wall (s) | **Latency-eq (s)** | Requests | Uncached | Cache read | Cache write | Cache-hit | Cost (US$) |
|---|---|---|---|---|---|---|---|---|---|
| 1 serial | 1 | 1394.5 | **1636.6** | 188 | 442,911 | 3,186,944 | 0 | 89.5% | 0.107342 |
| 2 parallel | 2 | 1083.0 | **1126.0** | 185 | 374,380 | 2,511,488 | 0 | 89.0% | 0.091772 |
| 3 serial-best | 1 | 2122.0 | **2061.8** | 284 | 637,645 | 6,604,288 | 0 | 92.7% | 0.167889 |
| 4 parallel-best | 2 | 919.9 | **1414.9** | 260 | 508,317 | 4,867,328 | 0 | 92.0% | 0.128692 |
| 5 serial-1lane | 1 | 1993.8 | **2164.4** | 252 | 510,444 | 4,567,808 | 0 | 91.5% | 0.129344 |
| 6 parallel-5lane | 5 | 820.6 | **390.5** | 233 | 440,584 | 3,924,352 | 0 | 91.5% | 0.112718 |
| 7 serial-olddef | 1 | 1998.6 | **1965.2** | 217 | 471,144 | 3,805,056 | 0 | 90.5% | 0.114963 |
| 8 par2-final | 2 | 1740.2 | **1363.2** | 232 | 411,332 | 3,845,248 | 0 | 92.0% | 0.108860 |
| 9 plain-tdd | 1 session | 356.1 | **306.0** | 47 | 44,873 | 1,197,952 | 0 | 97.5% | 0.016612 |

## Results — per role (pipeline runs)

| Run | coder req / US$ | reviewer req / US$ | director req / US$ |
|---|---|---|---|
| 1 serial | 142 / 0.068474 | 43 / 0.034029 | 3 / 0.004839 |
| 2 parallel | 154 / 0.060448 | 28 / 0.026096 | 3 / 0.005228 |
| 3 serial-best | 233 / 0.125302 | 48 / 0.037105 | 3 / 0.005481 |
| 4 parallel-best | 219 / 0.095637 | 38 / 0.028092 | 3 / 0.004963 |
| 5 serial-1lane | 200 / 0.090258 | 49 / 0.033656 | 3 / 0.005431 |
| 6 parallel-5lane | 189 / 0.079076 | 41 / 0.028002 | 3 / 0.005640 |
| 7 serial-olddef | 166 / 0.077706 | 48 / 0.032801 | 3 / 0.004456 |
| 8 par2-final | 181 / 0.071038 | 47 / 0.031989 | 4 / 0.005832 |
| 9 plain-tdd | single session: 47 req / 0.016612 | (no separate reviewer) | (none) |

Token split, all runs (`input` = uncached):

| Run | input | output | reasoning | cache read | cache write |
|---|---|---|---|---|---|
| 1 serial | 373,257 | 38,109 | 31,545 | 3,186,944 | 0 |
| 2 parallel | 311,979 | 35,431 | 26,970 | 2,511,488 | 0 |
| 3 serial-best | 521,136 | 50,149 | 66,360 | 6,604,288 | 0 |
| 4 parallel-best | 424,223 | 46,816 | 37,278 | 4,867,328 | 0 |
| 5 serial-1lane | 423,612 | 51,357 | 35,475 | 4,567,808 | 0 |
| 6 parallel-5lane | 363,123 | 43,918 | 33,543 | 3,924,352 | 0 |
| 7 serial-olddef | 398,085 | 40,664 | 32,395 | 3,805,056 | 0 |
| 8 par2-final | 332,167 | 44,620 | 34,545 | 3,845,248 | 0 |
| 9 plain-tdd | 30,902 | 9,897 | 4,074 | 1,197,952 | 0 |

## Factor isolation (matched pairs, one factor each)

Ratios are `variant / base`. Time uses the latency-equalised metric.

| Factor | Base | Variant | Cost ratio | Latency-eq ratio |
|---|---|---|---|---|
| Lanes (1→2) | 3 serial-best | 4 parallel-best | ×0.77 (-23%) | ×0.69 (-31%) |
| Lanes (1→2) | 7 serial-olddef | 2 parallel | ×0.80 (-20%) | ×0.57 (-43%) |
| Lanes (1→5) | 5 serial-1lane | 6 parallel-5lane | ×0.87 (-13%) | ×0.18 (-82%) |
| Def generation (stale→new) | 7 serial-olddef | 3 serial-best | ×1.46 (+46%) | ×1.05 (+5%) |
| Def generation (stale→new) | 2 parallel | 4 parallel-best | ×1.40 (+40%) | ×1.26 (+26%) |
| Allowlist (old→flexible) | 3 serial-best | 5 serial-1lane | ×0.77 (-23%) | ×1.05 (+5%) |
| Brief+def (mandatory→optional) | 4 parallel-best | 8 par2-final | ×0.85 (-15%) | ×0.96 (-4%) |
| Engine+brief (pre-parallel→new) | 1 serial | 7 serial-olddef | ×1.07 (+7%) | ×1.20 (+20%) |

### Factor summary

| Factor | Cost | Latency-equalised time |
|---|---|---|
| Lanes (parallelism) | −13% to −23% | −31% to −82% |
| Def generation (new semantics) | **+40% / +46%** | +5% / +26% |
| Allowlist (read-only + interpreters + rtk) | −23% | +5% |
| Brief mandatory → optional (with flexible defs) | −15% | −4% |
| Engine+brief (pre-parallel → new engine) | +7% | +20% |

Reviewer contribution to the def-generation cost penalty: **5%** (2-lane pair) and
**8%** (1-lane pair) — the coder explains 90-95%.

## Standard TDD vs the pipeline

Plain TDD (one session, no brief/reviewer/gates) finished the same ten tasks verified
green. Multiples below are **pipeline ÷ plain TDD**:

| Compared with | Cost | Latency-eq time | Wall-clock |
|---|---|---|---|
| 6 parallel-5lane | ×6.79 | ×1.28 | ×2.30 |
| 2 parallel | ×5.52 | ×3.68 | ×3.04 |
| 1 serial | ×6.46 | ×5.35 | ×3.92 |
| 5 serial-1lane | ×7.79 | ×7.07 | ×5.60 |

Plain TDD: **47 requests, 44,873 uncached tokens, 1,197,952 cache-read, 97.5% cache-hit,
US$0.016612, 356.1 s**, `flutter test` on the final tree exited 0.

Why the gap, structurally:

- The pipeline runs **many small stateless dispatches**: one per role per task, each
  re-sending the stable prefix (that is what the 3.8-6.6M cache-read tokens buy). Plain
  TDD keeps one growing session, so it re-reads the prefix far less often.
- The pipeline pays **gates** on the script side (`dart format` + the full suite +
  `analyze` per task in a worktree) plus per-task worktree setup and integration.
- Plain TDD pays none of that, but it also provides **no independent check**: nothing
  verifies that the tests actually encode the acceptance. It is the fastest and cheapest
  precisely because it removes the pipeline's guarantees, not because it is better.

## Caveats

- **n = 1 per configuration.** Provider latency varies by a factor of ~2 between runs;
  the latency-equalised column removes the *mean* shift but not run-to-run noise.
- The **brief is not isolable** on its own: the pre-mandate brief exists only in run 1,
  which also carries the pre-parallel engine. The `mandatory → optional` estimate comes
  from the `4 → 8` pair, which changes the definitions too.
- Plain TDD produced **no independent semantic check**: the pipeline's reviewer is the
  only mechanism that verifies the tests actually encode the acceptance. All pipeline
  runs here had 0 correction rounds, so that mechanism did not fire on this fixture —
  it cannot be scored from these numbers.
- Engine and brief are coupled: the brief text is generated by the engine's
  `brief-scaffold`, so "engine" and "brief" cannot be separated by ref alone.

