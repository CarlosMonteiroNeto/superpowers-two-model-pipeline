# Benchmark report — serial-best

| Metric | Value |
|---|---|
| Total wall-clock (s) | 2122.0 |
| LLM requests | 284 |
| Cache-hit % | 92.7 |
| Uncached tokens (in+out+reasoning) | 637645 |
| Cache read tokens | 6604288 |
| Cache write tokens | 0 |
| Cost | 0.167889 |

## Per role

| Role | Requests | Input | Output | Reasoning | Cache read | Span (s) |
|---|---|---|---|---|---|---|
| coder | 233 | 367842 | 39820 | 46423 | 6126720 | 1153.9 |
| reviewer | 48 | 131940 | 9153 | 17389 | 462976 | 624.5 |
| director | 3 | 21354 | 1176 | 2548 | 14592 | 21.6 |

## Per task

| Task | Status | Rounds | Brief (s) | Gate (s) | Coder req | Coder span (s) | Reviewer req | Reviewer span (s) |
|---|---|---|---|---|---|---|---|---|
| 1 | APPROVED | 0 | 2.0 | 10.4 | 19 | 78.3 | 7 | 29.8 |
| 2 | APPROVED | 0 | 3.0 | 9.2 | 21 | 226.9 | 2 | 11.1 |
| 3 | APPROVED | 0 | 2.0 | 9.0 | 23 | 90.8 | 5 | 357.8 |
| 4 | APPROVED | 0 | 2.0 | 9.0 | 22 | 87.5 | 2 | 7.3 |
| 5 | APPROVED | 0 | 2.0 | 8.7 | 21 | 115.7 | 7 | 90.0 |
| 6 | APPROVED | 0 | 2.0 | 9.0 | 19 | 66.5 | 7 | 19.6 |
| 7 | APPROVED | 0 | 2.0 | 8.9 | 17 | 66.8 | 2 | 6.5 |
| 8 | APPROVED | 0 | 2.0 | 9.4 | 29 | 128.3 | 2 | 41.2 |
| 9 | APPROVED | 0 | 2.0 | 9.5 | 21 | 89.8 | 9 | 31.5 |
| 10 | APPROVED | 0 | 2.0 | 10.1 | 41 | 203.3 | 5 | 29.7 |

