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


class DispatchTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="dispatch-tests-"))
        self.stub_dir = self._tmp / "stubs"
        self.stub_dir.mkdir()
        # opencode stub: logs argv to STUB_ARGV, emits a JSON event stream with
        # a sessionID, then a text reply.
        self.opencode = write_stub(
            self.stub_dir,
            "opencode",
            """
echo "$*" >> "${STUB_ARGV:?}"
echo '{"type":"step_start","sessionID":"ses_fixed123"}'
echo '{"type":"text","part":{"type":"text","text":"DONE"}}'
exit "${STUB_OPENCODE_EXIT:-0}"
""",
        )
        self.ws = self._tmp / "ws"
        self.ws.mkdir()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def brief(self, body="Brief: do the thing.\n"):
        p = self.ws / "task-3-brief.md"
        p.write_text(body, encoding="utf-8")
        return p

    def argv_log(self):
        return str(self._tmp / "stub-argv.log")

    def dispatch_log(self):
        return str(self._tmp / "dispatch-output.log")


class TestDispatchFresh(DispatchTestBase):
    def test_dispatches_agent_with_brief_and_tees_json_log(self):
        brief = self.brief()
        argv_log = self.argv_log()
        dlog = self.dispatch_log()
        r = run_script(
            "dispatch",
            ["--agent", "two-model-coder", "--task", "3",
             "--prompt-file", str(brief), "--log", dlog],
            cwd=self._tmp,
            env_extra={"OPENCODE_BIN": self.opencode, "STUB_ARGV": argv_log},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # the JSON event stream is teed to the dispatch log
        self.assertTrue(pathlib.Path(dlog).exists())
        self.assertIn("ses_fixed123", pathlib.Path(dlog).read_text(encoding="utf-8"))
        # the agent name and prompt file reach opencode (recorded by the stub)
        argv = pathlib.Path(argv_log).read_text(encoding="utf-8")
        self.assertIn("--agent", argv)
        self.assertIn("two-model-coder", argv)
        self.assertIn(str(brief), argv)

    def test_session_id_recorded_for_resume(self):
        brief = self.brief()
        argv_log = self.argv_log()
        dlog = self.dispatch_log()
        r = run_script(
            "dispatch",
            ["--agent", "two-model-coder", "--task", "3",
             "--prompt-file", str(brief), "--log", dlog],
            cwd=self._tmp,
            env_extra={"OPENCODE_BIN": self.opencode, "STUB_ARGV": argv_log},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # the session record is written next to the log (real pipeline:
        # --log <ws>/task-N-coder.log, so this is the workspace)
        sid = (pathlib.Path(dlog).parent / "task-3-session.txt").read_text(
            encoding="utf-8").strip()
        self.assertEqual(sid, "ses_fixed123")

    def test_opencode_failure_propagates(self):
        brief = self.brief()
        argv_log = self.argv_log()
        dlog = self.dispatch_log()
        r = run_script(
            "dispatch",
            ["--agent", "two-model-coder", "--task", "3",
             "--prompt-file", str(brief), "--log", dlog],
            cwd=self._tmp,
            env_extra={"OPENCODE_BIN": self.opencode, "STUB_ARGV": argv_log,
                       "STUB_OPENCODE_EXIT": "9"},
        )
        self.assertEqual(r.returncode, 9, r.stdout + r.stderr)


class TestDispatchResume(DispatchTestBase):
    def test_continue_resumes_session(self):
        brief = self.brief()
        argv_log = self.argv_log()
        dlog = self.dispatch_log()
        r = run_script(
            "dispatch",
            ["--agent", "two-model-coder", "--task", "3",
             "--continue", "ses_prev42", "--prompt-file", str(brief),
             "--log", dlog],
            cwd=self._tmp,
            env_extra={"OPENCODE_BIN": self.opencode, "STUB_ARGV": argv_log},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        argv = pathlib.Path(argv_log).read_text(encoding="utf-8")
        self.assertIn("--continue", argv)
        self.assertIn("ses_prev42", argv)


class TestDispatchUsage(DispatchTestBase):
    def test_missing_args_is_usage(self):
        r = run_script("dispatch", [], cwd=self._tmp, env_extra={"OPENCODE_BIN": self.opencode})
        self.assertEqual(r.returncode, 2)

    def test_missing_prompt_file_is_usage(self):
        r = run_script(
            "dispatch",
            ["--agent", "two-model-coder", "--task", "3",
             "--prompt-file", str(self.ws / "nope.md"), "--log", self.dispatch_log()],
            cwd=self._tmp,
            env_extra={"OPENCODE_BIN": self.opencode},
        )
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()