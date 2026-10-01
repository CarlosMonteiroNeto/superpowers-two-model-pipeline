"""Timeout cleanup and direct-child reaping contracts."""

import importlib.util
import pathlib
import subprocess
import sys
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills/two-model-sdd-pipeline/scripts/codex_process.py"


def subject():
    spec = importlib.util.spec_from_file_location("codex_process_timeout_subject", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CodexProcessTimeoutTests(unittest.TestCase):
    def test_registration_failure_uses_owned_direct_child_cleanup(self):
        process = subject()
        child = mock.Mock(pid=321)
        with mock.patch.object(process.subprocess, "Popen", return_value=child), \
             mock.patch.object(process, "_start_identity", return_value="owned-start"), \
             mock.patch.object(process, "_terminate_direct_child") as terminate, \
             mock.patch.object(process, "stop_owned_processes") as external_stop:
            with self.assertRaisesRegex(RuntimeError, "registration failed"):
                process.run_owned(["fake"], str(ROOT), on_start=lambda _record: (_ for _ in ()).throw(RuntimeError("registration failed")))
        terminate.assert_called_once_with(child, {"pid": 321, "start_identity": "owned-start"}, 0)
        external_stop.assert_not_called()

    def test_direct_cleanup_does_not_signal_reused_pid(self):
        process = subject()
        child = mock.Mock(pid=321)
        ownership = {"pid": 321, "start_identity": "old-owner"}
        with mock.patch.object(process, "_start_identity", return_value="new-owner"), \
             mock.patch.object(process.os, "name", "posix"), \
             mock.patch.object(process.os, "killpg", create=True) as killpg, \
             mock.patch.object(child, "wait", return_value=-9) as wait:
            process._terminate_direct_child(child, ownership, 0)
        killpg.assert_not_called()
        wait.assert_called_once()

    def test_real_timeout_reaps_child_and_preserves_output(self):
        process = subject()
        result = process.run_owned([
            sys.executable, "-u", "-c",
            "import sys,time; print('TIMEOUT-STDOUT',flush=True); "
            "print('TIMEOUT-STDERR',file=sys.stderr,flush=True); time.sleep(30)"],
            str(ROOT), timeout=0.5)

        self.assertTrue(result["timed_out"])
        self.assertIn("TIMEOUT-STDOUT", result["stdout"])
        self.assertIn("TIMEOUT-STDERR", result["stderr"])
        self.assertIsNone(process._start_identity(result["pid"]))

    def test_timeout_stops_descendant_processes(self):
        process = subject()
        code = ("import subprocess,sys,time; child=subprocess.Popen([sys.executable,'-c',"
                "'import time; time.sleep(30)']); print(child.pid,flush=True); time.sleep(30)")
        result = process.run_owned([sys.executable, "-u", "-c", code], str(ROOT), timeout=0.5)
        self.assertTrue(result["timed_out"])
        child_pid = int(result["stdout"].strip().splitlines()[0])
        self.assertIsNone(process._start_identity(child_pid))


if __name__ == "__main__":
    unittest.main()
