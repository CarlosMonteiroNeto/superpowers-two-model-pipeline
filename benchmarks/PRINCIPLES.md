# Cost & time principles of the two-model pipeline (measured)

Derived from the run record in `results/parallelism/BENCHMARK-REPORT.md`
(ten identical tasks, same fixture and plan, `opencode-go/deepseek-v4.1-flash`
for every role). Use this as an audit checklist: every principle below is a
question you can ask of any stage of the pipeline.

## The model

```
LLM cost  ≈ steps × context_per_step × price_per_token_type
LLM time  ≈ latency_per_step × steps / lanes
wall      ≈ LLM time (overlapped) + script-side time + serial tail
```

Consequences that fall out of the model:

- **Steps are the lever, not verbosity.** Output tokens are 6–8K per role; the
  cached prefix re-read every step is 180K–6.6M. One extra step costs more than
  a longer answer.
- **Cache is what makes the prefix affordable** (`cache_read` ≈ 10% of an
  uncached token, measured: `cache_read/(cache_read+input)` = 89–93% in every
  run). That is why the context must be a *stable prefix + appended deltas*:
  a change in the middle invalidates the cached prefix and bills it fresh.
- **Deterministic scripts cost zero tokens.** Every script
  (`brief-scaffold`, `route-next`, `coder-gate`, `red-form-check`,
  `keep-discard`, `integrate`, `wave-next`, `ledger-*`) runs without an LLM
  call. 100% of measured cost is in the dispatches.

## Principles (each with the measurement that produced it)

**P1 — Count dispatches, not tokens.** Cost tracks the number of LLM steps.
`2 parallel` → `4 parallel-best` (same plan, same lanes, a def change that only
removed shell permissions) went from 185 to 260 requests and +40% cost, while
tokens-per-request barely moved. *Audit: for each stage, how many dispatches
does it cause per task? A stage that adds a dispatch must justify it.*

**P2 — A denied tool call is a paid extra step.** Every permission denial
becomes a model turn. Removing `bash*`/`python*` and the read-only allowances
produced 47 denials and +40% cost; restoring the read-only set took denials to
17 and cost −25%. *Audit: does any allowlist force the agent to guess and
retry? Denials are a cost signal, not a safety win in themselves.*

**P3 — Any protocol step whose output nothing consumes is pure cost.** The
brief required the operador to DECLARE the RED failure reason and save it; no
script ever read that file (`red-form-check` reads only `task-N-red.txt`).
Removing it deletes steps without weakening any verdict. *Audit: grep for every
artifact a brief/def asks for, then confirm a script consumes it.*

**P4 — Gates should be deterministic and free; their false negatives are not.**
A gate that decides by exit code costs no tokens. But a strict form check on an
LLM-produced artifact can reject valid work and trigger a paid retry round
(observed: RED evidence saved as UTF-16, `red-form-check` read UTF-8 → FAIL
round). *Audit: for each gate, what happens on a false negative, and is the
artifact's form guaranteed?*

**P5 — Semantics is free; permissions and protocols are not.** Swapping the
agent-definition *prose* (new RED/runner wording, reviewer scope, punctual
director) changed effective tokens by ×1.00. What changed cost was the
allowlist (+52–59% when tightened) and the brief's protocol steps. *Audit: do
not trade quality wording for cost; do trade permissions and protocol.*

**P6 — Fresh per-task sessions bound the context; one long session does not.**
Per-task dispatches start at ~8.8K tokens every task and never exceed that
task's work. A single-session run (plain TDD) grew 8.7K → 39.6K over 47 steps
(4.5×) and never reset: cost ≈ O(n²) in tasks vs O(n). On this fixture the
single session was still 3.8× cheaper in effective tokens — the crossover is at
a large n, and the binding limit is the context window (and compaction), not
cost. *Audit: does any role accumulate context across tasks?*

**P7 — Parallelism reduces both time and cost.** Lanes 1→2: −23% cost, −31%
time. Lanes 1→5: −14% cost, −80% time (three independent pairs). Cost falls
because each shard is a bounded, cache-warm session. *Audit: is independent
work serialized only because nobody declared it independent?*

**P8 — The suite prohibition pays for itself.** With the old brief the operador
ran the full suite 7× per run (`dart test`, no file); with the new brief, 0× —
it uses the scoped runner instead. Here that is ~5–7% of wall-clock because the
fixture suite is ~10 s; the saving scales with suite duration. *Audit: does the
implementer duplicate a suite the gate already owns?*

**P9 — Script-side can dominate the parallel critical path.** `gate_s` per task
was 9–12 s serial but 58–311 s in the parallel runs: the gate's own suite is
~10 s, the rest is **cold worktree compile**. *Audit: measure script stages
separately from dispatch stages; the worktree warm-up is the current candidate.*

**P10 — Wall-clock is provider noise before it is anything else.** Latency per
request ranged 4.2–8.0 s across runs; one 357.8 s stall moved a 2,122 s run by
17%. Single-run time comparisons cannot decide a configuration. *Audit: never
conclude on time from n=1; compare latency-equalised medians over repeats.*

**P11 — Price windows break absolute dollars, not ratios.** The reported `cost`
field is a static list price (its $/Mtoken is flat across peak and off-peak —
verified). Real billing halves off-peak, so absolute rankings change while
within-window ratios do not. *Audit: compare configurations with effective
tokens (`uncached + 0.1 × cache_read`), which is price- and window-neutral.*

## Reusable audit checklist

1. **Dispatch census** — list every LLM dispatch a stage causes, per task (P1).
2. **Orphan artifacts** — for every file/prompt a brief asks the agent to
   produce, name the script that consumes it (P3).
3. **Denial probe** — count `prevents you` in the dispatch logs; treat any
   count > 0 as a defect to fix in the allowlist (P2).
4. **Duplicate work** — does any step re-run what another step already ran, or
   what the gate owns (P5, P8)?
5. **Context lifetime** — is the prefix stable and appended-to, and does
   context reset between tasks (P6)?
6. **Script-vs-LLM split** — measure gate/script seconds separately from
   dispatch seconds (P9).
7. **Repetition before conclusion** — for time, ≥3 runs per configuration and
   compare medians of the latency-equalised time (P10).
8. **Price normalisation** — rank by effective tokens; use dollars only with
   the window factor applied (P11).

## How many lanes?

`lanes_effective = min(ready tasks with pairwise-disjoint touches, --max-parallel,
provider/rate budget, machine capacity)`, and the speedup is capped by the
serial tail (integration + closing) — Amdahl, not CPU.

Measured here (ten tiny, fully independent tasks): 1→2 lanes −31% time,
1→5 lanes −80% time; and cost fell in both steps. That is the optimistic case.
The binding constraint is usually the **plan**, not the PC: `wave-next` only
co-schedules tasks whose `touches` are disjoint, so a plan full of shared files
collapses to waves of one. The way to know is a **sweep**: same plan at 1, 2, 5,
10 lanes, repeated, and find the knee where time stops falling while integration
time keeps rising.
