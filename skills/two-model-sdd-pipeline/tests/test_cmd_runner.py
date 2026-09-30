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


class CmdTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="cmd-tests-")
        self.stub_dir = pathlib.Path(self._tmp) / "stubs"
        self.stub_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)


class TestCmdUsage(CmdTestBase):
    def test_missing_full_file_is_usage(self):
        r = run_script("cmd", [], cwd=self._tmp, env_extra={"RTK_ENABLED": "0"})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_no_command_is_usage(self):
        out = pathlib.Path(self._tmp) / "o.txt"
        r = run_script("cmd", ["--full-file", str(out), "--"], cwd=self._tmp, env_extra={"RTK_ENABLED": "0"})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


class TestCmdRunner(CmdTestBase):
    @unittest.skipUnless(os.name == "nt", "Git Bash Windows path regression")
    def test_windows_full_file_path_works_without_msys_argument_conversion(self):
        out = pathlib.Path(self._tmp) / "nested output" / "out.txt"
        r = run_script(
            "cmd",
            ["--full-file", str(out), "--", "echo", "windows-path-ok"],
            cwd=self._tmp,
            env_extra={"RTK_ENABLED": "0", "MSYS2_ARG_CONV_EXCL": "*"},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(out.read_text(encoding="utf-8").strip(), "windows-path-ok")

    def test_saves_full_output_and_preserves_exit_code(self):
        """cmd must save FULL output to --full-file and return the command's
        true exit code (RTK is disabled here; passthrough)."""
        out = pathlib.Path(self._tmp) / "out.txt"
        r = run_script(
            "cmd",
            ["--full-file", str(out), "--", "sh", "-c", "echo hello-full; exit 7"],
            cwd=self._tmp,
            env_extra={"RTK_ENABLED": "0"},
        )
        self.assertEqual(r.returncode, 7, r.stdout + r.stderr)
        self.assertIn("hello-full", out.read_text(encoding="utf-8"))
        self.assertIn("hello-full", r.stdout)

    def test_passthrough_shows_full_output_when_rtk_disabled(self):
        out = pathlib.Path(self._tmp) / "out.txt"
        r = run_script(
            "cmd",
            ["--full-file", str(out), "--", "echo", "raw-line-1"],
            cwd=self._tmp,
            env_extra={"RTK_ENABLED": "0"},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("raw-line-1", r.stdout)
        self.assertIn("raw-line-1", out.read_text(encoding="utf-8"))

    def _git_repo(self):
        repo = pathlib.Path(self._tmp) / "repo"
        repo.mkdir()
        g = shutil.which("git") or "git"
        subprocess.run([g, "init", "-q"], cwd=str(repo), capture_output=True, check=True)
        subprocess.run([g, "config", "user.email", "test@example.com"], cwd=str(repo), capture_output=True, check=True)
        subprocess.run([g, "config", "user.name", "Test"], cwd=str(repo), capture_output=True, check=True)
        (repo / "f.txt").write_text("hello\n", encoding="utf-8")
        return repo

    def test_rtk_filter_used_when_available(self):
        """When RTK is available and a filter matches, stdout is the compressed
        view while the file keeps the FULL output. A stub rtk that collapses
        everything to one line proves the split."""
        rtk = write_stub(
            self.stub_dir,
            "rtk",
            """
echo "stub rtk pipe"; exit 0
""",
        )
        repo = self._git_repo()
        out = pathlib.Path(self._tmp) / "out.txt"
        r = run_script(
            "cmd",
            ["--full-file", str(out), "--", "git", "status"],
            cwd=repo,
            env_extra={"RTK_BIN": rtk},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("stub rtk pipe", r.stdout)
        # full output must still be in the file (git status of the repo
        # prints at least a branch line)
        self.assertTrue(out.exists())
        self.assertNotEqual(out.read_text(encoding="utf-8").strip(), "")

    def test_rtk_failure_never_masks_command_verdict(self):
        """If the rtk binary fails mid-pipe, cmd must return the COMMAND's
        exit code (PIPESTATUS[0]), not rtk's - a failing rtk must never turn
        a green command red or vice versa. The file keeps full output."""
        rtk = write_stub(
            self.stub_dir,
            "rtk",
            """
echo "rtk exploded" >&2; exit 9
""",
        )
        repo = self._git_repo()
        subprocess.run(["git", "add", "-A"], cwd=str(repo), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=str(repo), capture_output=True, check=True)
        out = pathlib.Path(self._tmp) / "out.txt"
        r = run_script(
            "cmd",
            ["--full-file", str(out), "--", "git", "status"],
            cwd=repo,
            env_extra={"RTK_BIN": rtk},
        )
        # git status exits 0; the failing rtk must not change the verdict.
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(out.exists())
        self.assertIn("On branch", out.read_text(encoding="utf-8"))


class TestRunGates(CmdTestBase):
    def _init_candidate_repo(self):
        subprocess.run(["git", "init", "-q", self._tmp], check=True)
        subprocess.run(["git", "-C", self._tmp, "config", "user.name", "Pipeline Test"], check=True)
        subprocess.run(["git", "-C", self._tmp, "config", "user.email", "pipeline@example.invalid"], check=True)
        anchor = pathlib.Path(self._tmp) / "README.md"
        anchor.write_text("candidate\n", encoding="utf-8")
        subprocess.run(["git", "-C", self._tmp, "add", "README.md"], check=True)
        subprocess.run(["git", "-C", self._tmp, "commit", "-qm", "candidate"], check=True)

    def write_legacy_gate(self, ws, test_cmd, analyze_cmd):
        (ws / "ledger.jsonl").write_text(json.dumps({
            "type": "gate",
            "toolchain_id": "legacy-python-v1",
            "lang": "python",
            "test_cmd": test_cmd,
            "analyze_cmd": analyze_cmd,
        }) + "\n", encoding="utf-8")

    def test_green_exits_zero(self):
        ws = pathlib.Path(self._tmp) / "ws"
        ws.mkdir()
        self.write_legacy_gate(ws, "echo ok-test", "echo ok-analyze")
        r = run_script(
            "run-gates",
            [str(ws), "echo ok-test", "echo ok-analyze"],
            cwd=self._tmp,
            env_extra={"RTK_ENABLED": "0"},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((ws / "run-gates-test.txt").exists())
        self.assertTrue((ws / "run-gates-analyze.txt").exists())

    def test_test_failure_exits_one(self):
        ws = pathlib.Path(self._tmp) / "ws"
        ws.mkdir()
        self.write_legacy_gate(ws, "exit 1", "echo ok-analyze")
        r = run_script(
            "run-gates",
            [str(ws), "exit 1", "echo ok-analyze"],
            cwd=self._tmp,
            env_extra={"RTK_ENABLED": "0"},
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue((ws / "run-gates-test.txt").exists())

    def test_analyze_failure_exits_two(self):
        ws = pathlib.Path(self._tmp) / "ws"
        ws.mkdir()
        self.write_legacy_gate(ws, "echo ok-test", "exit 2")
        r = run_script(
            "run-gates",
            [str(ws), "echo ok-test", "exit 2"],
            cwd=self._tmp,
            env_extra={"RTK_ENABLED": "0"},
        )
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_usage_error_exits_three(self):
        ws = pathlib.Path(self._tmp) / "ws"
        ws.mkdir()
        r = run_script("run-gates", [str(ws), "echo only-test"], cwd=self._tmp, env_extra={"RTK_ENABLED": "0"})
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)

    def test_unmatched_positional_and_commands_modes_do_not_execute_caller_commands(self):
        ws = pathlib.Path(self._tmp) / "unmatched-ws"
        ws.mkdir()
        test_cmd = "echo UNMATCHED_COMMAND_RAN"
        analyze_cmd = "true"

        for args in ([str(ws), test_cmd, analyze_cmd],
                     [str(ws), "--commands", test_cmd, analyze_cmd]):
            result = run_script("run-gates", list(args), cwd=self._tmp, env_extra={"RTK_ENABLED": "0"})
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("UNMATCHED_COMMAND_RAN", result.stdout + result.stderr)

    def test_structured_single_gate_requires_exact_toolchain_selection(self):
        ws = pathlib.Path(self._tmp) / "structured-ws"
        ws.mkdir()
        marker = pathlib.Path(self._tmp) / "structured-command-ran"
        descriptor = {
            "available": True,
            "toolchain_id": "python-structured-v1",
            "language": "python",
            "project_root": str(self._tmp),
            "commands": {
                "test": {"argv": [sys.executable, "-c",
                                   "import pathlib; pathlib.Path(r'{}').write_text('ran')".format(marker)],
                         "cwd": str(self._tmp), "env": {}},
                "analyze": {"argv": [sys.executable, "-c", "pass"], "cwd": str(self._tmp), "env": {}},
            },
        }
        (ws / "ledger.jsonl").write_text(json.dumps({
            "type": "gate", "toolchain_id": "python-structured-v1", "lang": "python",
            "toolchain_descriptor": descriptor,
        }) + "\n", encoding="utf-8")

        result = run_script(
            "run-gates", [str(ws), "python test", "python analyze"],
            cwd=self._tmp, env_extra={"RTK_ENABLED": "0"},
        )

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(marker.exists(), "a structured descriptor needs exact task/toolchain identity")

    def test_exact_toolchain_selection_is_not_misrouted_to_legacy_ledger_mode(self):
        self._init_candidate_repo()
        ws = pathlib.Path(self._tmp) / ".git" / "multi-structured-ws"
        ws.mkdir()
        (ws / "plan.json").write_text(json.dumps({
            "tasks": [{"id": 1, "toolchain_id": "python-selected-v1", "touches": ["tests/test_selected.py"]}],
        }), encoding="utf-8")
        entries = []
        for identity in ("python-first-v1", "python-selected-v1"):
            entries.append({
                "type": "gate", "toolchain_id": identity, "lang": "python",
                "toolchain_descriptor": {
                    "available": True, "toolchain_id": identity, "language": "python",
                    "project_root": str(self._tmp),
                    "commands": {
                        "test": {"argv": [sys.executable, "-c", "pass"], "cwd": str(self._tmp), "env": {}},
                        "analyze": {"argv": [sys.executable, "-c", "pass"], "cwd": str(self._tmp), "env": {}},
                    },
                },
            })
        (ws / "ledger.jsonl").write_text(
            "\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8",
        )

        result = run_script(
            "run-gates", [str(ws), "--tasks", "1"],
            cwd=self._tmp, env_extra={"RTK_ENABLED": "0"},
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class TestCmdFlutterRtk(CmdTestBase):
    def test_flutter_test_keeps_true_exit_code_and_full_file(self):
        """For flutter test, cmd runs the raw command (verdict = its exit code),
        writes FULL output to the file, and shows the RTK-compressed view on
        stdout (derived from the file via `rtk test -- cat <file>`). RTK wrapper
        exit codes are unreliable (mask child exit) so the verdict comes from the
        raw run and the compressed view is a read-only derivation."""
        rtk = write_stub(
            self.stub_dir,
            "rtk",
            """
cat; exit 0
""",
        )
        out = pathlib.Path(self._tmp) / "out.txt"
        r = run_script(
            "cmd",
            ["--full-file", str(out), "--", "sh", "-c",
             "echo flutter-run; exit 7"],
            cwd=self._tmp,
            env_extra={"RTK_BIN": rtk, "RTK_ENABLED": "1"},
        )
        # the raw command's exit code is the verdict (never rtk's).
        self.assertEqual(r.returncode, 7, r.stdout + r.stderr)
        # full output is in the file.
        self.assertIn("flutter-run", out.read_text(encoding="utf-8"))
        # stdout shows the (stub) compressed view derived from the full file.
        self.assertIn("flutter-run", r.stdout)

    def _flutter_stub(self, exit_code="0", output="stub: flutter ran"):
        return write_stub(
            self.stub_dir,
            "flutter",
            f"""
echo "{output}"
exit {exit_code}
""",
        )

    def test_flutter_test_runs_through_rtk_test_wrapper(self):
        """flutter test maps to the `rtk test` wrapper: the compressed LLM view
        on stdout comes from it, while the raw command's exit code is the
        verdict and the file keeps full output."""
        rtk = write_stub(
            self.stub_dir,
            "rtk",
            """
echo "stub rtk test"; cat; exit 0
""",
        )
        out = pathlib.Path(self._tmp) / "out.txt"
        flutter = self._flutter_stub()
        r = run_script(
            "cmd",
            ["--full-file", str(out), "--", flutter, "test"],
            cwd=self._tmp,
            env_extra={"RTK_BIN": rtk, "RTK_ENABLED": "1"},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("stub rtk test", r.stdout)
        self.assertIn("stub: flutter ran", out.read_text(encoding="utf-8"))

    def test_flutter_analyze_runs_through_rtk_err_when_available(self):
        """cmd must run flutter analyze raw for the verdict, save full output to
        the file, and show the RTK err compressed view on stdout."""
        rtk = write_stub(
            self.stub_dir,
            "rtk",
            """
echo "stub rtk err"; cat; exit 0
""",
        )
        out = pathlib.Path(self._tmp) / "out.txt"
        flutter = self._flutter_stub()
        r = run_script(
            "cmd",
            ["--full-file", str(out), "--", flutter, "analyze"],
            cwd=self._tmp,
            env_extra={"RTK_BIN": rtk, "RTK_ENABLED": "1"},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("stub rtk err", r.stdout)
        self.assertIn("stub: flutter ran", out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
