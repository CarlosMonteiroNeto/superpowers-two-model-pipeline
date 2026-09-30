import json
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
FINAL_GATE = ROOT / "skills/two-model-sdd-pipeline/scripts/final-gate"


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True).stdout.strip()


class FinalSuiteTests(unittest.TestCase):
    def _workspace(self, root, task_count=2, real_repo=False):
        if real_repo:
            git(root, "init", "-q")
            git(root, "config", "user.email", "test@example.invalid")
            git(root, "config", "user.name", "Test")
            (root / ".gitignore").write_text(".superpowers/\n", encoding="utf-8")
            git(root, "add", ".gitignore")
            git(root, "commit", "-qm", "fixture")
            candidate = git(root, "rev-parse", "HEAD")
        else:
            candidate = "abc1234"
        workspace = root / ".superpowers" / "workspace"
        workspace.mkdir(parents=True)
        toolchains = ["python", "flutter"][:task_count]
        (workspace / "plan.json").write_text(json.dumps({"tasks": [
            {"id": index + 1, "toolchain_id": value} for index, value in enumerate(toolchains)
        ]}), encoding="utf-8")
        entries = [{"type": "gate", "task": "-", "summary": "gate", "toolchain_id": value}
                   for value in toolchains]
        entries.extend({"type": "task_complete", "task": str(index + 1), "summary": "done"}
                       for index in range(task_count))
        entries.append({"type": "integrated", "task": str(task_count), "summary": "integrated", "commits": candidate})
        (workspace / "ledger.jsonl").write_text("".join(json.dumps(x) + "\n" for x in entries), encoding="utf-8")
        return workspace

    def _fake_runner(self, root, exit_code):
        calls = root / "calls.txt"
        fake = root / "run-gates"
        fake.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" > '" + str(calls).replace("'", "'\\''") + "'\nexit " + str(exit_code) + "\n", encoding="utf-8")
        fake.chmod(0o755)
        return fake, calls

    def test_final_gate_reruns_mixed_configured_toolchains_after_cached_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            workspace = self._workspace(root, real_repo=True)
            fake, calls = self._fake_runner(root, 0)
            result = subprocess.run(["bash", str(FINAL_GATE), str(workspace), "2"], cwd=root,
                                    env=dict(os.environ, RUN_GATES_BIN=str(fake)), text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(calls.exists(), "closing must revalidate all toolchains even when a prior gate was green")
            self.assertIn("--tasks 1 2", calls.read_text(encoding="utf-8"))

    def test_final_gate_blocks_new_closing_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            root.mkdir(exist_ok=True)
            workspace = self._workspace(root, task_count=1)
            fake, _ = self._fake_runner(root, 1)
            result = subprocess.run(["bash", str(FINAL_GATE), str(workspace), "1"], cwd=root,
                                    env=dict(os.environ, RUN_GATES_BIN=str(fake)), text=True, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("one or more configured test/analyze commands failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
