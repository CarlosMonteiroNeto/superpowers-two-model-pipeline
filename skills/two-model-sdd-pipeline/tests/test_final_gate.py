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


class FinalGateBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="final-gate-tests-")
        self.ws = pathlib.Path(self._tmp) / "ws"
        self.ws.mkdir()
        self.stub_dir = pathlib.Path(self._tmp) / "stubs"
        self.stub_dir.mkdir()
        # forward slashes: the ledger stores command strings; Windows backslashes
        # would be JSON-escaped and break tokenization.
        self.test_stub = write_stub(self.stub_dir, "tcmd", 'echo "tests ok"; exit "${STUB_TEST_EXIT:-0}"').replace("\\", "/")
        self.analyze_stub = write_stub(self.stub_dir, "acmd", 'echo "analyze ok"; exit "${STUB_ANALYZE_EXIT:-0}"').replace("\\", "/")
        self.env = {"STUB_TEST_EXIT": "0", "STUB_ANALYZE_EXIT": "0"}
        self.ledger = self.ws / "ledger.jsonl"

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def write_ledger(self, entries):
        self.ledger.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")

    def gate_entry(self):
        return {"ts": "t", "type": "gate", "task": "-", "summary": "gate",
                "test": self.test_stub, "analyze": self.analyze_stub}

    def review(self, task, verdict):
        return {"ts": "t", "type": "review_outcome", "task": str(task), "summary": verdict}

    def complete(self, task, parked=None):
        e = {"ts": "t", "type": "task_complete", "task": str(task), "summary": "ok"}
        if parked:
            e["PARKED"] = parked
        return e

    def run_it(self, total="3"):
        return subprocess.run(
            [BASH, str(SCRIPTS / "final-gate"), str(self.ws), total],
            capture_output=True, text=True, env={**os.environ, **self.env},
        )


class TestFinalGate(FinalGateBase):
    def test_ready_when_all_complete_and_green(self):
        self.write_ledger([
            self.gate_entry(),
            self.review(1, "APPROVED"), self.complete(1),
            self.review(2, "APPROVED"), self.complete(2),
            self.review(3, "APPROVED"), self.complete(3),
        ])
        r = self.run_it()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_missing_task_complete_blocks(self):
        self.write_ledger([
            self.gate_entry(),
            self.review(1, "APPROVED"), self.complete(1),
            self.review(2, "APPROVED"),
        ])
        r = self.run_it(total="3")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("task 3", r.stdout + r.stderr)

    def test_unresolved_send_back_blocks(self):
        self.write_ledger([
            self.gate_entry(),
            self.review(1, "SEND_BACK", ),
        ])
        r = self.run_it()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("SEND_BACK", r.stdout + r.stderr)

    def test_parked_critical_blocks(self):
        self.write_ledger([
            self.gate_entry(),
            self.review(1, "APPROVED"), self.complete(1, parked="sev=Critical"),
        ])
        r = self.run_it()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_parked_minor_does_not_block(self):
        self.write_ledger([
            self.gate_entry(),
            self.review(1, "APPROVED"), self.complete(1, parked="sev=Minor"),
        ])
        r = self.run_it(total="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_failing_test_command_blocks(self):
        self.write_ledger([
            self.gate_entry(),
            self.review(1, "APPROVED"), self.complete(1),
        ])
        self.env["STUB_TEST_EXIT"] = "1"
        r = self.run_it(total="1")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_missing_ledger_is_usage(self):
        r = self.run_it()
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()