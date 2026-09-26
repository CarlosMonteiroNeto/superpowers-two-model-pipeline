"""R2.1 acceptance tests for the command-scoped runner boundary."""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"
if os.name == "nt":
    _git_bash = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
    BASH = str(_git_bash) if _git_bash.exists() else "bash"
else:
    BASH = "bash"


class ScopedRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = pathlib.Path(tempfile.mkdtemp(prefix="scoped-run-ação com espaço-"))
        self.workspace = self.temp / "workspace"
        self.workspace.mkdir()
        self.sentinel = self.temp / "arbitrary-command-ran"

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def run_scoped(self, *args, env_extra=None):
        env = dict(os.environ)
        env["BASH_BIN"] = BASH
        env.update(env_extra or {})
        return subprocess.run(
            [BASH, str(SCRIPTS / "scoped-run"), str(self.workspace), *map(str, args)],
            capture_output=True, text=True, env=env, cwd=str(self.temp),
        )

    def test_runner_entrypoint_is_present(self):
        self.assertTrue(
            (SCRIPTS / "scoped-run").is_file(),
            "R2.1 requires scripts/scoped-run as the only worker test-command entrypoint",
        )

    def test_rejects_undeclared_mode_and_never_runs_supplied_command(self):
        self.assertTrue((SCRIPTS / "scoped-run").is_file(), "scoped-run entrypoint is missing")
        result = self.run_scoped(
            "9", "shell", "--", "python", "-c",
            "open(r'{}', 'w').write('executed')".format(self.sentinel),
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(
            any(word in (result.stdout + result.stderr).lower() for word in ("mode", "usage", "invalid")),
            result.stdout + result.stderr,
        )
        self.assertFalse(self.sentinel.exists(), "an undeclared mode must not execute caller-supplied commands")

    def test_rejects_extra_command_after_a_declared_mode(self):
        self.assertTrue((SCRIPTS / "scoped-run").is_file(), "scoped-run entrypoint is missing")
        result = self.run_scoped(
            "9", "test", "--", "python", "-c",
            "open(r'{}', 'w').write('executed')".format(self.sentinel),
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(
            any(word in (result.stdout + result.stderr).lower() for word in ("argument", "usage", "unexpected")),
            result.stdout + result.stderr,
        )
        self.assertFalse(self.sentinel.exists(), "scoped-run must not accept an arbitrary trailing command")

    def test_rejects_out_of_root_test_paths(self):
        self.assertTrue((SCRIPTS / "scoped-run").is_file(), "scoped-run entrypoint is missing")
        outside = pathlib.Path("..").joinpath("outside_test.py")
        result = self.run_scoped("9", "red", str(outside))
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(
            any(word in (result.stdout + result.stderr).lower() for word in ("path", "root", "canonical", "escape")),
            result.stdout + result.stderr,
        )

    def test_unittest_runner_uses_declared_cwd_and_environment_and_writes_bound_evidence(self):
        project = self.temp / "project with space-ação"
        tests = project / "tests"
        tests.mkdir(parents=True)
        marker = project / "runner marker.txt"
        (tests / "test_acceptance.py").write_text(
            "import os, pathlib, unittest\n"
            "class RunnerContract(unittest.TestCase):\n"
            "    def test_declared_context_then_fail(self):\n"
            "        self.assertTrue(os.path.samefile(pathlib.Path.cwd(), os.environ['EXPECTED_CWD']))\n"
            "        pathlib.Path(os.environ['RUNNER_MARKER']).write_text('executed', encoding='utf-8')\n"
            "        self.assertEqual('before', 'after')\n",
            encoding="utf-8",
        )
        command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
        descriptor = {
            "toolchain_id": "python-unit-v1",
            "language": "python",
            "executable": sys.executable,
            "project_root": str(project),
            "red_adapter": "unittest",
            "commands": {
                "red": {
                    "argv": command,
                    "cwd": ".",
                    "env": {"EXPECTED_CWD": str(project), "RUNNER_MARKER": str(marker)},
                },
                "test": {"argv": command, "cwd": ".", "env": {}},
            },
        }
        (self.workspace / "plan.json").write_text(json.dumps({
            "tasks": [{"id": 1, "title": "runner contract", "toolchain_id": "python-unit-v1",
                       "task_family_id": "family-1"}],
        }), encoding="utf-8")
        (self.workspace / "ledger.jsonl").write_text(json.dumps({
            "type": "gate", "toolchain_id": "python-unit-v1", "toolchain_descriptor": descriptor,
        }) + "\n", encoding="utf-8")

        result = self.run_scoped("1", "red", env_extra={"PIPELINE_ATTEMPT_ID": "attempt-1"})

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertTrue(marker.is_file(), result.stdout + result.stderr)
        self.assertEqual(marker.read_text(encoding="utf-8"), "executed")
        raw_output = self.workspace / "task-1-red-output.txt"
        self.assertIn("AssertionError", raw_output.read_text(encoding="utf-8"))
        evidence = json.loads((self.workspace / "task-1-red.txt").read_text(encoding="utf-8"))
        self.assertEqual(evidence["task_id"], 1)
        self.assertEqual(evidence["attempt_id"], "attempt-1")
        self.assertEqual(evidence["toolchain_id"], "python-unit-v1")
        self.assertTrue(evidence["source_snapshot"])
        self.assertEqual(len(evidence["executed_tests"]), 1)
        checked = subprocess.run(
            [sys.executable, str(SCRIPTS / "red-form-check"), str(self.workspace), "1", "unittest"],
            capture_output=True, text=True,
        )
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)


if __name__ == "__main__":
    unittest.main()
