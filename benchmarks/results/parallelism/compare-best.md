# Benchmark comparison — serial-best vs parallel-best

| Metric | Serial | Parallel | Delta (par - ser) |
|---|---|---|---|
| Wall-clock (s) | 2122.0 | 919.9 | -1202.1 |
| Speedup (serial/parallel) | - | - | 2.31x |
| LLM requests | 284 | 260 | -24 |
| Uncached tokens | 637645 | 508317 | -129328 |
| Cache-hit % | 92.7 | 92.0 | -0.7 |
| Cost | 0.167889 | 0.128692 | -0.039197 |

Parallel was **2.31x faster** in wall-clock time.

