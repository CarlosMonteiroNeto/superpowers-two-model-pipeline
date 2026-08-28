import os
import pathlib
import shutil
import subprocess
import sys
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
  test) echo "stub: flutter test $*"; exit "${STUB_TEST_EXIT:-0}" ;;
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
        self.graphify = write_stub(
            self.stub_dir,
            "graphify",
            """
echo "$*" >> "${STUB_LOG:?}"
exit "${STUB_GRAPHIFY_EXIT:-0}"
""",
        )
        self.env = {
            "FLUTTER_BIN": self.flutter,
            "DART_BIN": self.dart,
            "GRAPHIFY_BIN": self.graphify,
            "GIT_BIN": shutil.which("git") or "git",
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

    def test_chains_graphify_regen_after_commit(self):
        """After a green commit, the project graph is rebuilt before the next
        LLM (Reviewer / next task) reads the code."""
        repo = self._git_repo()
        (repo / "lib" / "app.dart").write_text("void main() { print('chained'); }\n", encoding="utf-8")
        log = pathlib.Path(self._tmp) / "g.log"
        r = run_script(
            "green-gate", ["-m", "Task 1: chained"],
            cwd=repo,
            env_extra={**self.env, "STUB_LOG": str(log)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = log.read_text(encoding="utf-8").splitlines()
        self.assertTrue(any("--update" in c for c in calls), calls)

    def test_no_commit_does_not_chain_graphify(self):
        """--no-commit (Phase 4 revalidation) changes nothing, so it must not
        rebuild the graph."""
        repo = self._git_repo()
        log = pathlib.Path(self._tmp) / "g.log"
        r = run_script(
            "green-gate", ["--no-commit"],
            cwd=repo,
            env_extra={**self.env, "STUB_LOG": str(log)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = log.read_text(encoding="utf-8") if log.exists() else ""
        self.assertEqual(calls, "")

    def test_graphify_failure_is_non_fatal(self):
        """A graphify failure must never fail a green gate: tests+analyze are
        the verdict; the graph rebuild is best-effort."""
        repo = self._git_repo()
        (repo / "lib" / "app.dart").write_text("void main() { print('nonfatal'); }\n", encoding="utf-8")
        r = run_script(
            "green-gate", ["-m", "Task 1: nonfatal"],
            cwd=repo,
            env_extra={**self.env, "STUB_GRAPHIFY_EXIT": "1", "STUB_LOG": str(pathlib.Path(self._tmp) / "g.log")},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Task 1: nonfatal", self._log(repo))


class TestRedGate(GateTestBase):
    def setUp(self):
        super().setUp()
        self.ws = pathlib.Path(self._tmp) / "ws"
        self.ws.mkdir()
        self.src_test = self.ws / "task-3-test.dart"
        self.src_test.write_text("void main() { expect(true, isFalse); }\n", encoding="utf-8")

    def _brief(self, dest="test/red_test.dart"):
        return self.ws / "task-3-brief.md"

    def test_materializes_and_verifies_red_when_tests_fail(self):
        brief = self._brief()
        brief.write_text(
            f"RED-TESTS:\n{self.src_test} -> {brief.parent}/red_target.dart\n",
            encoding="utf-8",
        )
        r = run_script(
            "red-gate", [str(self.ws), "3"],
            cwd=self.ws,
            env_extra={**self.env, "STUB_TEST_EXIT": "1"},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        target = self.ws / "red_target.dart"
        self.assertTrue(target.exists())
        self.assertEqual(target.read_text(encoding="utf-8"), self.src_test.read_text(encoding="utf-8"))

    def test_defective_brief_when_red_passes(self):
        brief = self._brief()
        brief.write_text(
            f"RED-TESTS:\n{self.src_test} -> {brief.parent}/red_target.dart\n",
            encoding="utf-8",
        )
        r = run_script(
            "red-gate", [str(self.ws), "3"],
            cwd=self.ws,
            env_extra={**self.env, "STUB_TEST_EXIT": "0"},
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_missing_brief_is_an_error(self):
        r = run_script("red-gate", [str(self.ws), "99"], cwd=self.ws, env_extra=self.env)
        self.assertEqual(r.returncode, 2)

    def test_chains_graphify_regen_after_red_verified(self):
        """After RED is verified, the graph is rebuilt so the Coder (LLM)
        reads the freshly materialized test files through the graph."""
        brief = self._brief()
        brief.write_text(
            f"RED-TESTS:\n{self.src_test} -> {brief.parent}/red_target.dart\n",
            encoding="utf-8",
        )
        log = pathlib.Path(self._tmp) / "g.log"
        r = run_script(
            "red-gate", [str(self.ws), "3"],
            cwd=self.ws,
            env_extra={**self.env, "STUB_TEST_EXIT": "1", "STUB_LOG": str(log)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = log.read_text(encoding="utf-8").splitlines()
        self.assertTrue(any("--update" in c for c in calls), calls)

    def test_red_gate_respects_graphify_enabled(self):
        brief = self._brief()
        brief.write_text(
            f"RED-TESTS:\n{self.src_test} -> {brief.parent}/red_target.dart\n",
            encoding="utf-8",
        )
        log = pathlib.Path(self._tmp) / "g.log"
        r = run_script(
            "red-gate", [str(self.ws), "3"],
            cwd=self.ws,
            env_extra={**self.env, "STUB_TEST_EXIT": "1", "STUB_LOG": str(log), "GRAPHIFY_ENABLED": "0"},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = log.read_text(encoding="utf-8") if log.exists() else ""
        self.assertEqual(calls, "")


class TestPubSync(GateTestBase):
    def test_resolution_ok_exits_zero(self):
        r = run_script("pub-sync", [], cwd=self._tmp, env_extra={**self.env, "STUB_DRYRUN_EXIT": "0"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_conflict_writes_report_and_fails(self):
        r = run_script("pub-sync", [], cwd=self._tmp, env_extra={**self.env, "STUB_DRYRUN_EXIT": "1"})
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(pathlib.Path(self._tmp, "pub-sync-report.txt").exists())

    def test_chains_graphify_package_for_added_packages(self):
        """pub-sync knows which packages were added; it must index each one
        before returning. The chain is best-effort: graphify-package fails
        without a package_config.json, and pub-sync must still succeed."""
        log = pathlib.Path(self._tmp) / "g.log"
        r = run_script(
            "pub-sync", ["pkg_a", "pkg_b"],
            cwd=self._tmp,
            env_extra={**self.env, "STUB_LOG": str(log), "STUB_DRYRUN_EXIT": "0"},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = r.stdout + r.stderr
        self.assertIn("PUB-SYNC: warning", out)
        self.assertIn("pkg_a", out)
        self.assertIn("pkg_b", out)

    def test_pub_sync_respects_graphify_enabled(self):
        log = pathlib.Path(self._tmp) / "g.log"
        r = run_script(
            "pub-sync", ["pkg_a"],
            cwd=self._tmp,
            env_extra={**self.env, "STUB_LOG": str(log), "STUB_DRYRUN_EXIT": "0", "GRAPHIFY_ENABLED": "0"},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("PUB-SYNC: warning", r.stdout + r.stderr)


class TestGraphifyRegen(GateTestBase):
    def test_invokes_graphify_with_update_on_root(self):
        log = pathlib.Path(self._tmp) / "graphify.log"
        r = run_script(
            "graphify-regen", [],
            cwd=self._tmp,
            env_extra={**self.env, "STUB_LOG": str(log)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = log.read_text(encoding="utf-8").splitlines()
        self.assertTrue(any("--update" in c for c in calls), calls)
        # the root argument must resolve to the working directory (any path form)
        self.assertTrue(any(os.path.basename(self._tmp) in c for c in calls), calls)


if __name__ == "__main__":
    unittest.main()