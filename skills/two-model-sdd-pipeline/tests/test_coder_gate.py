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
        # run-gates stub: controllable exit via STUB_GATE_EXIT
        self.gate = write_stub(
            self.stub_dir, "run-gates",
            """
echo "gate args: $*" >> "${STUB_GATE_LOG:?}"
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
                                "summary": "round 1", "status": "FAIL", "round": "1/4"}) + "\n")
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
        self.assertIn("round 2 passed", ledger_text)
        # a commit was made by the generic engine path (base + green commit)
        log = subprocess.run(["git", "log", "--oneline"], cwd=str(self.repo),
                             capture_output=True, text=True).stdout
        self.assertEqual(log.count("\n"), 2, log)

    def test_gate_failure_with_budget_resumes_coder(self):
        self.brief()
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": "x", "type": "red_check", "task": "1", "summary": "RED"}) + "\n")
        gate_log = self._tmp / "gate.log"
        dispatch_log = self._tmp / "dispatch.log"
        self._stubs(gate_log, dispatch_log)
        r = run_script(
            "coder-gate", [str(self.ws), "1"],
            cwd=str(self.repo),
            env_extra=self._env(STUB_GATE_EXIT="1"),
        )
        self.assertIn(r.returncode, (0, 1), r.stdout + r.stderr)
        fix_prompts = list(self.ws.glob("task-1-fix-round-*.md"))
        self.assertGreaterEqual(len(fix_prompts), 1, "fix prompt not built")
        dcalls = dispatch_log.read_text(encoding="utf-8") if dispatch_log.exists() else ""
        self.assertIn("two-model-coder", dcalls)

    def test_test_defect_short_circuits_to_escalated(self):
        self.brief()
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": "x", "type": "red_check", "task": "1", "summary": "RED"}) + "\n")
        (self.ws / "task-1-coder.log").write_text("TEST_DEFECT: the test is wrong\n", encoding="utf-8")
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


class TestGenericRedGate(CoderGateTestBase):
    def test_materializes_and_verifies_red_with_explicit_test_cmd(self):
        src = self._tmp / "test.py"
        src.write_text("assert False\n", encoding="utf-8")
        brief = self.ws / "task-1-brief.md"
        brief.write_text(
            "RED-TESTS:\n"
            f"{src} -> {self._tmp}/real_test.py\n"
            "\n"
            "EXPECTED-RED:\n"
            "assert False\n",
            encoding="utf-8",
        )
        # A stub test runner: report the expected failure text + exit 1.
        test_runner = write_stub(
            self.stub_dir, "runner",
            'echo "assert False" >&2\nexit 1\n',
        )
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
            "red-gate", [str(self.ws), "1", test_runner],
            cwd=str(self.repo),
            env_extra={
                "DISPATCH_BIN": dispatch_stub,
                "CODER_GATE": coder_gate_stub,
                "STUB_DISPATCH_LOG": str(dispatch_log),
                "RTK_ENABLED": "0",
            },
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self._tmp / "real_test.py").exists())
        self.assertIn("two-model-coder", dispatch_log.read_text(encoding="utf-8"))
        self.assertIn("coder-gate ran", r.stderr)

    def test_missing_test_cmd_and_no_ledger_is_usage(self):
        brief = self.ws / "task-1-brief.md"
        brief.write_text("RED-TESTS:\nnone -> none\n\nEXPECTED-RED:\nx\n", encoding="utf-8")
        # delete the ledger so no gate entry exists
        self.ledger_path.unlink()
        r = run_script("red-gate", [str(self.ws), "1"], cwd=str(self.repo), env_extra={})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()