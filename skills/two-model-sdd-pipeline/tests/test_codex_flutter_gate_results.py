"""Controller-owned R3.2 Flutter reviewer transport failure test."""
import json
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
GREEN = ROOT / "skills" / "flutter-app-pipeline" / "scripts" / "green-gate"
BASH = r"C:\Program Files\Git\bin\bash.exe" if os.name == "nt" else "bash"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
        capture_output=True, text=True)


class FlutterGateResultTests(unittest.TestCase):
    def test_reviewer_transport_failure_is_not_reported_as_green(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            repo = root / "repo"
            repo.mkdir()
            git(repo, "init", "-q")
            git(repo, "config", "user.email", "test@example.invalid")
            git(repo, "config", "user.name", "test")
            (repo / "src.txt").write_text("base\n", encoding="utf-8")
            git(repo, "add", "src.txt")
            git(repo, "commit", "-qm", "base")
            base = git(repo, "rev-parse", "HEAD").stdout.strip()
            (repo / "src.txt").write_text("candidate\n", encoding="utf-8")
            ws = root / "workspace"
            ws.mkdir()
            (ws / "task-1-brief.md").write_text("review this", encoding="utf-8")
            cmd = root / "cmd.sh"
            cmd.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            dispatch = root / "dispatch.sh"
            dispatch.write_text("#!/usr/bin/env bash\nexit 23\n", encoding="utf-8")
            if os.name != "nt":
                cmd.chmod(0o755); dispatch.chmod(0o755)
            env = dict(os.environ, CMD_BIN=str(cmd), DISPATCH_BIN=str(dispatch),
                FLUTTER_BIN="flutter-stub", GIT_BIN="git",
                REVIEW_PACKAGE_BIN=str(ROOT / "skills" / "two-model-sdd-pipeline" / "scripts" / "review-package"))
            result = subprocess.run([BASH, str(GREEN), "-w", str(ws), "-t", "1", "-b", base],
                cwd=repo, env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("review", (result.stdout + result.stderr).lower())
            self.assertNotEqual(git(repo, "rev-parse", "HEAD").stdout.strip(), base)

