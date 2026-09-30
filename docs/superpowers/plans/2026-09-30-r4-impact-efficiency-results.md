# R4 impact efficiency results

Date: 2026-09-30

## Workload measurements

Measurements used disposable, synthetic Python and Flutter fixtures with the installed Graphify 0.9.50 and local toolchains. These are useful for checking that extraction and affected-test execution work end to end, but are too small to represent a production repository or to establish net savings.

| Workload | Graph extraction | Full suite | Selected suite | Tests |
| --- | ---: | ---: | ---: | ---: |
| Python / `unittest` | 1,357 ms | 159 ms | 107 ms | 3 total, 1 selected |
| Flutter | 1,471 ms | 4,914 ms warm | 4,473 ms | 2 total, 1 selected |

The Flutter cold full-suite run took 16,659 ms; a separate earlier run included cold dependency/compiler setup and took 63,711 ms. Those cold-start values are environment/setup dominated. The table uses a warmed full-suite measurement for comparison.

## Cache and gate evidence

- A cold eligible gate builds evidence for the distinct base and candidate identities (two cache misses/builds).
- An unchanged warm gate performs zero extractions (two cache hits).
- With a cached base and changed candidate identity, only the candidate is rebuilt (one miss/build).
- Corrupt or incomplete entries rebuild; cache-write failures preserve valid fresh evidence.
- Post-run identity verification is covered by tests asserting no graph construction or reselection. Its elapsed time was not separately instrumented.
- Final shared suite: 1,101 tests ran. The only failure was a duplicate documentation assertion for the obsolete phrase `without graph context`; the current lifecycle test already verifies the revised wording. After removing that stale duplicate, all 7 documentation tests passed, as did the 6 gate-execution tests. Two tests were skipped because the Windows environment's `zip` CLI does not support the stdin-list option those tests require.
- Flutter suite: 150 tests passed.
- Final review findings were fixed: post-command manifest tampering is rejected against a pre-command seal, test/worker processes cannot access the supervisor cache path, and prior Green evidence cannot skip tests.

## Conclusion and limits

These measurements do not support a claim of net speedup. For tiny fixtures, cold extraction costs more than the saved selected-versus-full test time. The code-path evidence shows warm-cache reuse can avoid extraction and verification does not extract again, but a meaningful net-gate comparison needs representative repository workloads and should account for cache hit rate, test duration, and setup state. Unsupported or uncertain impact evidence continues to fall back to full suites.
