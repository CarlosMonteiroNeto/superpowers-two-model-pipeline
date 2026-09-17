# Benchmark report — par2-staleflex

| Metric | Value |
|---|---|
| Total wall-clock (s) | 1853.3 |
| LLM requests | 235 |
| Cache-hit % | 90.7 |
| Uncached tokens (in+out+reasoning) | 441441 |
| Cache read tokens | 3570816 |
| Cache write tokens | 0 |
| Cost | 0.110746 |

## Per role

| Role | Requests | Input | Output | Reasoning | Cache read | Span (s) |
|---|---|---|---|---|---|---|
| coder | 186 | 222949 | 36289 | 15283 | 3160448 | 1718.1 |
| reviewer | 45 | 118771 | 7812 | 13726 | 378368 | 213.4 |
| director | 4 | 24572 | 1294 | 745 | 32000 | 17.1 |

## Per task

| Task | Status | Rounds | Brief (s) | Gate (s) | Coder req | Coder span (s) | Reviewer req | Reviewer span (s) |
|---|---|---|---|---|---|---|---|---|
| 1 | APPROVED | 0 | 0.0 | 273.0 | 16 | 96.2 | 2 | 9.4 |
| 2 | APPROVED | 0 | 0.0 | 122.2 | 20 | 249.2 | 9 | 40.0 |
| 3 | APPROVED | 0 | 0.0 | 165.3 | 19 | 112.9 | 3 | 14.1 |
| 4 | APPROVED | 0 | 0.0 | 88.1 | 20 | 191.0 | 7 | 37.7 |
| 5 | APPROVED | 0 | 0.0 | 200.2 | 22 | 176.8 | 2 | 12.6 |
| 6 | APPROVED | 0 | 0.0 | 86.2 | 23 | 291.9 | 5 | 17.4 |
| 7 | APPROVED | 0 | 0.0 | 77.7 | 17 | 87.9 | 7 | 26.3 |
| 8 | APPROVED | 0 | 0.0 | 66.0 | 17 | 100.8 | 2 | 5.9 |
| 9 | APPROVED | 0 | 0.0 | 57.9 | 16 | 329.3 | 3 | 15.5 |
| 10 | APPROVED | 0 | 0.0 | 311.4 | 16 | 82.0 | 5 | 34.6 |

