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


class GateTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="pipeline-tests-")
        self.stub_dir = pathlib.Path(self._tmp) / "stubs"
        self.stub_dir.mkdir()
        self.flutter = write_stub(
            self.stub_dir,
            "flutter",
            """
cmd="$1"; shift
case "$cmd" in
  test) echo "stub: flutter test $*"; echo "${STUB_TEST_OUTPUT:-}"; exit "${STUB_TEST_EXIT:-0}" ;;
  analyze) echo "stub: flutter analyze"; exit "${STUB_ANALYZE_EXIT:-0}" ;;
  pub)
    sub="$1"; shift
    case "$sub" in
      add|get) echo "stub: flutter pub $sub $*"; exit "${STUB_PUB_EXIT:-0}" ;;
      upgrade) echo "stub: flutter pub upgrade --dry-run"; exit "${STUB_DRYRUN_EXIT:-0}" ;;
      *) exit "${STUB_PUB_EXIT:-0}" ;;
    esac
    ;;
esac
exit 0
""",
        )
        self.dart = write_stub(
            self.stub_dir,
            "dart",
            """
echo "stub: dart $*"
exit "${STUB_FORMAT_EXIT:-0}"
""",
        )
        # Dispatch stub: records argv to STUB_DISPATCH_LOG (defaults to
        # /dev/null so unrelated tests don't fail on an unset var); exits per
        # STUB_DISPATCH_EXIT (default 0). Used to verify red-gate/green-gate
        # chain the Coder/Reviewer dispatch on success.
        self.dispatch = write_stub(
            self.stub_dir,
            "dispatch",
            """
echo "$*" >> "${STUB_DISPATCH_LOG:-/dev/null}"
exit "${STUB_DISPATCH_EXIT:-0}"
""",
        )
        # coder-gate stub: red-gate now chains into coder-gate after dispatch.
        # The chain is stubbed out so red-gate tests assert RED verification +
        # dispatch without exercising the full retry loop (covered separately
        # in test_coder_gate.py).
        self.coder_gate = write_stub(
            self.stub_dir,
            "coder-gate",
            """
echo "coder-gate ran" >&2
exit "${STUB_CODER_GATE_EXIT:-0}"
""",
        )
        self.env = {
            "FLUTTER_BIN": self.flutter,
            "DART_BIN": self.dart,
            "GIT_BIN": shutil.which("git") or "git",
            "RTK_ENABLED": "0",
            "DISPATCH_BIN": self.dispatch,
            "CODER_GATE": self.coder_gate,
        }

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)


class TestGreenGate(GateTestBase):
    def _git_repo(self):
        repo = pathlib.Path(self._tmp) / "repo"
        repo.mkdir()
        subprocess.run(
            [self.env["GIT_BIN"], "init", "-q"],
            cwd=str(repo), capture_output=True, check=True,
        )
        subprocess.run(
            [self.env["GIT_BIN"], "config", "user.email", "test@example.com"],
            cwd=str(repo), capture_output=True, check=True,
        )
        subprocess.run(
            [self.env["GIT_BIN"], "config", "user.name", "Test"],
            cwd=str(repo), capture_output=True, check=True,
        )
        (repo / "lib").mkdir()
        (repo / "lib" / "app.dart").write_text("void main() {}\n", encoding="utf-8")
        (repo / "test").mkdir()
        (repo / "test" / "app_test.dart").write_text("void main() {}\n", encoding="utf-8")
        subprocess.run(
            [self.env["GIT_BIN"], "add", "-A"],
            cwd=str(repo), capture_output=True, check=True,
        )
        subprocess.run(
            [self.env["GIT_BIN"], "commit", "-q", "-m", "baseline"],
            cwd=str(repo), capture_output=True, check=True,
        )
        return repo

    def _log(self, repo):
        r = subprocess.run(
            [self.env["GIT_BIN"], "log", "--oneline"],
            cwd=str(repo), capture_output=True, text=True, check=True,
        )
        return r.stdout

    def test_green_runs_all_gates_and_commits(self):
        repo = self._git_repo()
        (repo / "lib" / "app.dart").write_text("void main() { print('done'); }\n", encoding="utf-8")
        r = run_script("green-gate", ["-m", "Task 1: done"], cwd=repo, env_extra=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Task 1: done", self._log(repo))

    def test_no_commit_flag_never_commits(self):
        repo = self._git_repo()
        before = self._log(repo)
        r = run_script("green-gate", ["--no-commit"], cwd=repo, env_extra=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self._log(repo), before)

    def test_test_failure_reports_and_does_not_commit(self):
        repo = self._git_repo()
        before = self._log(repo)
        r = run_script(
            "green-gate", ["-m", "should not commit"],
            cwd=repo,
            env_extra={**self.env, "STUB_TEST_EXIT": "1"},
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self._log(repo), before)
        self.assertTrue((repo / "green-gate-report.txt").exists())

    def test_analyze_failure_reports_and_does_not_commit(self):
        repo = self._git_repo()
        before = self._log(repo)
        r = run_script(
            "green-gate", ["-m", "should not commit"],
            cwd=repo,
            env_extra={**self.env, "STUB_ANALYZE_EXIT": "1"},
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self._log(repo), before)
        self.assertTrue((repo / "green-gate-report.txt.analyze").exists())

    def test_format_drift_reports_and_does_not_commit(self):
        repo = self._git_repo()
        before = self._log(repo)
        r = run_script(
            "green-gate", ["-m", "should not commit"],
            cwd=repo,
            env_extra={**self.env, "STUB_FORMAT_EXIT": "1"},
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self._log(repo), before)

    def _ws_with_plan(self):
        ws = pathlib.Path(self._tmp) / "ws"
        ws.mkdir(exist_ok=True)
        (ws / "plan.json").write_text(
            json.dumps({"feature": "t", "tasks": [
                {"id": 3, "title": "t3", "touches": ["lib/app.dart"], "depends_on": []},
            ]}),
            encoding="utf-8",
        )
        return ws

    def test_green_commits_and_dispatches_reviewer(self):
        """On all-green + commit with a workspace/task/base, green-gate must:
        commit the task, build the implementation-only review package, and
        dispatch the Reviewer headlessly (Item 3). No knowledge-graph step
        exists in the pipeline anymore."""
        repo = self._git_repo()
        (repo / "lib" / "app.dart").write_text("void main() { print('done'); }\n", encoding="utf-8")
        ws = self._ws_with_plan()
        d_log = pathlib.Path(self._tmp) / "d.log"
        base = "HEAD"
        r = run_script(
            "green-gate",
            ["-m", "Task 3: done", "-w", str(ws), "-t", "3", "-b", base],
            cwd=repo,
            env_extra={**self.env, "STUB_DISPATCH_LOG": str(d_log)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Task 3: done", self._log(repo))
        # reviewer dispatched headlessly
        dcalls = d_log.read_text(encoding="utf-8") if d_log.exists() else ""
        self.assertIn("two-model-reviewer", dcalls)
        # review package built into the workspace
        self.assertTrue((ws / "task-3-review-package.diff").exists())

    def test_no_commit_skips_reviewer_dispatch(self):
        """--no-commit validation changes nothing, so it must not dispatch
        the reviewer."""
        repo = self._git_repo()
        ws = self._ws_with_plan()
        d_log = pathlib.Path(self._tmp) / "d.log"
        r = run_script(
            "green-gate",
            ["--no-commit", "-w", str(ws), "-t", "3", "-b", "HEAD"],
            cwd=repo,
            env_extra={**self.env, "STUB_DISPATCH_LOG": str(d_log)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        dcalls = d_log.read_text(encoding="utf-8") if d_log.exists() else ""
        self.assertEqual(dcalls, "")


class TestRedGate(GateTestBase):
    def setUp(self):
        super().setUp()
        self.ws = pathlib.Path(self._tmp) / "ws"
        self.ws.mkdir()
        (self.ws / "task-3-brief.md").write_text(
            "# Task 3 Brief (scaffolded)\n", encoding="utf-8")

    def _red_env(self, **extra):
        env = dict(self.env)
        env["CODER_GATE"] = self.coder_gate
        env.update(extra)
        return env

    def test_dispatches_coder_and_chains_coder_gate(self):
        """On a scaffolded brief, red-gate dispatches Agente operador
        headlessly (Item 4) and chains straight into coder-gate — no
        materialization: the operador authors the RED tests."""
        dlog = pathlib.Path(self._tmp) / "dispatch.log"
        r = run_script(
            "red-gate", [str(self.ws), "3"],
            cwd=self.ws,
            env_extra=self._red_env(STUB_DISPATCH_LOG=str(dlog)),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = dlog.read_text(encoding="utf-8") if dlog.exists() else ""
        self.assertIn("--agent", calls)
        self.assertIn("two-model-coder", calls)
        self.assertIn("coder-gate ran", r.stderr)

    def test_ledgers_red_check(self):
        ledger = self.ws / "ledger.jsonl"
        ledger.write_text("", encoding="utf-8")
        dlog = pathlib.Path(self._tmp) / "dispatch.log"
        r = run_script(
            "red-gate", [str(self.ws), "3"],
            cwd=self.ws,
            env_extra=self._red_env(STUB_DISPATCH_LOG=str(dlog)),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("red_check", ledger.read_text(encoding="utf-8"))

    def test_propagates_coder_gate_exit(self):
        dlog = pathlib.Path(self._tmp) / "dispatch.log"
        r = run_script(
            "red-gate", [str(self.ws), "3"],
            cwd=self.ws,
            env_extra=self._red_env(
                STUB_DISPATCH_LOG=str(dlog), STUB_CODER_GATE_EXIT="2"),
        )
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_missing_brief_is_an_error(self):
        r = run_script("red-gate", [str(self.ws), "99"], cwd=self.ws, env_extra=self.env)
        self.assertEqual(r.returncode, 2)

    def test_defective_brief_does_not_dispatch(self):
        """Without a scaffolded brief there is nothing to dispatch —
        back to Agente diretor, never a bare Coder run."""
        (self.ws / "task-3-brief.md").unlink()
        dlog = pathlib.Path(self._tmp) / "dispatch.log"
        r = run_script(
            "red-gate", [str(self.ws), "3"],
            cwd=self.ws,
            env_extra=self._red_env(STUB_DISPATCH_LOG=str(dlog)),
        )
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        calls = dlog.read_text(encoding="utf-8") if dlog.exists() else ""
        self.assertEqual(calls, "", f"missing brief must not dispatch, got: {calls}")


class TestPubSync(GateTestBase):
    def test_resolution_ok_exits_zero(self):
        r = run_script("pub-sync", [], cwd=self._tmp, env_extra={**self.env, "STUB_DRYRUN_EXIT": "0"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_conflict_writes_report_and_fails(self):
        r = run_script("pub-sync", [], cwd=self._tmp, env_extra={**self.env, "STUB_DRYRUN_EXIT": "1"})
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(pathlib.Path(self._tmp, "pub-sync-report.txt").exists())

    def test_added_packages_resolve_without_graph(self):
        """pub-sync resolves added packages with no knowledge-graph step: the
        pipeline no longer indexes downloads, so adding packages must succeed
        silently (no warnings, no side effects)."""
        r = run_script(
            "pub-sync", ["pkg_a", "pkg_b"],
            cwd=self._tmp,
            env_extra={**self.env, "STUB_DRYRUN_EXIT": "0"},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = r.stdout + r.stderr
        self.assertNotIn("PUB-SYNC: warning", out)
        self.assertIn("lockfile consistent", out)


if __name__ == "__main__":
    unittest.main()
