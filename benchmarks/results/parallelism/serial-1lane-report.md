# Benchmark report — serial-1lane

| Metric | Value |
|---|---|
| Total wall-clock (s) | 1993.8 |
| LLM requests | 252 |
| Cache-hit % | 91.5 |
| Uncached tokens (in+out+reasoning) | 510444 |
| Cache read tokens | 4567808 |
| Cache write tokens | 0 |
| Cost | 0.129344 |

## Per role

| Role | Requests | Input | Output | Reasoning | Cache read | Span (s) |
|---|---|---|---|---|---|---|
| coder | 200 | 269468 | 41189 | 21292 | 4116480 | 1139.1 |
| reviewer | 49 | 130542 | 8620 | 12654 | 436608 | 213.8 |
| director | 3 | 23602 | 1548 | 1529 | 14720 | 20.3 |

## Per task

| Task | Status | Rounds | Brief (s) | Gate (s) | Coder req | Coder span (s) | Reviewer req | Reviewer span (s) |
|---|---|---|---|---|---|---|---|---|
| 1 | APPROVED | 0 | 5.0 | 19.0 | 22 | 131.1 | 7 | 34.2 |
| 2 | APPROVED | 0 | 4.0 | 19.2 | 25 | 133.5 | 5 | 21.3 |
| 3 | APPROVED | 0 | 4.0 | 12.6 | 17 | 79.7 | 5 | 18.3 |
| 4 | APPROVED | 0 | 4.0 | 21.0 | 20 | 172.9 | 8 | 27.9 |
| 5 | APPROVED | 0 | 3.0 | 23.1 | 21 | 107.4 | 4 | 27.0 |
| 6 | APPROVED | 0 | 4.0 | 22.1 | 18 | 104.7 | 9 | 32.4 |
| 7 | APPROVED | 0 | 4.0 | 14.5 | 14 | 74.4 | 2 | 6.9 |
| 8 | APPROVED | 0 | 3.0 | 18.8 | 24 | 125.4 | 2 | 7.5 |
| 9 | APPROVED | 0 | 4.0 | 18.7 | 23 | 121.3 | 2 | 9.6 |
| 10 | APPROVED | 0 | 3.0 | 14.2 | 16 | 88.7 | 5 | 28.7 |

