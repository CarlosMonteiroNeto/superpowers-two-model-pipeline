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


class TokenKillTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="token-kill-tests-"))

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def write(self, name, body):
        p = pathlib.Path(self._tmp) / name
        p.write_text(body, encoding="utf-8")
        return p


class TestTokenKillErr(TokenKillTestBase):
    def test_err_minifies_error_log(self):
        """token-kill err must emit a compressed error view of a log file,
        preserving the error lines an LLM needs."""
        log = self.write(
            "err.log",
            "info line 1\nERROR: real failure here\ninfo line 2\n",
        )
        r = run_script("token-kill", ["err", str(log)], cwd=self._tmp, env_extra={"RTK_ENABLED": "0"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ERROR", r.stdout)

    def test_err_missing_file_is_usage(self):
        r = run_script("token-kill", ["err", str(self._tmp / "nope.log")], cwd=self._tmp, env_extra={})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


class TestTokenKillSrc(TokenKillTestBase):
    def test_src_strips_comments_and_blank_lines(self):
        """token-kill src must strip comments and blank lines from a source
        payload before it is sent to C/D (token reduction)."""
        src = self.write(
            "sample.dart",
            "// leading comment\n\nint x = 1; // trailing\n\n/* block */\nint y = 2;\n",
        )
        r = run_script("token-kill", ["src", str(src)], cwd=self._tmp, env_extra={})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("comment", r.stdout)
        self.assertIn("int x = 1;", r.stdout)
        self.assertIn("int y = 2;", r.stdout)


class TestTokenKillJson(TokenKillTestBase):
    def test_json_trims_report(self):
        """token-kill json must re-serialize a JSON report compactly."""
        rep = self.write(
            "review.json",
            '{\n  "verdict": "APPROVED",\n  "findings": []\n}\n',
        )
        r = run_script("token-kill", ["json", str(rep)], cwd=self._tmp, env_extra={})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('"verdict"', r.stdout)
        # compact: no newline between the two keys
        self.assertNotIn('{\n', r.stdout.replace('{\n  "verdict"', '{"verdict"'))

    def test_json_invalid_falls_back_to_cat(self):
        """Invalid JSON must fall back to raw output, never lose content."""
        rep = self.write("bad.json", "not json at all\n")
        r = run_script("token-kill", ["json", str(rep)], cwd=self._tmp, env_extra={})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("not json at all", r.stdout)


class TestTokenKillUsage(TokenKillTestBase):
    def test_no_args_is_usage(self):
        r = run_script("token-kill", [], cwd=self._tmp, env_extra={})
        self.assertEqual(r.returncode, 2)

    def test_bad_mode_is_usage(self):
        log = self.write("x.log", "hello\n")
        r = run_script("token-kill", ["bogus", str(log)], cwd=self._tmp, env_extra={})
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()