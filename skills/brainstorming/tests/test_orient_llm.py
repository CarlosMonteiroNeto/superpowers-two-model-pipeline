import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
REPO = SCRIPTS.parent.parent.parent

if os.name == "nt":
    git_bash = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
    BASH = str(git_bash) if git_bash.exists() else "bash"
else:
    BASH = "bash"


def run_it(repo):
    return subprocess.run(
        [BASH, str(SCRIPTS / "orient-llm"), str(repo)],
        capture_output=True, text=True,
    )


class TestOrientLlm(unittest.TestCase):
    def test_readme_present_prints_and_exits_zero(self):
        r = run_it(REPO)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("README-LLM.md", r.stdout)

    def test_missing_readme_exits_one(self):
        tmp = tempfile.mkdtemp(prefix="orient-llm-tests-")
        try:
            r = run_it(tmp)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("README-LLM.md", r.stdout + r.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_bad_repo_arg_exits_two(self):
        r = run_it(pathlib.Path(tempfile.gettempdir()) / "definitely-not-a-repo")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()