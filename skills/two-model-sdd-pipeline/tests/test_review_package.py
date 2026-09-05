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


class ReviewPackageTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="review-package-tests-"))
        self.ws = self._tmp / "ws"
        self.ws.mkdir()
        self.repo = self._tmp / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(self.repo), check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(self.repo), check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(self.repo), check=True)
        (self.repo / "app.dart").write_text("void main() {}\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(self.repo), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=str(self.repo), check=True)
        self.base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(self.repo),
                                   capture_output=True, text=True, check=True).stdout.strip()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _change_and_commit(self):
        (self.repo / "app.dart").write_text("void main() { print('x'); }\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(self.repo), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "change"], cwd=str(self.repo), check=True)
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(self.repo),
                              capture_output=True, text=True, check=True).stdout.strip()


class TestReviewPackage(ReviewPackageTestBase):
    def test_default_package_has_diff_only(self):
        head = self._change_and_commit()
        out = self._tmp / "pkg.diff"
        r = run_script("review-package", [str(self.ws), self.base, head, str(out)],
                       cwd=str(self.repo), env_extra={})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = out.read_text(encoding="utf-8")
        self.assertIn("## Commits", text)
        self.assertIn("## Diff", text)
        self.assertNotIn("## Task Brief", text)

    def test_task_arg_inlines_brief_and_interfaces(self):
        head = self._change_and_commit()
        (self.ws / "task-3-brief.md").write_text("# Task 3\n\nBuild the feature.\n", encoding="utf-8")
        (self.ws / "task-3-interfaces.md").write_text("## lib/app.dart\n\ninterface notes\n", encoding="utf-8")
        out = self._tmp / "pkg.diff"
        r = run_script("review-package", [str(self.ws), self.base, head, str(out), "3"],
                       cwd=str(self.repo), env_extra={})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = out.read_text(encoding="utf-8")
        self.assertIn("## Task Brief", text)
        self.assertIn("Build the feature.", text)
        self.assertIn("## Interfaces", text)
        self.assertIn("interface notes", text)
        self.assertIn("## Commits", text)
        self.assertIn("## Diff", text)
        # order: brief before interfaces before commits
        self.assertLess(text.index("## Task Brief"), text.index("## Interfaces"))
        self.assertLess(text.index("## Interfaces"), text.index("## Commits"))

    def test_task_arg_tolerates_missing_brief_or_interfaces(self):
        head = self._change_and_commit()
        (self.ws / "task-3-brief.md").write_text("# Task 3\n\nBuild.\n", encoding="utf-8")
        out = self._tmp / "pkg.diff"
        r = run_script("review-package", [str(self.ws), self.base, head, str(out), "3"],
                       cwd=str(self.repo), env_extra={})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = out.read_text(encoding="utf-8")
        self.assertIn("## Task Brief", text)
        self.assertNotIn("## Interfaces", text)
        self.assertIn("## Commits", text)

    def test_usage_with_too_many_args(self):
        r = run_script("review-package", ["a", "b", "c", "d", "e", "f"],
                       cwd=str(self.repo), env_extra={})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()