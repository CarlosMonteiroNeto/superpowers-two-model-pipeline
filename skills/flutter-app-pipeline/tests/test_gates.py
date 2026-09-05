import json
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
        self.graphify = write_stub(
            self.stub_dir,
            "graphify",
            """
echo "$*" >> "${STUB_LOG:?}"
exit "${STUB_GRAPHIFY_EXIT:-0}"
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
        # Native Windows stub for python-invoked scripts (subprocess.run with
        # a bash-shebang file fails on CreateProcess; a .cmd is executable).
        if os.name == "nt":
            self.graphify_cmd = pathlib.Path(self.stub_dir) / "graphify.cmd"
            self.graphify_cmd.write_text(
                '@echo off\necho %* >> "%STUB_LOG%"\nexit /b %STUB_GRAPHIFY_EXIT%\n',
                encoding="ascii",
            )
        else:
            self.graphify_cmd = self.graphify
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
            "GRAPHIFY_BIN": self.graphify,
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

    def test_does_not_chain_graphify_after_commit(self):
        """green-gate no longer rebuilds the project graph: the Reviewer reads
        the review package (diff), not the graph, and graphify is a
        Controller-side lazy optimization at brief time. The gate must stay
        fast and deterministic with no graphify side effect."""
        repo = self._git_repo()
        (repo / "lib" / "app.dart").write_text("void main() { print('chained'); }\n", encoding="utf-8")
        log = pathlib.Path(self._tmp) / "g.log"
        r = run_script(
            "green-gate", ["-m", "Task 1: chained"],
            cwd=repo,
            env_extra={**self.env, "STUB_LOG": str(log)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = log.read_text(encoding="utf-8") if log.exists() else ""
        self.assertEqual(calls, "", f"green-gate must not invoke graphify, got: {calls}")

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

    def test_green_commits_updates_graph_and_dispatches_reviewer(self):
        """On all-green + commit with a workspace/task/base, green-gate must:
        commit the task, run the post-commit graph update (ADR-0004), build the
        review package, and dispatch the Reviewer headlessly (Item 3)."""
        repo = self._git_repo()
        (repo / "lib" / "app.dart").write_text("void main() { print('done'); }\n", encoding="utf-8")
        ws = self._ws_with_plan()
        g_log = pathlib.Path(self._tmp) / "g.log"
        d_log = pathlib.Path(self._tmp) / "d.log"
        base = "HEAD"
        r = run_script(
            "green-gate",
            ["-m", "Task 3: done", "-w", str(ws), "-t", "3", "-b", base],
            cwd=repo,
            env_extra={**self.env, "STUB_LOG": str(g_log), "STUB_DISPATCH_LOG": str(d_log)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Task 3: done", self._log(repo))
        # post-commit graph update happened
        calls = g_log.read_text(encoding="utf-8") if g_log.exists() else ""
        self.assertTrue(any("update" in c for c in calls.splitlines()), calls)
        # reviewer dispatched headlessly
        dcalls = d_log.read_text(encoding="utf-8") if d_log.exists() else ""
        self.assertIn("two-model-reviewer", dcalls)
        # review package built into the workspace
        self.assertTrue((ws / "task-3-review-package.diff").exists())

    def test_no_commit_skips_graphify_and_reviewer(self):
        """--no-commit validation must not update the graph nor dispatch the
        reviewer (nothing changed)."""
        repo = self._git_repo()
        ws = self._ws_with_plan()
        g_log = pathlib.Path(self._tmp) / "g.log"
        d_log = pathlib.Path(self._tmp) / "d.log"
        r = run_script(
            "green-gate",
            ["--no-commit", "-w", str(ws), "-t", "3", "-b", "HEAD"],
            cwd=repo,
            env_extra={**self.env, "STUB_LOG": str(g_log), "STUB_DISPATCH_LOG": str(d_log)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = g_log.read_text(encoding="utf-8") if g_log.exists() else ""
        self.assertEqual(calls, "")
        dcalls = d_log.read_text(encoding="utf-8") if d_log.exists() else ""
        self.assertEqual(dcalls, "")


class TestRedGate(GateTestBase):
    def setUp(self):
        super().setUp()
        self.ws = pathlib.Path(self._tmp) / "ws"
        self.ws.mkdir()
        self.src_test = self.ws / "task-3-test.dart"
        self.src_test.write_text("void main() { expect(true, isFalse); }\n", encoding="utf-8")

    def _brief(self, dest="test/red_test.dart"):
        return self.ws / "task-3-brief.md"

    def _brief_text(self, expected_red="Error: api_client.dart does not exist"):
        return (
            "RED-TESTS:\n"
            f"{self.src_test} -> {self._brief().parent}/red_target.dart\n"
            "\n"
            "EXPECTED-RED:\n"
            f"{expected_red}\n"
        )

    def test_materializes_and_verifies_red_when_tests_fail(self):
        brief = self._brief()
        brief.write_text(self._brief_text(), encoding="utf-8")
        r = run_script(
            "red-gate", [str(self.ws), "3"],
            cwd=self.ws,
            env_extra={**self.env, "STUB_TEST_EXIT": "1",
                       "STUB_TEST_OUTPUT": "Error: api_client.dart does not exist"},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        target = self.ws / "red_target.dart"
        self.assertTrue(target.exists())
        self.assertEqual(target.read_text(encoding="utf-8"), self.src_test.read_text(encoding="utf-8"))

    def test_defective_brief_when_red_passes(self):
        brief = self._brief()
        brief.write_text(self._brief_text(), encoding="utf-8")
        r = run_script(
            "red-gate", [str(self.ws), "3"],
            cwd=self.ws,
            env_extra={**self.env, "STUB_TEST_EXIT": "0"},
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_defective_brief_when_red_fails_for_wrong_reason(self):
        """A RED failure whose report does NOT contain the brief's expected
        failure text is a defective brief, not a verified RED: the test
        failed for the wrong reason (e.g. a compile error in test setup
        instead of the missing production symbol)."""
        brief = self._brief()
        brief.write_text(
            self._brief_text(expected_red="Error: api_client.dart does not exist"),
            encoding="utf-8",
        )
        r = run_script(
            "red-gate", [str(self.ws), "3"],
            cwd=self.ws,
            env_extra={**self.env, "STUB_TEST_EXIT": "1",
                       "STUB_TEST_OUTPUT": "Error: type 'SessionStore' not found in test setup"},
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_missing_expected_red_is_defective(self):
        """A brief without an EXPECTED-RED block cannot be verified: the
        gate must reject it instead of rubber-stamping any failure."""
        brief = self._brief()
        brief.write_text(
            f"RED-TESTS:\n{self.src_test} -> {brief.parent}/red_target.dart\n",
            encoding="utf-8",
        )
        r = run_script(
            "red-gate", [str(self.ws), "3"],
            cwd=self.ws,
            env_extra={**self.env, "STUB_TEST_EXIT": "1",
                       "STUB_TEST_OUTPUT": "Error: anything"},
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_missing_brief_is_an_error(self):
        r = run_script("red-gate", [str(self.ws), "99"], cwd=self.ws, env_extra=self.env)
        self.assertEqual(r.returncode, 2)

    def test_does_not_chain_graphify_after_red_verified(self):
        """red-gate no longer rebuilds the project graph: the Coder reads the
        brief and the materialized tests, not the graph; graphify is a
        Controller-side lazy optimization at brief time."""
        brief = self._brief()
        brief.write_text(self._brief_text(), encoding="utf-8")
        log = pathlib.Path(self._tmp) / "g.log"
        r = run_script(
            "red-gate", [str(self.ws), "3"],
            cwd=self.ws,
            env_extra={**self.env, "STUB_TEST_EXIT": "1",
                       "STUB_TEST_OUTPUT": "Error: api_client.dart does not exist",
                       "STUB_LOG": str(log)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = log.read_text(encoding="utf-8") if log.exists() else ""
        self.assertEqual(calls, "", f"red-gate must not invoke graphify, got: {calls}")

    def test_red_verified_dispatches_coder(self):
        """On RED verified, red-gate dispatches the Coder headlessly (Item 4):
        no main-agent intermediation."""
        brief = self._brief()
        brief.write_text(self._brief_text(), encoding="utf-8")
        dlog = pathlib.Path(self._tmp) / "dispatch.log"
        r = run_script(
            "red-gate", [str(self.ws), "3"],
            cwd=self.ws,
            env_extra={**self.env, "STUB_TEST_EXIT": "1",
                       "STUB_TEST_OUTPUT": "Error: api_client.dart does not exist",
                       "STUB_DISPATCH_LOG": str(dlog)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = dlog.read_text(encoding="utf-8") if dlog.exists() else ""
        self.assertIn("--agent", calls)
        self.assertIn("two-model-coder", calls)

    def test_defective_brief_does_not_dispatch(self):
        """A defective brief (RED passes before implementation) must NOT
        dispatch the Coder - back to B for arbitration."""
        brief = self._brief()
        brief.write_text(self._brief_text(), encoding="utf-8")
        dlog = pathlib.Path(self._tmp) / "dispatch.log"
        r = run_script(
            "red-gate", [str(self.ws), "3"],
            cwd=self.ws,
            env_extra={**self.env, "STUB_TEST_EXIT": "0",
                       "STUB_DISPATCH_LOG": str(dlog)},
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        calls = dlog.read_text(encoding="utf-8") if dlog.exists() else ""
        self.assertEqual(calls, "", f"defective brief must not dispatch, got: {calls}")


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
    def test_invokes_graphify_update_subcommand_on_root(self):
        """graphify-regen must invoke `graphify update <root>` - the real
        CLI form - not the old `graphify <root> --update` (which the real
        CLI rejects; a wrapper was needed to translate it)."""
        log = pathlib.Path(self._tmp) / "graphify.log"
        r = run_script(
            "graphify-regen", [],
            cwd=self._tmp,
            env_extra={**self.env, "STUB_LOG": str(log)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = log.read_text(encoding="utf-8").splitlines()
        self.assertTrue(any(c.strip().startswith("update ") for c in calls), calls)
        # the root argument must resolve to the working directory (any path form)
        self.assertTrue(any(os.path.basename(self._tmp) in c for c in calls), calls)

    def test_never_uses_the_old_flag_form(self):
        log = pathlib.Path(self._tmp) / "graphify.log"
        r = run_script(
            "graphify-regen", [],
            cwd=self._tmp,
            env_extra={**self.env, "STUB_LOG": str(log)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = log.read_text(encoding="utf-8").splitlines()
        self.assertFalse(any("--update" in c for c in calls), calls)


class TestGraphifyPackage(GateTestBase):
    def _run_pkg(self, args, env_extra):
        env = dict(os.environ)
        env.update(self.env)
        env.update(env_extra)
        env["GRAPHIFY_BIN"] = str(self.graphify_cmd)
        # graphify-package has no .py extension (bash shebang for Unix);
        # invoke the real python module directly so Windows can run it.
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "graphify_package.py"), *args],
            cwd=str(self._tmp),
            env=env,
            capture_output=True,
            text=True,
        )

    def test_invokes_graphify_update_subcommand_on_package_dir(self):
        """graphify-package must invoke `graphify update <pkg_dir>` - the
        real CLI form - not `graphify <pkg_dir> --out <dir>`."""
        config = {
            "configVersion": 2,
            "packages": [
                {"name": "pkg_a", "rootUri": "file:///C:/cache/pkg_a/", "packageUri": "lib/"},
            ],
        }
        config_path = pathlib.Path(self._tmp) / "package_config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        log = pathlib.Path(self._tmp) / "g.log"
        r = self._run_pkg(
            ["pkg_a", "--config", str(config_path)],
            {"STUB_LOG": str(log)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = log.read_text(encoding="utf-8").splitlines()
        self.assertTrue(any(c.strip().startswith("update ") for c in calls), calls)
        self.assertTrue(any("pkg_a" in c for c in calls), calls)
        self.assertFalse(any("--out" in c for c in calls), calls)

    def test_missing_package_is_an_error(self):
        config_path = pathlib.Path(self._tmp) / "package_config.json"
        config_path.write_text(json.dumps({"configVersion": 2, "packages": []}), encoding="utf-8")
        r = self._run_pkg(["nope", "--config", str(config_path)], {})
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
