# Benchmark report — par2-final

| Metric | Value |
|---|---|
| Total wall-clock (s) | 1740.2 |
| LLM requests | 232 |
| Cache-hit % | 92.0 |
| Uncached tokens (in+out+reasoning) | 411332 |
| Cache read tokens | 3845248 |
| Cache write tokens | 0 |
| Cost | 0.108860 |

## Per role

| Role | Requests | Input | Output | Reasoning | Cache read | Span (s) |
|---|---|---|---|---|---|---|
| coder | 181 | 189960 | 35056 | 18858 | 3398656 | 1533.0 |
| reviewer | 47 | 117602 | 8121 | 13761 | 406528 | 237.3 |
| director | 4 | 24605 | 1443 | 1926 | 40064 | 28.0 |

## Per task

| Task | Status | Rounds | Brief (s) | Gate (s) | Coder req | Coder span (s) | Reviewer req | Reviewer span (s) |
|---|---|---|---|---|---|---|---|---|
| 1 | APPROVED | 0 | 0.0 | 82.3 | 16 | 427.8 | 2 | 13.0 |
| 2 | APPROVED | 0 | 0.0 | 305.3 | 32 | 205.4 | 5 | 20.7 |
| 3 | APPROVED | 0 | 0.0 | 182.7 | 22 | 146.7 | 6 | 25.7 |
| 4 | APPROVED | 0 | 1.0 | 99.9 | 15 | 88.1 | 10 | 50.2 |
| 5 | APPROVED | 0 | 0.0 | 66.3 | 15 | 94.1 | 2 | 19.0 |
| 6 | APPROVED | 0 | 1.0 | 75.4 | 15 | 87.6 | 5 | 21.4 |
| 7 | APPROVED | 0 | 0.0 | 83.3 | 17 | 108.6 | 8 | 29.7 |
| 8 | APPROVED | 0 | 0.0 | 103.8 | 14 | 89.9 | 2 | 9.8 |
| 9 | APPROVED | 0 | 0.0 | 95.6 | 17 | 146.3 | 2 | 16.1 |
| 10 | APPROVED | 0 | 1.0 | 105.2 | 18 | 138.3 | 5 | 31.6 |

