# Benchmark report — serial-olddef

| Metric | Value |
|---|---|
| Total wall-clock (s) | 1998.6 |
| LLM requests | 217 |
| Cache-hit % | 90.5 |
| Uncached tokens (in+out+reasoning) | 471144 |
| Cache read tokens | 3805056 |
| Cache write tokens | 0 |
| Cost | 0.114963 |

## Per role

| Role | Requests | Input | Output | Reasoning | Cache read | Span (s) |
|---|---|---|---|---|---|---|
| coder | 166 | 250382 | 30616 | 19387 | 3382400 | 1080.8 |
| reviewer | 48 | 126012 | 8968 | 12159 | 407680 | 266.1 |
| director | 3 | 21691 | 1080 | 849 | 14976 | 15.8 |

## Per task

| Task | Status | Rounds | Brief (s) | Gate (s) | Coder req | Coder span (s) | Reviewer req | Reviewer span (s) |
|---|---|---|---|---|---|---|---|---|
| 1 | APPROVED | 0 | 5.0 | 21.0 | 28 | 228.4 | 7 | 38.0 |
| 2 | APPROVED | 0 | 3.0 | 13.3 | 13 | 87.4 | 10 | 55.6 |
| 3 | APPROVED | 0 | 4.0 | 13.1 | 17 | 127.4 | 6 | 43.2 |
| 4 | APPROVED | 0 | 3.0 | 21.2 | 15 | 86.2 | 5 | 24.1 |
| 5 | APPROVED | 0 | 5.0 | 21.2 | 17 | 98.4 | 3 | 15.2 |
| 6 | APPROVED | 0 | 3.0 | 13.4 | 13 | 98.4 | 2 | 12.3 |
| 7 | APPROVED | 0 | 5.0 | 20.5 | 16 | 93.6 | 4 | 18.3 |
| 8 | APPROVED | 0 | 4.0 | 22.0 | 15 | 86.0 | 7 | 36.8 |
| 9 | APPROVED | 0 | 5.0 | 23.9 | 14 | 78.5 | 2 | 9.1 |
| 10 | APPROVED | 0 | 3.0 | 22.3 | 18 | 96.6 | 2 | 13.5 |

