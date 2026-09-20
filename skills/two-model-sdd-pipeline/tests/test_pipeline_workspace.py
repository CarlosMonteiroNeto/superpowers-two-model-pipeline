import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest


SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
if os.name == "nt":
    _git_bash = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
    BASH = str(_git_bash) if _git_bash.exists() else "bash"
else:
    BASH = "bash"


class PipelineWorkspacePathTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = pathlib.Path(tempfile.mkdtemp(prefix="pipeline-workspace-"))
        self.repo = self.temp_dir / "repo with spaces"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "test"], check=True)
        (self.repo / "README.md").write_text("test\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "base"], check=True)
        self.plan = self.repo / "docs" / "superpowers" / "plans" / "sample-plan.json"
        self.plan.parent.mkdir(parents=True)
        self.plan.write_text(json.dumps({"feature": "test", "tasks": []}), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_creates_workspace_when_git_reports_windows_toplevel_path(self):
        result = subprocess.run(
            [BASH, str(SCRIPTS / "pipeline-workspace"), str(self.plan)],
            cwd=self.repo,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        workspace = self.repo / ".superpowers" / "two-model" / "sample-plan"
        self.assertTrue(result.stdout.strip(), "workspace path was not printed")
        self.assertEqual(json.loads((workspace / "plan.json").read_text(encoding="utf-8"))["feature"], "test")


if __name__ == "__main__":
    unittest.main()
