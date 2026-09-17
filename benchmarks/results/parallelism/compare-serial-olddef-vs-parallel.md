# Benchmark comparison — serial-olddef vs parallel

| Metric | Serial | Parallel | Delta (par - ser) |
|---|---|---|---|
| Wall-clock (s) | 1998.6 | 1083.0 | -915.6 |
| Speedup (serial/parallel) | - | - | 1.85x |
| LLM requests | 217 | 185 | -32 |
| Uncached tokens | 471144 | 374380 | -96764 |
| Cache-hit % | 90.5 | 89.0 | -1.5 |
| Cost | 0.114963 | 0.091772 | -0.023191 |

Parallel was **1.85x faster** in wall-clock time.

