"""Shared path classifier for the two-model pipeline (no LLM).

`is_test_path` is the single definition of "looks like a test file". Two
callers must agree on it or the scope gate breaks in opposite directions:

- `brief-scaffold` rejects a test path inside `touches` (a test inside
  `touches` can never prove RED, because tests are defined as
  `changed - touches`).
- `keep-discard` exempts the operador's newly authored test files from the
  out-of-scope check, so an honest task (touches `src/a.dart`, operador also
  writes `test/a_test.dart`) is KEEP, not DISCARD.

Two copies of this predicate is exactly how the scope gate would start
discarding every task (finding H3), so both import this module.
"""


def is_test_path(path):
    return (
        path == "test" or path == "tests"
        or path.startswith("test/") or path.startswith("tests/")
        or "/test/" in path or "/tests/" in path
        or path.startswith("__tests__") or "/__tests__/" in path
        or path.endswith("_test.dart") or path.endswith("_test.go")
        or path.endswith("_test.py") or path.startswith("test_")
        or ".test." in path or ".spec." in path
    )
