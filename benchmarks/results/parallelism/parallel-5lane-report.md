# Benchmark report — parallel-5lane

| Metric | Value |
|---|---|
| Total wall-clock (s) | 820.6 |
| LLM requests | 233 |
| Cache-hit % | 91.5 |
| Uncached tokens (in+out+reasoning) | 440584 |
| Cache read tokens | 3924352 |
| Cache write tokens | 0 |
| Cost | 0.112718 |

## Per role

| Role | Requests | Input | Output | Reasoning | Cache read | Span (s) |
|---|---|---|---|---|---|---|
| coder | 189 | 228015 | 35635 | 21181 | 3594752 | 1643.5 |
| reviewer | 41 | 111676 | 6919 | 10257 | 314880 | 193.2 |
| director | 3 | 23432 | 1364 | 2105 | 14720 | 20.7 |

## Per task

| Task | Status | Rounds | Brief (s) | Gate (s) | Coder req | Coder span (s) | Reviewer req | Reviewer span (s) |
|---|---|---|---|---|---|---|---|---|
| 1 | APPROVED | 0 | 0.0 | 248.6 | 14 | 167.9 | 4 | 30.0 |
| 2 | APPROVED | 0 | 0.0 | 232.8 | 18 | 175.1 | 5 | 26.3 |
| 3 | APPROVED | 0 | 1.0 | 45.3 | 20 | 147.7 | 2 | 7.1 |
| 4 | APPROVED | 0 | 0.0 | 165.8 | 26 | 246.2 | 5 | 22.5 |
| 5 | APPROVED | 0 | 0.0 | 172.1 | 18 | 247.7 | 6 | 31.5 |
| 6 | APPROVED | 0 | 0.0 | 94.8 | 19 | 123.2 | 2 | 8.1 |
| 7 | APPROVED | 0 | 0.0 | 128.3 | 13 | 110.8 | 4 | 15.9 |
| 8 | APPROVED | 0 | 0.0 | 70.6 | 21 | 159.5 | 5 | 17.0 |
| 9 | APPROVED | 0 | 0.0 | 105.9 | 19 | 133.5 | 2 | 11.2 |
| 10 | APPROVED | 0 | 0.0 | 98.3 | 21 | 132.0 | 6 | 23.6 |

