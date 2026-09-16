# Benchmark comparison ù serial vs parallel

| Metric | Serial | Parallel | Delta (par - ser) |
|---|---|---|---|
| Wall-clock (s) | 1394.5 | 2025.0 | 630.5 |
| Speedup (serial/parallel) | - | - | 0.69x |
| LLM requests | 188 | 5 | -183 |
| Uncached tokens | 442911 | 34476 | -408435 |
| Cache-hit % | 89.5 | 70.6 | -18.9 |
| Cost | 0.107342 | 0.007833 | -0.099509 |

Parallel was **1.45x slower** in wall-clock time.

