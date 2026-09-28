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
    path = pathlib.Path(directory) / name
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    if os.name == "nt":
        subprocess.run([BASH, "-c", "chmod +x '{}'".format(path)], check=True)
    else:
        path.chmod(0o755)
    return str(path)


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

    def test_task_arg_inlines_brief(self):
        head = self._change_and_commit()
        (self.ws / "task-3-brief.md").write_text("# Task 3\n\nBuild the feature.\n", encoding="utf-8")
        out = self._tmp / "pkg.diff"
        r = run_script("review-package", [str(self.ws), self.base, head, str(out), "3"],
                       cwd=str(self.repo), env_extra={})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = out.read_text(encoding="utf-8")
        self.assertIn("## Task Brief", text)
        self.assertIn("Build the feature.", text)
        self.assertIn("## Commits", text)
        self.assertIn("## Diff", text)
        # order: brief before commits
        self.assertLess(text.index("## Task Brief"), text.index("## Commits"))

    def test_task_arg_tolerates_missing_brief(self):
        head = self._change_and_commit()
        out = self._tmp / "pkg.diff"
        r = run_script("review-package", [str(self.ws), self.base, head, str(out), "3"],
                       cwd=str(self.repo), env_extra={})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = out.read_text(encoding="utf-8")
        self.assertNotIn("## Task Brief", text)
        self.assertIn("## Commits", text)

    def test_task_package_contains_raw_gate_operator_and_protected_state_evidence(self):
        head = self._change_and_commit()
        task = {"id": 3, "title": "Evidence task", "verification": {"new_test_files": ["tests/test_app.py"]}}
        (self.ws / "plan.json").write_text(json.dumps({"tasks": [task]}), encoding="utf-8")
        dispatch_id = "a" * 32
        event = {"type": "operator_result", "task": "3", "dispatch_id": dispatch_id,
                 "status": "DONE", "final_output": {"status": "DONE", "summary": "Operator self-review: scope and tests checked."}}
        (self.ws / "ledger.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
        (self.ws / "task-3-red.txt").write_text('{"tests_run":1,"failures":["test_missing_behavior"]}\n', encoding="utf-8")
        (self.ws / "task-3-test.txt").write_text("1 passed in 0.01s\n", encoding="utf-8")
        evidence = self.repo / ".superpowers" / "codex"
        evidence.mkdir(parents=True)
        (evidence / (dispatch_id + ".json")).write_text(json.dumps({"final_output": event["final_output"]}), encoding="utf-8")
        (evidence / ("before-" + dispatch_id + ".json")).write_text('{"git_head":"a","protected_files":{"plan.json":{"exists":true}}}', encoding="utf-8")
        (evidence / ("after-" + dispatch_id + ".json")).write_text('{"git_head":"a","protected_files":{"plan.json":{"exists":true}}}', encoding="utf-8")
        (evidence / ("comparison-" + dispatch_id + ".json")).write_text('{"integrity_ok":true,"changed_protected_paths":[]}', encoding="utf-8")
        out = self._tmp / "pkg.diff"
        result = run_script("review-package", [str(self.ws), self.base, head, str(out), "3"],
                            cwd=str(self.repo), env_extra={})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        package = out.read_text(encoding="utf-8")
        for marker in ("Raw RED evidence", "test_missing_behavior", "Raw GREEN evidence",
                       "1 passed in 0.01s", "Operator self-review", "scope and tests checked",
                       "Protected state before", "Protected state after", "integrity_ok"):
            with self.subTest(marker=marker):
                self.assertIn(marker, package)

    def test_guidance_hook_failure_keeps_baseline_package_successful(self):
        head = self._change_and_commit()
        out = self._tmp / "pkg.diff"
        guidance = write_stub(self._tmp, "guidance-fails", "exit 19\n")
        r = run_script(
            "review-package", [str(self.ws), self.base, head, str(out), "3"],
            cwd=str(self.repo), env_extra={"REVIEW_GUIDANCE_BIN": guidance},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("optional review guidance unavailable", r.stderr)
        text = out.read_text(encoding="utf-8")
        self.assertIn("## Commits", text)
        self.assertIn("## Diff", text)

    def test_usage_with_too_many_args(self):
        r = run_script("review-package", ["a", "b", "c", "d", "e", "f"],
                       cwd=str(self.repo), env_extra={})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
