# Benchmark comparison — serial vs parallel

| Metric | Serial | Parallel | Delta (par - ser) |
|---|---|---|---|
| Wall-clock (s) | 1394.5 | 1083.0 | -311.5 |
| Speedup (serial/parallel) | - | - | 1.29x |
| LLM requests | 188 | 185 | -3 |
| Uncached tokens | 442911 | 374380 | -68531 |
| Cache-hit % | 89.5 | 89.0 | -0.5 |
| Cost | 0.107342 | 0.091772 | -0.015570 |

Parallel was **1.29x faster** in wall-clock time.

