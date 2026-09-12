import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"

if os.name == "nt":
    git_bash = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
    BASH = str(git_bash) if git_bash.exists() else "bash"
else:
    BASH = "bash"

# --- go test -json fixtures (the gate entry in setUp resolves lang=go) ---
# Hand-derived runner output, not computed by the code under test.

# A named test ran and failed: a valid red for scripts/red-form-check.
GO_TEST_FAILURE = "\n".join([
    '{"Time":"2026-01-01T00:00:00Z","Action":"run",'
    '"Package":"example.com/foo","Test":"TestAdd"}',
    '{"Time":"2026-01-01T00:00:00Z","Action":"output",'
    '"Package":"example.com/foo","Test":"TestAdd",'
    '"Output":"=== RUN   TestAdd\\n"}',
    '{"Time":"2026-01-01T00:00:00Z","Action":"output",'
    '"Package":"example.com/foo","Test":"TestAdd",'
    '"Output":"    add_test.go:10: got 5, want 4\\n"}',
    '{"Time":"2026-01-01T00:00:00Z","Action":"fail",'
    '"Package":"example.com/foo","Test":"TestAdd","Elapsed":0.0}',
]) + "\n"

# A build failure with no executed test: form-invalid (compile/load red).
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


def write_stub(directory, name, body):
    p = pathlib.Path(directory) / name
    p.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    if os.name == "nt":
        subprocess.run([BASH, "-c", "chmod +x '{}'".format(p)], capture_output=True)
    else:
        p.chmod(0o755)
    return str(p)


def run_script(script, args, cwd, env_extra):
    env = dict(os.environ)
    env.update(env_extra)
    return subprocess.run(
        [BASH, str(SCRIPTS / script), *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
    )


class CoderGateTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="coder-gate-tests-"))
        self.stub_dir = self._tmp / "stubs"
        self.stub_dir.mkdir()
        self.ws = self._tmp / "ws"
        self.ws.mkdir()
        # a gate ledger entry with lang/test_cmd/analyze_cmd (resolve-toolchain shape)
        (self.ws / "ledger.jsonl").write_text(
            json.dumps({
                "ts": "2026-09-05T00:00:00Z",
                "type": "gate",
                "task": "-",
                "summary": "auto-detected: go (go.mod)",
                "test_cmd": "go test ./...",
                "analyze_cmd": "go vet ./...",
                "detected": "auto",
                "lang": "go",
            }) + "\n",
            encoding="utf-8",
        )
        self.ledger_path = self.ws / "ledger.jsonl"
        # coder-gate computes base=$(git rev-parse HEAD) from cwd - set up a git repo
        self.repo = self._tmp / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(self.repo), check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(self.repo), check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(self.repo), check=True)
        (self.repo / "file.txt").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(self.repo), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=str(self.repo), check=True)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def ledger_types(self):
        return [json.loads(l)["type"] for l in
                (self.ledger_path.read_text(encoding="utf-8")).splitlines() if l.strip()]

    def brief(self, body="# Task 1\n\nDo the thing.\n"):
        p = self.ws / "task-1-brief.md"
        p.write_text(body, encoding="utf-8")
        return p


class TestResolveToolchain(CoderGateTestBase):
    def test_resolves_go_marker_and_ledgers_gate(self):
        root = self._tmp / "proj"
        root.mkdir()
        (root / "go.mod").write_text("module test\n", encoding="utf-8")
        r = run_script("resolve-toolchain", [str(self.ws), str(root)], cwd=self._tmp, env_extra={})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("go test ./...", r.stdout)
        entries = [json.loads(l) for l in
                   self.ledger_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        last = entries[-1]
        self.assertEqual(last["type"], "gate")
        self.assertEqual(last["lang"], "go")
        self.assertEqual(last["test_cmd"], "go test ./...")

    def test_no_marker_exits_2(self):
        root = self._tmp / "emptyproj"
        root.mkdir()
        r = run_script("resolve-toolchain", [str(self.ws), str(root)], cwd=self._tmp, env_extra={})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_ambiguous_markers_exit_1(self):
        root = self._tmp / "ambigproj"
        root.mkdir()
        (root / "go.mod").write_text("module test\n", encoding="utf-8")
        (root / "package.json").write_text("{}\n", encoding="utf-8")
        r = run_script("resolve-toolchain", [str(self.ws), str(root)], cwd=self._tmp, env_extra={})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)


class TestCoderGate(CoderGateTestBase):
    def _stubs(self, gate_log, dispatch_log):
        # run-gates stub: controllable exit via STUB_GATE_EXIT - or, when
        # STUB_COUNT_FILE is set, fail until the Nth invocation
        # (STUB_GATE_PASS_AFTER) then pass, so unbounded-loop tests
        # terminate deterministically.
        self.gate = write_stub(
            self.stub_dir, "run-gates",
            """
echo "gate args: $*" >> "${STUB_GATE_LOG:?}"
if [ -n "${STUB_COUNT_FILE:-}" ]; then
  n=$(cat "$STUB_COUNT_FILE" 2>/dev/null || echo 0)
  n=$((n + 1))
  echo "$n" > "$STUB_COUNT_FILE"
  if [ "$n" -lt "${STUB_GATE_PASS_AFTER:-1}" ]; then exit 1; fi
  exit 0
fi
exit "${STUB_GATE_EXIT:-0}"
""",
        )
        self.dispatch = write_stub(
            self.stub_dir, "dispatch",
            """
echo "$*" >> "${STUB_DISPATCH_LOG:?}"
exit "${STUB_DISPATCH_EXIT:-0}"
""",
        )
        self.gate_log = gate_log
        self.dispatch_log = dispatch_log

    def _env(self, **extra):
        env = {
            "STUB_GATE_LOG": str(self.gate_log),
            "STUB_DISPATCH_LOG": str(self.dispatch_log),
            "RUN_GATES_BIN": self.gate,
            "DISPATCH_BIN": self.dispatch,
            "GIT_BIN": "git",
        }
        env.update(extra)
        return env

    def test_gate_green_commits_and_dispatches(self):
        self.brief()
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": "x", "type": "red_check", "task": "1", "summary": "RED"}) + "\n")
            f.write(json.dumps({"ts": "x", "type": "coder_round", "task": "1",
                                "summary": "attempt failed", "status": "FAIL"}) + "\n")
        (self.ws / "task-1-red.txt").write_text(GO_TEST_FAILURE, encoding="utf-8")
        gate_log = self._tmp / "gate.log"
        dispatch_log = self._tmp / "dispatch.log"
        self._stubs(gate_log, dispatch_log)
        # simulate the Coder's work: a change in the repo working tree
        (self.repo / "file.txt").write_text("y\n", encoding="utf-8")
        r = run_script(
            "coder-gate", [str(self.ws), "1"],
            cwd=str(self.repo),
            env_extra=self._env(STUB_GATE_EXIT="0"),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ledger_text = self.ledger_path.read_text(encoding="utf-8")
        self.assertIn("Coder passed the gate", ledger_text)
        # a commit was made by the generic engine path (base + green commit)
        log = subprocess.run(["git", "log", "--oneline"], cwd=str(self.repo),
                             capture_output=True, text=True).stdout
        self.assertEqual(log.count("\n"), 2, log)

    def test_gate_failure_retries_until_green(self):
        """The Coder loop is unbounded: repeated gate failures keep
        redispatching the Coder with fresh fix prompts (no hand-back to the
        main agent) until the gate passes - then commit + Reviewer dispatch
        and exit 0."""
        self.brief()
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": "x", "type": "red_check", "task": "1", "summary": "RED"}) + "\n")
        (self.ws / "task-1-red.txt").write_text(GO_TEST_FAILURE, encoding="utf-8")
        gate_log = self._tmp / "gate.log"
        dispatch_log = self._tmp / "dispatch.log"
        self._stubs(gate_log, dispatch_log)
        count_file = self._tmp / "gate.count"
        count_file.write_text("0", encoding="utf-8")
        # simulate the Coder's work: a change in the repo working tree
        (self.repo / "file.txt").write_text("y\n", encoding="utf-8")
        r = run_script(
            "coder-gate", [str(self.ws), "1"],
            cwd=str(self.repo),
            env_extra=self._env(STUB_COUNT_FILE=str(count_file), STUB_GATE_PASS_AFTER="3"),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # two failures rebuilt the (fixed-path) fix prompt before green
        self.assertTrue((self.ws / "task-1-fix.md").exists(), "fix prompt not built")
        dcalls = dispatch_log.read_text(encoding="utf-8") if dispatch_log.exists() else ""
        self.assertGreaterEqual(dcalls.count("two-model-coder"), 2, dcalls)
        self.assertIn("two-model-reviewer", dcalls)
        ledger_text = self.ledger_path.read_text(encoding="utf-8")
        self.assertIn("Coder passed the gate", ledger_text)

    def test_test_defect_short_circuits_to_escalated(self):
        self.brief()
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": "x", "type": "red_check", "task": "1", "summary": "RED"}) + "\n")
        # round-1 log whose final text event carries the Status: TEST_DEFECT contract
        (self.ws / "task-1-coder.log").write_text(
            '{"type":"text","part":{"type":"text","text":"This test contradicts. Status: TEST_DEFECT"}}\n',
            encoding="utf-8",
        )
        gate_log = self._tmp / "gate.log"
        dispatch_log = self._tmp / "dispatch.log"
        self._stubs(gate_log, dispatch_log)
        r = run_script(
            "coder-gate", [str(self.ws), "1"],
            cwd=str(self.repo),
            env_extra=self._env(),
        )
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        ledger_text = self.ledger_path.read_text(encoding="utf-8")
        self.assertIn("escalated", ledger_text)

    def test_fix_prompt_text_does_not_false_escalate(self):
        """Regression for the whole-log-grep false-positive: the fix prompt
        coder-gate itself writes into the round-N log contains the word
        TEST_DEFECT as instruction text. A round-2 log with that text but a
        final Status: DONE must NOT escalate - the loop continues until the
        gate passes (exit 0, no `escalated` entry)."""
        self.brief()
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": "x", "type": "red_check", "task": "1", "summary": "RED"}) + "\n")
            f.write(json.dumps({"ts": "x", "type": "coder_round", "task": "1",
                                "summary": "attempt failed", "status": "FAIL"}) + "\n")
        (self.ws / "task-1-red.txt").write_text(GO_TEST_FAILURE, encoding="utf-8")
        # latest coder log: fix-prompt-style text + final Status: DONE
        # (dispatch overwrites the fixed log path every retry, so this file
        # is always the latest round)
        (self.ws / "task-1-coder.log").write_text(
            '{"type":"text","part":{"type":"text","text":"Report TEST_DEFECT if the test is wrong."}}\n'
            '{"type":"text","part":{"type":"text","text":"Fixed. Status: DONE"}}\n',
            encoding="utf-8",
        )
        gate_log = self._tmp / "gate.log"
        dispatch_log = self._tmp / "dispatch.log"
        self._stubs(gate_log, dispatch_log)
        count_file = self._tmp / "gate.count"
        count_file.write_text("0", encoding="utf-8")
        r = run_script(
            "coder-gate", [str(self.ws), "1"],
            cwd=str(self.repo),
            env_extra=self._env(STUB_COUNT_FILE=str(count_file), STUB_GATE_PASS_AFTER="2"),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ledger_text = self.ledger_path.read_text(encoding="utf-8")
        self.assertNotIn("escalated", ledger_text)


class TestRedFormEvidence(CoderGateTestBase):
    """Coder-owned RED, form-checked: the operador authors its RED tests, RUNS
    them itself, and saves the runner's machine-readable output to
    task-N-red.txt. coder-gate only approves green after scripts/red-form-check
    finds a valid red (suite loaded, at least one test executed, failed as an
    assertion/runtime error). There is no expected_red substring anymore — the
    plan carries none, and legacy plan metadata is ignored."""

    def _plan(self, task):
        (self.ws / "plan.json").write_text(
            json.dumps({"feature": "t", "tasks": [task]}), encoding="utf-8")

    def _stubs(self, gate_log, dispatch_log, dispatch_writes_valid_red=False):
        self.gate = write_stub(
            self.stub_dir, "run-gates",
            """
echo "gate args: $*" >> "${STUB_GATE_LOG:?}"
exit "${STUB_GATE_EXIT:-0}"
""",
        )
        evidence_write = ""
        if dispatch_writes_valid_red:
            # On a coder retry, drop the prepared machine-readable RED in
            # place so the next round passes the form check.
            evidence_write = (
                'case "$*" in\n'
                '  *two-model-coder*) cp "${STUB_RED_SRC:?}" '
                '"%s/task-1-red.txt" ;;\n'
                'esac\n' % self.ws.as_posix()
            )
        self.dispatch = write_stub(
            self.stub_dir, "dispatch",
            """
echo "$*" >> "${STUB_DISPATCH_LOG:?}"
"""
            + evidence_write
            + """
exit "${STUB_DISPATCH_EXIT:-0}"
""",
        )
        self.gate_log = gate_log
        self.dispatch_log = dispatch_log

    def _env(self, **extra):
        env = {
            "STUB_GATE_LOG": str(self.gate_log),
            "STUB_DISPATCH_LOG": str(self.dispatch_log),
            "RUN_GATES_BIN": self.gate,
            "DISPATCH_BIN": self.dispatch,
            "GIT_BIN": "git",
        }
        env.update(extra)
        return env

    def _run(self, **extra):
        return run_script(
            "coder-gate", [str(self.ws), "1"],
            cwd=str(self.repo),
            env_extra=self._env(**extra),
        )

    def test_form_valid_red_without_expected_red_is_accepted(self):
        """A form-valid RED is accepted even when the plan carries no
        expected_red at all."""
        self.brief()
        self._plan({"id": 1, "title": "t", "touches": ["lib/app.go"],
                    "acceptance": ["thing works"]})
        (self.ws / "task-1-red.txt").write_text(
            GO_TEST_FAILURE, encoding="utf-8")
        gate_log = self._tmp / "gate.log"
        dispatch_log = self._tmp / "dispatch.log"
        self._stubs(gate_log, dispatch_log)
        (self.repo / "file.txt").write_text("y\n", encoding="utf-8")
        r = self._run(STUB_GATE_EXIT="0")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.ws / "task-1-fix.md").exists(),
                         "coder-gate must accept a form-only RED")
        ledger_text = self.ledger_path.read_text(encoding="utf-8")
        self.assertIn("Coder passed the gate", ledger_text)
        log = subprocess.run(["git", "log", "--oneline"], cwd=str(self.repo),
                             capture_output=True, text=True).stdout
        self.assertEqual(log.count("\n"), 2, log)
        self.assertIn("two-model-reviewer",
                      dispatch_log.read_text(encoding="utf-8"))

    def test_form_valid_red_is_not_grepped_against_expected_red(self):
        """A plan that still carries a legacy expected_red is ignored: form
        validity alone decides, so a form-valid RED whose text does not contain
        expected_red is accepted without a fix round."""
        self.brief()
        self._plan({"id": 1, "title": "t", "touches": ["lib/app.go"],
                    "expected_red": "missing feature"})
        (self.ws / "task-1-red.txt").write_text(
            GO_TEST_FAILURE, encoding="utf-8")
        # Legacy retry evidence: lets the pre-change implementation (substring
        # grep) terminate so this test fails fast instead of looping.
        legacy = self._tmp / "legacy-red.txt"
        legacy.write_text("FAIL: missing feature\n", encoding="utf-8")
        gate_log = self._tmp / "gate.log"
        dispatch_log = self._tmp / "dispatch.log"
        self._stubs(gate_log, dispatch_log, dispatch_writes_valid_red=True)
        (self.repo / "file.txt").write_text("y\n", encoding="utf-8")
        r = self._run(STUB_GATE_EXIT="0", STUB_RED_SRC=legacy.as_posix())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(
            (self.ws / "task-1-fix.md").exists(),
            "coder-gate must accept a form-only RED: a form-valid RED is "
            "accepted even when it does not contain the plan's expected_red",
        )

    def test_form_invalid_red_fails_then_recovers(self):
        """A compile/load red (no executed test) is a FAIL round with a fix
        prompt — never a green, never a TEST_DEFECT. The coder saves a
        form-valid red on retry and the next round passes."""
        self.brief()
        self._plan({"id": 1, "title": "t", "touches": ["lib/app.go"],
                    "acceptance": ["thing works"]})
        (self.ws / "task-1-red.txt").write_text(
            GO_BUILD_FAILURE, encoding="utf-8")
        valid = self._tmp / "valid-red.txt"
        valid.write_text(GO_TEST_FAILURE, encoding="utf-8")
        gate_log = self._tmp / "gate.log"
        dispatch_log = self._tmp / "dispatch.log"
        self._stubs(gate_log, dispatch_log, dispatch_writes_valid_red=True)
        (self.repo / "file.txt").write_text("y\n", encoding="utf-8")
        r = self._run(STUB_GATE_EXIT="0", STUB_RED_SRC=valid.as_posix())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(
            (self.ws / "task-1-fix.md").exists(),
            "a form-invalid RED must fail the round with a fix prompt",
        )
        ledger_text = self.ledger_path.read_text(encoding="utf-8")
        self.assertIn("Coder failed the gate", ledger_text)
        self.assertIn("Coder passed the gate", ledger_text)
        self.assertNotIn("escalated", ledger_text)

    def test_missing_red_evidence_fails_then_recovers(self):
        """No saved RED evidence: the round fails with a dedicated fix prompt
        (never a green approval), the resumed coder saves machine-readable
        evidence, and the next round passes."""
        self.brief()
        self._plan({"id": 1, "title": "t", "touches": ["lib/app.go"],
                    "acceptance": ["thing works"]})
        valid = self._tmp / "valid-red.txt"
        valid.write_text(GO_TEST_FAILURE, encoding="utf-8")
        gate_log = self._tmp / "gate.log"
        dispatch_log = self._tmp / "dispatch.log"
        self._stubs(gate_log, dispatch_log, dispatch_writes_valid_red=True)
        (self.repo / "file.txt").write_text("y\n", encoding="utf-8")
        r = self._run(STUB_GATE_EXIT="0", STUB_RED_SRC=valid.as_posix())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(
            (self.ws / "task-1-fix.md").exists(),
            "missing RED evidence must fail the round with a fix prompt",
        )
        ledger_text = self.ledger_path.read_text(encoding="utf-8")
        self.assertIn("Coder failed the gate", ledger_text)
        self.assertIn("Coder passed the gate", ledger_text)


class TestGenericRedGate(CoderGateTestBase):
    def test_dispatches_coder_and_chains_coder_gate(self):
        """On a scaffolded brief, generic red-gate dispatches Agente
        operador and chains coder-gate — no materialization: the operador
        authors the RED tests."""
        (self.ws / "task-1-brief.md").write_text(
            "# Task 1 Brief (scaffolded)\n", encoding="utf-8")
        dispatch_stub = write_stub(
            self.stub_dir, "dispatch",
            'echo "$*" >> "${STUB_DISPATCH_LOG:?}"\nexit 0\n',
        )
        coder_gate_stub = write_stub(
            self.stub_dir, "coder-gate",
            'echo "coder-gate ran" >&2\nexit 0\n',
        )
        dispatch_log = self._tmp / "dispatch.log"
        r = run_script(
            "red-gate", [str(self.ws), "1"],
            cwd=str(self.repo),
            env_extra={
                "DISPATCH_BIN": dispatch_stub,
                "CODER_GATE": coder_gate_stub,
                "STUB_DISPATCH_LOG": str(dispatch_log),
                "RTK_ENABLED": "0",
            },
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("two-model-coder", dispatch_log.read_text(encoding="utf-8"))
        self.assertIn("coder-gate ran", r.stderr)
        self.assertIn(
            "red_check", self.ledger_path.read_text(encoding="utf-8"))

    def test_missing_test_cmd_and_no_ledger_is_usage(self):
        brief = self.ws / "task-1-brief.md"
        brief.write_text("RED-TESTS:\nnone -> none\n\nEXPECTED-RED:\nx\n", encoding="utf-8")
        # delete the ledger so no gate entry exists
        self.ledger_path.unlink()
        r = run_script("red-gate", [str(self.ws), "1"], cwd=str(self.repo), env_extra={})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()