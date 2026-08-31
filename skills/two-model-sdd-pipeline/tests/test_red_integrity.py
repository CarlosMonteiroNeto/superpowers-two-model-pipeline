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


class RedIntegrityBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="red-integrity-tests-")
        self.ws = pathlib.Path(self._tmp) / "ws"
        self.ws.mkdir()
        self.repo = pathlib.Path(self._tmp) / "repo"
        (self.repo / "test").mkdir(parents=True)
        self.src = self.ws / "task-3-test.dart"
        self.src.write_text("void main() { expect(true, isFalse); }\n", encoding="utf-8")
        self.dst = self.repo / "test" / "task_3_test.dart"
        self.dst.write_text(self.src.read_text(encoding="utf-8"), encoding="utf-8")
        self.brief = self.ws / "task-3-brief.md"

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def write_brief(self):
        self.brief.write_text(f"RED-TESTS:\n{self.src} -> {self.dst}\n", encoding="utf-8")

    def run_it(self, task="3"):
        return subprocess.run(
            [BASH, str(SCRIPTS / "red-integrity"), str(self.ws), task],
            capture_output=True, text=True,
        )


class TestRedIntegrity(RedIntegrityBase):
    def test_identical_tests_pass(self):
        self.write_brief()
        r = self.run_it()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_tampered_test_fails(self):
        self.write_brief()
        self.dst.write_text("tampered by the coder\n", encoding="utf-8")
        r = self.run_it()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(self.dst.name, r.stdout + r.stderr)

    def test_missing_brief_is_usage(self):
        r = self.run_it()
        self.assertEqual(r.returncode, 2)

    def test_brief_without_red_tests_is_usage(self):
        self.brief.write_text("no RED-TESTS block\n", encoding="utf-8")
        r = self.run_it()
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()