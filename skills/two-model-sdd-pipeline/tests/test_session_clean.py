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


class SessionCleanTest(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="session-clean-tests-"))
        self.stub_dir = self._tmp / "stubs"
        self.stub_dir.mkdir()
        self.ws = self._tmp / "ws"
        self.ws.mkdir()
        # opencode stub: record every `session delete <id>` call.
        self.opencode = write_stub(
            self.stub_dir,
            "opencode",
            """
if [ "$1" = "session" ] && [ "$2" = "delete" ]; then
  echo "${3:-}" >> "${DELETED_LOG:?}"
fi
exit 0
""",
        )
        self.deleted = self._tmp / "deleted.log"

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def deleted_sids(self):
        if not self.deleted.exists():
            return []
        return self.deleted.read_text(encoding="utf-8").strip().splitlines()

    def test_task_mode_deletes_only_that_tasks_sessions(self):
        (self.ws / "task-3-session.txt").write_text("ses_3\n", encoding="utf-8")
        (self.ws / "task-3-two-model-coder-session.txt").write_text("ses_3c\n", encoding="utf-8")
        (self.ws / "task-4-session.txt").write_text("ses_4\n", encoding="utf-8")
        r = run_script(
            "session-clean", [str(self.ws), "3"],
            cwd=self._tmp,
            env_extra={"OPENCODE_BIN": self.opencode, "DELETED_LOG": str(self.deleted)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(self.deleted_sids()), ["ses_3", "ses_3c"])
        self.assertFalse((self.ws / "task-3-session.txt").exists())
        self.assertFalse((self.ws / "task-3-two-model-coder-session.txt").exists())
        self.assertTrue((self.ws / "task-4-session.txt").exists())

    def test_all_mode_deletes_every_session(self):
        (self.ws / "task-1-session.txt").write_text("ses_1\n", encoding="utf-8")
        (self.ws / "task-2-session.txt").write_text("ses_2\n", encoding="utf-8")
        (self.ws / "task-2-two-model-reviewer-session.txt").write_text("ses_2r\n", encoding="utf-8")
        r = run_script(
            "session-clean", [str(self.ws), "all"],
            cwd=self._tmp,
            env_extra={"OPENCODE_BIN": self.opencode, "DELETED_LOG": str(self.deleted)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(self.deleted_sids()), ["ses_1", "ses_2", "ses_2r"])
        self.assertEqual(list(self.ws.iterdir()), [])

    def test_no_session_files_is_ok(self):
        r = run_script(
            "session-clean", [str(self.ws), "3"],
            cwd=self._tmp,
            env_extra={"OPENCODE_BIN": self.opencode, "DELETED_LOG": str(self.deleted)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.deleted_sids(), [])

    def test_missing_args_is_usage(self):
        r = run_script("session-clean", [], cwd=self._tmp, env_extra={})
        self.assertEqual(r.returncode, 2)

    def test_delete_failure_is_non_fatal_and_record_still_removed(self):
        (self.ws / "task-3-session.txt").write_text("ses_3\n", encoding="utf-8")
        failing = write_stub(
            self.stub_dir,
            "opencode-failing",
            "exit 1\n",
        )
        r = run_script(
            "session-clean", [str(self.ws), "3"],
            cwd=self._tmp,
            env_extra={"OPENCODE_BIN": failing, "DELETED_LOG": str(self.deleted)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.ws / "task-3-session.txt").exists())


if __name__ == "__main__":
    unittest.main()