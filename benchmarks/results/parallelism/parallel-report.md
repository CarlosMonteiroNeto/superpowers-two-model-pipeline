# Benchmark report — parallel

| Metric | Value |
|---|---|
| Total wall-clock (s) | 1083.0 |
| LLM requests | 185 |
| Cache-hit % | 89.0 |
| Uncached tokens (in+out+reasoning) | 374380 |
| Cache read tokens | 2511488 |
| Cache write tokens | 0 |
| Cost | 0.091772 |

## Per role

| Role | Requests | Input | Output | Reasoning | Cache read | Span (s) |
|---|---|---|---|---|---|---|
| coder | 154 | 184271 | 28364 | 14750 | 2313088 | 938.6 |
| reviewer | 28 | 103946 | 5762 | 10827 | 183424 | 133.9 |
| director | 3 | 23762 | 1305 | 1393 | 14976 | 17.8 |

## Per task

| Task | Status | Rounds | Brief (s) | Gate (s) | Coder req | Coder span (s) | Reviewer req | Reviewer span (s) |
|---|---|---|---|---|---|---|---|---|
| 1 | APPROVED | 0 | 1.0 | 87.8 | 14 | 99.5 | 2 | 8.1 |
| 2 | APPROVED | 0 | 0.0 | 85.4 | 17 | 104.3 | 2 | 14.7 |
| 3 | APPROVED | 0 | 0.0 | 62.0 | 16 | 139.9 | 2 | 8.5 |
| 4 | APPROVED | 0 | 0.0 | 75.3 | 17 | 130.6 | 7 | 26.0 |
| 5 | APPROVED | 0 | 1.0 | 58.7 | 12 | 70.3 | 2 | 11.6 |
| 6 | APPROVED | 0 | 1.0 | 58.8 | 14 | 70.6 | 2 | 8.4 |
| 7 | APPROVED | 0 | 0.0 | 54.4 | 15 | 82.1 | 2 | 7.7 |
| 8 | APPROVED | 0 | 0.0 | 69.0 | 13 | 68.2 | 2 | 9.3 |
| 9 | APPROVED | 0 | 0.0 | 88.8 | 17 | 83.6 | 2 | 8.1 |
| 10 | APPROVED | 0 | 0.0 | 83.5 | 19 | 89.5 | 5 | 31.7 |

