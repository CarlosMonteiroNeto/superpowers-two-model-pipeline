# Benchmark report — parallel-best

| Metric | Value |
|---|---|
| Total wall-clock (s) | 919.9 |
| LLM requests | 260 |
| Cache-hit % | 92.0 |
| Uncached tokens (in+out+reasoning) | 508317 |
| Cache read tokens | 4867328 |
| Cache write tokens | 0 |
| Cost | 0.128692 |

## Per role

| Role | Requests | Input | Output | Reasoning | Cache read | Span (s) |
|---|---|---|---|---|---|---|
| coder | 219 | 290210 | 39281 | 24708 | 4570624 | 943.6 |
| reviewer | 38 | 110441 | 6335 | 11464 | 282112 | 139.3 |
| director | 3 | 23572 | 1200 | 1106 | 14592 | 14.9 |

## Per task

| Task | Status | Rounds | Brief (s) | Gate (s) | Coder req | Coder span (s) | Reviewer req | Reviewer span (s) |
|---|---|---|---|---|---|---|---|---|
| 1 | APPROVED | 0 | 1.0 | 51.7 | 26 | 113.8 | 2 | 9.4 |
| 2 | APPROVED | 0 | 0.0 | 45.4 | 27 | 120.8 | 2 | 9.1 |
| 3 | APPROVED | 0 | 0.0 | 61.2 | 16 | 70.4 | 5 | 15.6 |
| 4 | APPROVED | 0 | 0.0 | 42.0 | 22 | 89.8 | 2 | 8.9 |
| 5 | APPROVED | 0 | 1.0 | 60.3 | 18 | 86.2 | 2 | 7.2 |
| 6 | APPROVED | 0 | 0.0 | 63.7 | 16 | 83.2 | 9 | 27.2 |
| 7 | APPROVED | 0 | 1.0 | 56.4 | 26 | 103.7 | 8 | 22.5 |
| 8 | APPROVED | 0 | 0.0 | 63.6 | 23 | 97.7 | 3 | 8.1 |
| 9 | APPROVED | 0 | 0.0 | 89.2 | 17 | 70.5 | 2 | 10.4 |
| 10 | APPROVED | 0 | 0.0 | 52.5 | 28 | 107.4 | 3 | 20.7 |

