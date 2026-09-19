"""Regression module for the bounded dispatch retry (D11/rec #2).

A transient opencode failure (provider timeout rc=124, dropped connection)
used to stop the whole task: red-gate ledgered dispatch_interrupted and
exited, coder-gate's fix loop blocked, task-run blocked on the corrective
path. dispatch-retry wraps the launcher so those transient codes are retried
a bounded number of times before the original verdict survives.

These tests stub DISPATCH_BIN with a deterministic counter stub and prove the
wrapper's contract: transient codes retry, permanent codes (0 = dispatched,
2 = usage/missing prompt, 3 = wrong-agent refusal) pass through unchanged,
only the final attempt's code is returned, and failed attempts are ledgered.
"""

import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"

if os.name == "nt":
    _gb = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
    BASH = str(_gb) if _gb.exists() else "bash"
else:
    BASH = "bash"


def write_stub(directory, name, body):
    p = pathlib.Path(directory) / name
    p.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    subprocess.run([BASH, "-c", "chmod +x '{}'".format(p)], capture_output=True)
    return str(p)


def run_script(script, args, env_extra):
    env = dict(os.environ)
    env.update(env_extra)
    return subprocess.run(
        [BASH, str(SCRIPTS / script), *args],
        capture_output=True, text=True, env=env)


class DispatchRetryTest(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="dispatch-retry-"))
        self.stub_dir = self._tmp / "stubs"
        self.stub_dir.mkdir()
        self.ws = self._tmp / "ws"
        self.ws.mkdir()
        self.count_file = self._tmp / "calls.count"
        self.count_file.write_text("0", encoding="utf-8")
        self.out_log = self._tmp / "dispatch.out"
        self.ledger = self.ws / "ledger.jsonl"

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def dispatch_stub(self, fails=0, fail_exit="1", ok_exit="0"):
        count = str(self.count_file).replace("\\", "/")
        return write_stub(self.stub_dir, "dispatch", """
echo "$*" >> "{out}"
n=$(cat "{count}" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "{count}"
if [ "$n" -le {fails} ]; then exit {fail_exit}; fi
exit {ok_exit}
""".format(out=str(self.out_log).replace("\\", "/"), count=count,
           fails=fails, fail_exit=fail_exit, ok_exit=ok_exit))

    def calls(self):
        return int(self.count_file.read_text(encoding="utf-8"))

    def ledger_types(self):
        if not self.ledger.exists():
            return []
        return [line.split('"type":')[1].split('"')[1] for line in
                self.ledger.read_text(encoding="utf-8").splitlines()
                if '"type":' in line]

    def run_it(self, *args, fails=0, fail_exit="1", ok_exit="0", **env_extra):
        env = {"DISPATCH_BIN": self.dispatch_stub(
            fails=fails, fail_exit=fail_exit, ok_exit=ok_exit)}
        env.update(env_extra)
        return run_script("dispatch-retry", list(args), env)

    def test_success_first_attempt_passes_through_with_one_call(self):
        r = self.run_it("--task", "1", "--log",
                        str(self.ws / "task-1-coder.log"), ok_exit="0")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.calls(), 1)
        self.assertEqual(self.ledger_types(), [])

    def test_transient_failure_retries_until_success_and_ledgers(self):
        r = self.run_it("--task", "7", "--log",
                        str(self.ws / "task-7-coder.log"),
                        fails=2, fail_exit="124", ok_exit="0")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.calls(), 3)
        self.assertEqual(
            self.ledger_types().count("dispatch_retry"), 2)
        self.assertIn("124", self.ledger.read_text(encoding="utf-8"))

    def test_usage_exit_is_not_retried(self):
        r = self.run_it("--task", "1", "--log",
                        str(self.ws / "task-1-coder.log"), ok_exit="2")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self.calls(), 1)

    def test_wrong_agent_refusal_is_not_retried(self):
        r = self.run_it("--task", "1", "--log",
                        str(self.ws / "task-1-coder.log"), ok_exit="3")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual(self.calls(), 1)

    def test_gives_up_after_max_tries_preserving_last_code(self):
        r = self.run_it("--task", "1", "--log",
                        str(self.ws / "task-1-coder.log"),
                        fails=99, fail_exit="124", ok_exit="0")
        self.assertEqual(r.returncode, 124, r.stdout + r.stderr)
        self.assertEqual(self.calls(), 3)
        self.assertEqual(self.ledger_types().count("dispatch_retry"), 2)

    def test_max_tries_override_is_respected(self):
        r = self.run_it("--task", "1", "--log",
                        str(self.ws / "task-1-coder.log"),
                        fails=99, fail_exit="1", ok_exit="0",
                        DISPATCH_MAX_TRIES="2")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(self.calls(), 2)

    def test_arguments_forwarded_verbatim(self):
        r = self.run_it("--agent", "two-model-coder-go", "--task", "5",
                        "--continue", "ses-1", "--prompt-file",
                        str(self.ws / "fix.md"), "--log",
                        str(self.ws / "task-5-coder.log"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = self.out_log.read_text(encoding="utf-8")
        self.assertIn("--agent two-model-coder-go", out)
        self.assertIn("--task 5", out)
        self.assertIn("--continue ses-1", out)
        self.assertIn("--prompt-file", out)
        self.assertIn("fix.md", out)

    def test_retries_without_task_or_log_do_not_ledger(self):
        """The retry behavior is independent of the ledger; a dispatch invoked
        without --task/--log still retries but records nothing."""
        r = self.run_it("--agent", "two-model-coder-go",
                        "--prompt-file", str(self.ws / "brief.md"),
                        fails=1, fail_exit="124", ok_exit="0")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.calls(), 2)
        self.assertEqual(self.ledger_types(), [])


if __name__ == "__main__":
    unittest.main()