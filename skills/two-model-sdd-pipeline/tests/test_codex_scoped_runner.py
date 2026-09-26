"""R2.1 acceptance tests for the command-scoped runner boundary."""

import os
import pathlib
import shutil
import subprocess
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

    def run_scoped(self, *args):
        return subprocess.run(
            [BASH, str(SCRIPTS / "scoped-run"), str(self.workspace), *map(str, args)],
            capture_output=True, text=True, env=dict(os.environ), cwd=str(self.temp),
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
        self.assertFalse(self.sentinel.exists(), "an undeclared mode must not execute caller-supplied commands")

    def test_rejects_extra_command_after_a_declared_mode(self):
        self.assertTrue((SCRIPTS / "scoped-run").is_file(), "scoped-run entrypoint is missing")
        result = self.run_scoped(
            "9", "test", "--", "python", "-c",
            "open(r'{}', 'w').write('executed')".format(self.sentinel),
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.sentinel.exists(), "scoped-run must not accept an arbitrary trailing command")

    def test_rejects_out_of_root_test_paths(self):
        self.assertTrue((SCRIPTS / "scoped-run").is_file(), "scoped-run entrypoint is missing")
        outside = pathlib.Path("..").joinpath("outside_test.py")
        result = self.run_scoped("9", "red", str(outside))
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn(str(outside), result.stdout + result.stderr,
                         "a noncanonical path must not be treated as an executable test path")


if __name__ == "__main__":
    unittest.main()
