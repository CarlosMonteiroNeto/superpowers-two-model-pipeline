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


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)


def make_commit(repo, file_rel, content, msg):
    p = pathlib.Path(repo) / file_rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", msg)


class DocCheckBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="doc-check-tests-")
        self.repo = pathlib.Path(self._tmp) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "t")
        make_commit(self.repo, "lib/app.dart", "void main() {}", "feat: initial")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def run_it(self, repo=None):
        return subprocess.run(
            [BASH, str(SCRIPTS / "doc-check"), str(repo or self.repo)],
            capture_output=True, text=True,
        )


class TestDocCheck(DocCheckBase):
    def test_pipeline_change_with_readme_passes(self):
        make_commit(self.repo, "skills/foo/SKILL.md", "skill", "feat: skill")
        make_commit(self.repo, "README.txt", "readme", "docs: readme")
        r = self.run_it()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_pipeline_change_without_readme_fails(self):
        make_commit(self.repo, "skills/bar/SKILL.md", "skill", "feat: skill")
        r = self.run_it()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("README", r.stdout + r.stderr)

    def test_non_pipeline_change_passes(self):
        make_commit(self.repo, "lib/util.dart", "x", "fix: util")
        r = self.run_it()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_initial_commit_passes(self):
        r = self.run_it()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()