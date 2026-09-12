"""Black-box tests for scripts/red-form-check.

The script classifies the Agente operador's saved machine-readable RED
evidence (<ws>/task-N-red.txt) per language. Expectations are hand-derived
runner fixtures, not computed by the code under test. The script is run as a
real process and only its exit code is asserted (0 = valid red, 1 = invalid
red / missing evidence, 2 = unsupported language / bad usage).
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"

# --- flutter test --machine fixtures (JSONL) ---

FLUTTER_ASSERTION_FAILURE = "\n".join([
    '{"protocolVersion":"0.1.1","runnerVersion":"1.24.0","pid":1,'
    '"type":"start","time":0}',
    '{"test":{"id":1,"name":"loading /repo/test/foo_test.dart",'
    '"url":"file:///repo/test/foo_test.dart","line":0,"column":0},'
    '"type":"testStart","time":1}',
    '{"test":{"id":2,"name":"foo adds",'
    '"url":"file:///repo/test/foo_test.dart","line":5,"column":3},'
    '"type":"testStart","time":2}',
    '{"testID":2,"result":"failure","skipped":false,"hidden":false,'
    '"type":"testDone","time":9}',
    '{"error":"Expected: <4>\\n  Actual: <5>","stackTrace":"...",'
    '"isFailure":true,"type":"error","time":10}',
    '{"type":"done","success":false,"time":11}',
]) + "\n"

FLUTTER_RUNTIME_ERROR = "\n".join([
    '{"protocolVersion":"0.1.1","runnerVersion":"1.24.0","pid":1,'
    '"type":"start","time":0}',
    '{"test":{"id":1,"name":"foo throws",'
    '"url":"file:///repo/test/foo_test.dart","line":5,"column":3},'
    '"type":"testStart","time":1}',
    '{"testID":1,"result":"error","skipped":false,"hidden":false,'
    '"type":"testDone","time":9}',
    '{"error":"StateError: bad state","stackTrace":"...",'
    '"isFailure":false,"type":"error","time":10}',
    '{"type":"done","success":false,"time":11}',
]) + "\n"

FLUTTER_COMPILE_ERROR = "\n".join([
    '{"protocolVersion":"0.1.1","runnerVersion":"1.24.0","pid":1,'
    '"type":"start","time":0}',
    '{"error":"Failed to load /repo/test/foo_test.dart: '
    'Compilation failed","stackTrace":"","isFailure":true,'
    '"type":"error","time":5}',
    '{"type":"done","success":false,"time":6}',
]) + "\n"

# --- pytest --json-report fixtures (single JSON object) ---

PYTHON_ASSERTION_FAILURE = json.dumps({
    "created": 1.0,
    "duration": 0.01,
    "exitcode": 1,
    "summary": {"passed": 0, "failed": 1, "total": 1, "collected": 1},
    "collectors": [],
    "tests": [{
        "nodeid": "test_foo.py::test_add",
        "lineno": 3,
        "outcome": "failed",
        "setup": {"duration": 0.0, "outcome": "passed"},
        "call": {
            "duration": 0.0,
            "outcome": "failed",
            "crash": {"path": "test_foo.py", "lineno": 5,
                      "message": "assert 2 + 2 == 5"},
            "traceback": [],
        },
        "teardown": {"duration": 0.0, "outcome": "passed"},
    }],
}) + "\n"

PYTHON_COLLECTION_ERROR = json.dumps({
    "created": 1.0,
    "duration": 0.01,
    "exitcode": 2,
    "summary": {"error": 1, "total": 1, "collected": 0},
    "collectors": [{
        "nodeid": "test_foo.py",
        "outcome": "failed",
        "result": [{"type": "error",
                    "message": "SyntaxError: invalid syntax"}],
    }],
    "tests": [],
}) + "\n"

# --- go test -json fixtures (JSONL) ---

GO_TEST_FAILURE = "\n".join([
    '{"Time":"2026-01-01T00:00:00Z","Action":"run",'
    '"Package":"example.com/foo","Test":"TestAdd"}',
    '{"Time":"2026-01-01T00:00:00Z","Action":"output",'
    '"Package":"example.com/foo","Test":"TestAdd",'
    '"Output":"=== RUN   TestAdd\\n"}',
    '{"Time":"2026-01-01T00:00:00Z","Action":"output",'
    '"Package":"example.com/foo","Test":"TestAdd",'
    '"Output":"    add_test.go:10: got 5, want 4\\n"}',
    '{"Time":"2026-01-01T00:00:00Z","Action":"output",'
    '"Package":"example.com/foo","Test":"TestAdd",'
    '"Output":"--- FAIL: TestAdd (0.00s)\\n"}',
    '{"Time":"2026-01-01T00:00:00Z","Action":"fail",'
    '"Package":"example.com/foo","Test":"TestAdd","Elapsed":0.0}',
    '{"Time":"2026-01-01T00:00:00Z","Action":"fail",'
    '"Package":"example.com/foo","Elapsed":0.0}',
]) + "\n"

GO_BUILD_FAILURE = "\n".join([
    '{"Time":"2026-01-01T00:00:00Z","Action":"output",'
    '"Package":"example.com/foo","Output":"# example.com/foo\\n"}',
    '{"Time":"2026-01-01T00:00:00Z","Action":"output",'
    '"Package":"example.com/foo",'
    '"Output":"./add.go:5:2: undefined: bar\\n"}',
    '{"Time":"2026-01-01T00:00:00Z","Action":"build-fail",'
    '"Package":"example.com/foo","Elapsed":0.1}',
    '{"Time":"2026-01-01T00:00:00Z","Action":"fail",'
    '"Package":"example.com/foo","Elapsed":0.1}',
]) + "\n"


class RedFormCheckBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="red-form-check-tests-")
        self.ws = pathlib.Path(self._tmp) / "ws"
        self.ws.mkdir()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def write_evidence(self, text, task="1"):
        (self.ws / ("task-%s-red.txt" % task)).write_text(
            text, encoding="utf-8",
        )

    def run_it(self, task="1", lang="flutter"):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "red-form-check"),
             str(self.ws), task, lang],
            capture_output=True, text=True, env=dict(os.environ),
        )


class TestRedFormCheck(RedFormCheckBase):
    def test_flutter_assertion_failure_is_valid(self):
        self.write_evidence(FLUTTER_ASSERTION_FAILURE)
        r = self.run_it(lang="flutter")
        self.assertEqual(
            r.returncode, 0,
            "red-form-check must accept an executed assertion failure: "
            + r.stdout + r.stderr,
        )

    def test_flutter_runtime_error_is_valid(self):
        self.write_evidence(FLUTTER_RUNTIME_ERROR)
        r = self.run_it(lang="flutter")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_dart_alias_accepts_assertion_failure(self):
        self.write_evidence(FLUTTER_ASSERTION_FAILURE)
        r = self.run_it(lang="dart")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_flutter_compile_error_is_invalid(self):
        self.write_evidence(FLUTTER_COMPILE_ERROR)
        r = self.run_it(lang="flutter")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_python_assertion_failure_is_valid(self):
        self.write_evidence(PYTHON_ASSERTION_FAILURE)
        r = self.run_it(lang="python")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_python_collection_error_is_invalid(self):
        self.write_evidence(PYTHON_COLLECTION_ERROR)
        r = self.run_it(lang="python")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_go_test_failure_is_valid(self):
        self.write_evidence(GO_TEST_FAILURE)
        r = self.run_it(lang="go")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_go_build_failure_is_invalid(self):
        self.write_evidence(GO_BUILD_FAILURE)
        r = self.run_it(lang="go")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_missing_evidence_is_invalid(self):
        r = self.run_it(lang="flutter")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_unsupported_language_is_usage(self):
        self.write_evidence(FLUTTER_ASSERTION_FAILURE)
        r = self.run_it(lang="ruby")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_bad_usage_is_usage(self):
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "red-form-check")],
            capture_output=True, text=True, env=dict(os.environ),
        )
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
