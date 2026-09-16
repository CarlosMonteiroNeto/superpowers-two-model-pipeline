# Pipeline Parallelism Benchmark

Measures the cost of the two-model pipeline **before** parallel task
execution (the serial engine) against the **current** engine (waves +
worktrees), on an identical 10-task workload.

This harness is deliberately implemented as TDD tooling, independent of the
pipeline it measures. It never modifies the pipeline: the engine is checked
out clean from a git ref into a throwaway worktree, and the harness lives
outside the measured repository.

## What is compared

| Side | Engine ref | Command |
|---|---|---|
| serial (baseline) | `d5c0868` — the last commit on `main` before the `feat/parallel-task-execution` branch merged | `run-pipeline PLAN --no-push` |
| parallel | `origin/main` | `run-pipeline PLAN --no-push --max-parallel 5` |

Both sides run the same 10-task plan against the same fixture, sequentially
on the same machine (never concurrently — parallel runs would distort cache
state and provider rate limits).

The parallel side uses `--max-parallel 5` so `wave-next` emits two waves of
five (`5 de cada lado`); the serial side runs all ten one at a time.

## Metrics

Per task and per role (`coder` = Agente operador, `reviewer` = Agente revisor,
`director` = Agente diretor), derived only from the pipeline's own artifacts:

- **pure token cost** — uncached `input` + `output` + `reasoning`, plus
  `cache.read` / `cache.write` separately (from each `step_finish` event);
- **cache-hit %** — `cache.read / (cache.read + input)`;
- **LLM requests** — the count of `step_finish` events (one per API call);
- **wall-clock** — total run time, plus per-stage spans reconstructed from
  the dispatch logs' millisecond timestamps and the ledger timeline
  (brief, gate, operador, revisor);
- **correction rounds** — from the per-task ledger.

Source of truth: `<workspace>/task-N-coder.log` and `task-N-reviewer.log`
(the `opencode run --format json` event streams `dispatch` already tees) and
`<workspace>/ledger.jsonl`.

## Layout

```
benchmarks/
  fixture/                 Dart package template (10 stub features + smoke test + spec)
  plans/                   the 10-task plan.json
  scripts/run-side         run one side; writes <work>/result.json
  scripts/bench_report.py  analyzer (log + ledger -> metrics)   [unit-tested]
  scripts/bench_compare.py serial vs parallel deltas            [unit-tested]
  scripts/report, compare  thin CLI wrappers
  run-benchmark            orchestrator: runs the side(s) and writes reports
  tests/                   python unittest suite (run-tests.sh)
  results/<name>/          reports (serial-report.md/json, parallel-report.md/json, compare.md)
```

## Running

Baseline (serial engine) — already run for this branch:

```bash
bash benchmarks/run-benchmark --only serial --serial-ref d5c0868 \
  --results-dir benchmarks/results/parallelism
```

Parallel side, once `origin/main` carries the engine you want to measure
(fetch first so the ref is current):

```bash
git fetch origin
bash benchmarks/run-benchmark --only parallel --parallel-ref origin/main \
  --max-parallel 5 --results-dir benchmarks/results/parallelism
```

Running the parallel step into the same `--results-dir` automatically emits
`compare.md` / `compare.json` (serial vs parallel speedup). Both sides in one
go: drop `--only`.

Scratch (engine worktree + fixture repo) is created under the gitignored
`.superpowers/bench/<results-name>/`; only reports land in `results/`.

## Baseline result (serial engine, `d5c0868`)

Run on 2026-09-16, all 10 tasks approved, `--no-push`:

| Metric | Serial |
|---|---|
| Total wall-clock | 1394.5 s (~23.2 min) |
| LLM requests | 188 |
| Cache-hit % | 89.5 |
| Uncached tokens (in+out+reasoning) | 442,911 |
| Cache-read tokens | 3,186,944 |
| Cost | 0.107342 |
| Coder / reviewer / director span | 675.3 / 217.3 / 17.1 s |
| Correction rounds | 0 (all tasks approved first review) |

The per-task `gate` column (~9-12 s) is the script window from the operador's
dispatch ending to the commit; the remaining wall-clock is gate execution,
integration, closing and provider latency.

Full artifacts: `results/parallelism/serial-report.{md,json}` and
`serial-result.json`.

## Best-condition pair (same engine, same agent definitions)

The controlled answer to "would a non-parallel version with the improvements
beat the current parallel one?" Both sides use the identical engine
(`origin/main` = `dda0b0a`) and the identical corrected, `rtk-run`-enabled
agent definitions, so the only variable is wave width — the delta is wave
scheduling alone.

| Metric | serial (`--max-parallel 1`) | parallel (`--max-parallel 2`) |
|---|---|---|
| Wall-clock | 2122.0 s | 919.9 s (**2.31x faster**) |
| LLM requests | 284 | 260 |
| Uncached tokens | 637,645 | 508,317 |
| Cache-hit % | 92.7 | 92.0 |
| Cost | 0.167889 | 0.128692 |

**No** — the non-parallel version is much slower. Parallelism is the decisive
factor, not the general improvements: on the same engine, dropping to one lane
costs 2.31x.

Caveat observed while collecting this: the hardened allowlist (ADR-0016 drops
`bash*`/`python*`) causes permission-denial churn on Windows, where the
operador's shell is PowerShell and it reaches for `Get-ChildItem` / `Test-Path`
/ `Get-Content` — 47 denials in the serial run, 27 in the parallel run. It
inflates both sides; serial pays it in full, parallel partly absorbs it in
overlap.

Full artifacts: `results/parallelism/{serial-best,parallel-best}-report.{md,json}`
and `compare-best.{md,json}`.

## Lane-width sweep (same engine, same agent defs)

Same engine (`origin/main` = `dda0b0a`) and same agent definitions on each
side; only the wave width differs.

| Lanes | Waves | Wall-clock | Requests | Uncached tokens | Cost |
|---|---|---|---|---|---|
| 1 (serial) | 10 | 1993.8 s | 252 | 510,444 | 0.129344 |
| 5 | 2 | 820.6 s | 233 | 440,584 | 0.112718 |

1 -> 5 lanes is **2.43x** faster. (The 2-lane row elsewhere in this file used
an earlier agent-def revision, so treat it as indicative only.)

Denial-churn note: adding the platform-generic read-only allowances took the
serial run's permission denials from 47 to 17 (parallel 27 -> 12) but barely
moved wall-clock (2122.0 -> 1993.8 s). So the denial churn was **not** the
dominant cost — the earlier 1395 -> 2122 regression is mostly provider-latency
variance across a 10-task serial run (one reviewer call alone was 357.8 s),
plus more per-task steps. Single runs are noisy; attribute with repeats.

Full artifacts: `results/parallelism/{serial-1lane,parallel-5lane}-report.{md,json}`
and `compare-serial-1lane-vs-parallel-5lane.{md,json}`.

## Non-interactive by construction

The benchmark must not pause for approvals, or the timing is wrong:

- tier agents are pre-configured (no gate question);
- `resolve-toolchain` auto-detects `pubspec.yaml` -> `lang=flutter`;
- the tier agents use `allow`/`deny` permissions with no `ask`, so no prompt
  blocks a dispatch;
- `run-pipeline` runs with `--no-push` (no PR creation).

## Tests

```bash
bash benchmarks/tests/run-tests.sh
```

Covers the analyzer (hand-derived numbers from synthetic logs), the fixture
and plan validity (validated against the engine's own `brief-scaffold`),
the runner (stub engine: worktree, scratch repo, command construction,
timing, exit-code propagation) and the orchestrator (stub engine: reports
and comparison).
