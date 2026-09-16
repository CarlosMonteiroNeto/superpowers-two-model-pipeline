# Benchmark comparison — serial-1lane vs parallel-5lane

| Metric | Serial | Parallel | Delta (par - ser) |
|---|---|---|---|
| Wall-clock (s) | 1993.8 | 820.6 | -1173.2 |
| Speedup (serial/parallel) | - | - | 2.43x |
| LLM requests | 252 | 233 | -19 |
| Uncached tokens | 510444 | 440584 | -69860 |
| Cache-hit % | 91.5 | 91.5 | +0.0 |
| Cost | 0.129344 | 0.112718 | -0.016626 |

Parallel was **2.43x faster** in wall-clock time.

