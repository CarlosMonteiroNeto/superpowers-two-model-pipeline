import hashlib
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


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RedIntegrityBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="red-integrity-tests-")
        self.ws = pathlib.Path(self._tmp) / "ws"
        self.ws.mkdir()
        self.repo = pathlib.Path(self._tmp) / "repo"
        (self.repo / "test").mkdir(parents=True)
        self.test_file = self.repo / "test" / "task_3_test.dart"
        self.test_file.write_text("void main() { expect(true, isFalse); }\n", encoding="utf-8")
        self.snapshot = self.ws / "task-3-test-snapshot.txt"

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def write_snapshot(self, digest=None):
        self.snapshot.write_text(
            "%s  %s\n" % (digest or sha(self.test_file), "test/task_3_test.dart"),
            encoding="utf-8",
        )

    def run_it(self, task="3"):
        return subprocess.run(
            [BASH, str(SCRIPTS / "red-integrity"), str(self.ws), task],
            capture_output=True, text=True, cwd=str(self.repo),
        )


class TestRedIntegrity(RedIntegrityBase):
    def test_snapshot_match_passes(self):
        self.write_snapshot()
        r = self.run_it()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_weakened_test_fails(self):
        self.write_snapshot()
        self.test_file.write_text("void main() {}\n", encoding="utf-8")
        r = self.run_it()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("task_3_test.dart", r.stdout + r.stderr)

    def test_missing_test_file_fails(self):
        self.write_snapshot()
        self.test_file.unlink()
        r = self.run_it()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_missing_snapshot_is_usage(self):
        r = self.run_it()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_empty_snapshot_is_usage(self):
        self.snapshot.write_text("\n", encoding="utf-8")
        r = self.run_it()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
