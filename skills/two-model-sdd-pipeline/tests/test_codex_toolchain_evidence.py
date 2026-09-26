"""R2.1 acceptance tests for executable toolchains and attempt-bound RED evidence."""

import importlib.util
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


def load_module(testcase, filename, module_name, expected_function):
    path = SCRIPTS / filename
    testcase.assertTrue(path.is_file(), "R2.1 requires scripts/" + filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    testcase.assertIsNotNone(spec)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    testcase.assertTrue(callable(getattr(module, expected_function, None)))
    return module


class ToolchainEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = pathlib.Path(tempfile.mkdtemp(prefix="toolchain-ação com espaço-"))
        self.project = self.temp / "repo with espaço-ação"
        self.project.mkdir()

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def test_toolchain_descriptor_uses_argv_cwd_and_environment(self):
        module = load_module(self, "toolchain_contract.py", "toolchain_contract", "resolve_toolchain")
        test_argv = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]
        integration_argv = [sys.executable, "-m", "unittest", "discover", "-s", "integration"]
        runtime = {
            "toolchains": {
                "python-unittest": {
                    "executable": sys.executable,
                    "commands": {
                        "red": {"argv": test_argv, "cwd": ".", "env": {"PYTHONUTF8": "1"}},
                        "test": {"argv": test_argv, "cwd": ".", "env": {"PYTHONUTF8": "1"}},
                        "analyze": {"argv": [sys.executable, "-m", "compileall", "src"], "cwd": ".", "env": {}},
                    },
                    "red_adapter": "unittest",
                },
                "python-integration": {
                    "executable": sys.executable,
                    "commands": {
                        "red": {"argv": integration_argv, "cwd": ".", "env": {}},
                        "test": {"argv": integration_argv, "cwd": ".", "env": {}},
                    },
                    "red_adapter": "unittest",
                },
            },
        }
        resolved = module.resolve_toolchain(
            {"toolchain_id": "python-unittest", "touches": ["src/app.py"]},
            runtime,
            str(self.project),
        )
        self.assertIsInstance(resolved, dict)
        self.assertEqual(resolved["toolchain_id"], "python-unittest")
        self.assertEqual(resolved["commands"]["test"]["argv"], test_argv)
        self.assertEqual(pathlib.Path(resolved["commands"]["test"]["cwd"]), self.project)
        self.assertEqual(resolved["commands"]["test"]["env"]["PYTHONUTF8"], "1")
        self.assertEqual(resolved["red_adapter"], "unittest")
        self.assertEqual(
            module.resolve_toolchain(
                {"toolchain_id": "python-integration", "touches": ["tests/integration/test_api.py"]},
                runtime,
                str(self.project),
            )["commands"]["test"]["argv"],
            integration_argv,
            "same-language toolchains must resolve by exact task identity, not ledger order",
        )

    def test_empty_node_manifest_does_not_guess_npm_test_or_eslint(self):
        (self.project / "package.json").write_text(json.dumps({"name": "empty-scripts", "scripts": {}}), encoding="utf-8")
        workspace = self.temp / "workspace"
        workspace.mkdir()
        result = subprocess.run(
            [BASH, str(SCRIPTS / "resolve-toolchain"), str(workspace), str(self.project)],
            capture_output=True, text=True, cwd=str(self.temp), env=dict(os.environ),
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("npm test", result.stdout + result.stderr)
        self.assertNotIn("npx eslint", result.stdout + result.stderr)
        self.assertFalse((workspace / "ledger.jsonl").exists(),
                         "unsupported guessed commands must not become an approved gate record")

    def test_node_or_rust_without_a_tested_red_adapter_fails_preflight(self):
        module = load_module(self, "toolchain_contract.py", "toolchain_contract", "resolve_toolchain")
        runtime = {"toolchains": {"node": {"executable": shutil.which("node") or "node", "commands": {
            "test": {"argv": ["node", "--test"], "cwd": ".", "env": {}},
        }}}}
        try:
            result = module.resolve_toolchain({"toolchain_id": "node"}, runtime, str(self.project))
        except (OSError, ValueError):
            return
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("error") or result.get("available") is False,
                        "Node without an explicitly tested RED adapter must fail preflight")

    def test_unittest_red_requires_an_executed_failing_test_and_matching_attempt(self):
        module = load_module(self, "red_evidence.py", "red_evidence", "validate_evidence")
        evidence_path = self.temp / "attempt-red.json"
        expected = {
            "task_id": 8,
            "attempt_id": "attempt-4",
            "toolchain_id": "python-unittest",
            "runner": "scoped-run-v1",
            "command": [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            "source_snapshot": "commit:0123456789abcdef",
        }
        evidence = dict(expected)
        evidence.update({
            "adapter": "unittest",
            "exit_code": 1,
            "executed_tests": ["test_acceptance"],
            "failures": ["test_acceptance"],
            "errors": [],
        })
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        accepted = module.validate_evidence(str(evidence_path), expected)
        self.assertTrue(accepted["valid_red"], accepted)

        stale_expected = dict(expected, attempt_id="attempt-5")
        rejected = module.validate_evidence(str(evidence_path), stale_expected)
        self.assertFalse(rejected["valid_red"], rejected)

        collection_only = dict(evidence, executed_tests=[], failures=[], errors=["ImportError before test execution"])
        evidence_path.write_text(json.dumps(collection_only), encoding="utf-8")
        rejected = module.validate_evidence(str(evidence_path), expected)
        self.assertFalse(rejected["valid_red"], rejected)

    def test_red_form_check_accepts_valid_unittest_evidence_and_keeps_existing_adapters(self):
        workspace = self.temp / "red-workspace"
        workspace.mkdir()
        evidence = {
            "version": 1,
            "adapter": "unittest",
            "tests_run": 1,
            "failures": ["test_acceptance"],
            "errors": [],
            "tests": [{"id": "test_acceptance", "outcome": "failure"}],
        }
        (workspace / "task-1-red.txt").write_text(json.dumps(evidence), encoding="utf-8")
        unittest_red = subprocess.run(
            [sys.executable, str(SCRIPTS / "red-form-check"), str(workspace), "1", "unittest"],
            capture_output=True, text=True,
        )
        self.assertEqual(unittest_red.returncode, 0, unittest_red.stdout + unittest_red.stderr)

        collection = dict(evidence, tests_run=0, failures=[], errors=["collection error"], tests=[])
        (workspace / "task-1-red.txt").write_text(json.dumps(collection), encoding="utf-8")
        invalid_red = subprocess.run(
            [sys.executable, str(SCRIPTS / "red-form-check"), str(workspace), "1", "unittest"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(invalid_red.returncode, 0, invalid_red.stdout + invalid_red.stderr)

        (workspace / "task-2-red.txt").write_text(json.dumps({"tests": [{"outcome": "failed"}]}), encoding="utf-8")
        pytest_red = subprocess.run(
            [sys.executable, str(SCRIPTS / "red-form-check"), str(workspace), "2", "python"],
            capture_output=True, text=True,
        )
        self.assertEqual(pytest_red.returncode, 0, pytest_red.stdout + pytest_red.stderr)

        (workspace / "task-3-red.txt").write_text(
            '{"Test":"TestAccepts","Action":"run"}\n{"Test":"TestAccepts","Action":"fail"}\n',
            encoding="utf-8",
        )
        go_red = subprocess.run(
            [sys.executable, str(SCRIPTS / "red-form-check"), str(workspace), "3", "go"],
            capture_output=True, text=True,
        )
        self.assertEqual(go_red.returncode, 0, go_red.stdout + go_red.stderr)


if __name__ == "__main__":
    unittest.main()
