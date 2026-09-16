# Benchmark report ù serial

| Metric | Value |
|---|---|
| Total wall-clock (s) | 1394.5 |
| LLM requests | 188 |
| Cache-hit % | 89.5 |
| Uncached tokens (in+out+reasoning) | 442911 |
| Cache read tokens | 3186944 |
| Cache write tokens | 0 |
| Cost | 0.107342 |

## Per role

| Role | Requests | Input | Output | Reasoning | Cache read | Span (s) |
|---|---|---|---|---|---|---|
| coder | 142 | 213537 | 28478 | 18107 | 2830848 | 675.3 |
| reviewer | 43 | 137818 | 8195 | 12360 | 341120 | 217.3 |
| director | 3 | 21902 | 1436 | 1078 | 14976 | 17.1 |

## Per task

| Task | Status | Rounds | Brief (s) | Gate (s) | Coder req | Coder span (s) | Reviewer req | Reviewer span (s) |
|---|---|---|---|---|---|---|---|---|
| 1 | APPROVED | 0 | 3.0 | 12.3 | 13 | 51.8 | 6 | 26.2 |
| 2 | APPROVED | 0 | 3.0 | 11.2 | 17 | 90.6 | 5 | 19.8 |
| 3 | APPROVED | 0 | 3.0 | 9.0 | 12 | 62.8 | 2 | 7.7 |
| 4 | APPROVED | 0 | 2.0 | 9.4 | 16 | 112.3 | 2 | 12.3 |
| 5 | APPROVED | 0 | 2.0 | 9.3 | 14 | 62.5 | 7 | 62.2 |
| 6 | APPROVED | 0 | 3.0 | 8.9 | 16 | 56.9 | 6 | 30.0 |
| 7 | APPROVED | 0 | 2.0 | 9.5 | 15 | 70.2 | 4 | 14.7 |
| 8 | APPROVED | 0 | 2.0 | 9.4 | 11 | 47.1 | 7 | 21.8 |
| 9 | APPROVED | 0 | 2.0 | 10.2 | 14 | 60.1 | 2 | 7.3 |
| 10 | APPROVED | 0 | 2.0 | 10.1 | 14 | 60.9 | 2 | 15.4 |

