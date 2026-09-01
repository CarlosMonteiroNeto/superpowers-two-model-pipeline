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
    def test_green_exits_zero(self):
        ws = pathlib.Path(self._tmp) / "ws"
        ws.mkdir()
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


if __name__ == "__main__":
    unittest.main()
