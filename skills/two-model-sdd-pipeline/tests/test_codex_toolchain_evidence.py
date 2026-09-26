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

    def test_explicitly_unavailable_toolchain_stays_unavailable_when_runtime_appears(self):
        module = load_module(self, "toolchain_contract.py", "toolchain_contract", "resolve_toolchain")
        runtime = {"toolchains": {"python-unavailable": {
            "available": False,
            "preflight_error": "executable was missing during resolution",
            "language": "python",
            "executable": sys.executable,
            "red_adapter": "unittest",
            "commands": {
                "red": {"argv": [sys.executable, "-m", "unittest"], "cwd": ".", "env": {}},
                "test": {"argv": [sys.executable, "-m", "unittest"], "cwd": ".", "env": {}},
            },
        }}}

        result = module.resolve_toolchain(
            {"toolchain_id": "python-unavailable"}, runtime, str(self.project),
        )

        self.assertFalse(result.get("available"), result)
        self.assertIn("unavailable", result.get("error", ""))

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
            "adapter": "unittest",
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

    def test_unittest_import_collection_error_is_not_an_executed_test(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            module = load_module(self, "scoped_runner.py", "scoped_runner", "_parse_unittest")
        finally:
            sys.path.pop(0)
        output = (
            "test_missing_module (unittest.loader._FailedTest.test_missing_module) ... ERROR\n"
            "\n======================================================================\n"
            "ERROR: test_missing_module (unittest.loader._FailedTest.test_missing_module)\n"
            "----------------------------------------------------------------------\n"
            "ImportError: Failed to import test module\n"
            "\nRan 1 test in 0.001s\n\nFAILED (errors=1)\n"
        )
        tests_run, executed, failures, errors = module._parse_unittest(output)
        self.assertEqual(tests_run, 1)
        self.assertEqual(executed, [], "a loader _FailedTest is collection failure, not an executed test")
        self.assertEqual(failures, [])
        self.assertEqual(errors, [])

    def test_red_form_check_accepts_bound_unittest_evidence_and_keeps_existing_adapters(self):
        workspace = self.temp / "red-workspace"
        workspace.mkdir()

        def write_bound(task, adapter, payload):
            identity = {
                "task_id": task,
                "attempt_id": "attempt-%s" % task,
                "toolchain_id": "fixture-%s" % adapter,
                "runner": "scoped-run-v1",
                "command": ["fixture-runner", adapter],
                "source_snapshot": "tree:fixture-%s" % task,
                "adapter": adapter,
            }
            (workspace / ("task-%s-attempt.json" % task)).write_text(
                json.dumps(identity), encoding="utf-8",
            )
            (workspace / ("task-%s-red.txt" % task)).write_text(
                json.dumps(dict(identity, **payload)), encoding="utf-8",
            )

        unittest_evidence = {
            "version": 1,
            "adapter": "unittest",
            "tests_run": 1,
            "executed_tests": ["test_acceptance"],
            "failures": ["test_acceptance"],
            "errors": [],
            "tests": [{"id": "test_acceptance", "outcome": "failure"}],
            "exit_code": 1,
        }
        write_bound(1, "unittest", unittest_evidence)
        unittest_red = subprocess.run(
            [sys.executable, str(SCRIPTS / "red-form-check"), str(workspace), "1", "unittest"],
            capture_output=True, text=True,
        )
        self.assertEqual(unittest_red.returncode, 0, unittest_red.stdout + unittest_red.stderr)

        # Toolchain descriptors keep the language semantic (`python`) while
        # selecting unittest as the tested RED adapter.
        python_unittest_red = subprocess.run(
            [sys.executable, str(SCRIPTS / "red-form-check"), str(workspace), "1", "python"],
            capture_output=True, text=True,
        )
        self.assertEqual(python_unittest_red.returncode, 0,
                         python_unittest_red.stdout + python_unittest_red.stderr)

        collection = dict(unittest_evidence, tests_run=0, executed_tests=[], failures=[],
                          errors=["collection error"], tests=[])
        write_bound(1, "unittest", collection)
        invalid_red = subprocess.run(
            [sys.executable, str(SCRIPTS / "red-form-check"), str(workspace), "1", "unittest"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(invalid_red.returncode, 0, invalid_red.stdout + invalid_red.stderr)

        pytest_output = json.dumps({"tests": [{"nodeid": "test_acceptance", "outcome": "failed"}]})
        write_bound(2, "pytest_json_report", {"adapter": "pytest_json_report", "raw_output": pytest_output})
        pytest_red = subprocess.run(
            [sys.executable, str(SCRIPTS / "red-form-check"), str(workspace), "2", "python"],
            capture_output=True, text=True,
        )
        self.assertEqual(pytest_red.returncode, 0, pytest_red.stdout + pytest_red.stderr)

        go_output = ('{"Test":"TestAccepts","Action":"run"}\n'
                     '{"Test":"TestAccepts","Action":"fail"}\n')
        write_bound(3, "go_test_json", {"adapter": "go_test_json", "raw_output": go_output})
        go_red = subprocess.run(
            [sys.executable, str(SCRIPTS / "red-form-check"), str(workspace), "3", "go"],
            capture_output=True, text=True,
        )
        self.assertEqual(go_red.returncode, 0, go_red.stdout + go_red.stderr)

    def test_red_form_check_rejects_adapter_that_differs_from_attempt_manifest(self):
        workspace = self.temp / "adapter-mismatch-workspace"
        workspace.mkdir()
        identity = {
            "task_id": 1,
            "attempt_id": "attempt-adapter-mismatch",
            "toolchain_id": "python-unittest",
            "runner": "scoped-run-v1",
            "command": [sys.executable, "-m", "unittest", "tests.test_acceptance"],
            "source_snapshot": "commit:0123456789abcdef",
            "adapter": "unittest",
        }
        (workspace / "task-1-attempt.json").write_text(json.dumps(identity), encoding="utf-8")
        mismatched = dict(identity)
        mismatched.update({
            "adapter": "pytest_json_report",
            "raw_output": json.dumps({"tests": [{"nodeid": "test_acceptance", "outcome": "failed"}]}),
        })
        (workspace / "task-1-red.txt").write_text(json.dumps(mismatched), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "red-form-check"), str(workspace), "1", "python"],
            capture_output=True, text=True,
        )

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("adapter", result.stderr.lower())

    def test_red_form_check_rejects_valid_but_unbound_legacy_red_evidence(self):
        workspace = self.temp / "unbound-legacy-red-workspace"
        workspace.mkdir()
        legacy_evidence = {
            "adapter": "unittest",
            "tests_run": 1,
            "executed_tests": ["test_acceptance"],
            "failures": ["test_acceptance"],
            "errors": [],
            "tests": [{"id": "test_acceptance", "outcome": "failure"}],
            "exit_code": 1,
        }
        (workspace / "task-1-red.txt").write_text(json.dumps(legacy_evidence), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "red-form-check"), str(workspace), "1", "unittest"],
            capture_output=True, text=True,
        )

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_red_form_check_rejects_unittest_collection_error_even_when_named_as_executed(self):
        workspace = self.temp / "strict-red-workspace"
        workspace.mkdir()
        identity = {
            "version": 1,
            "task_id": 1,
            "task_family_id": "family-1",
            "attempt_id": "attempt-9",
            "toolchain_id": "python-unittest",
            "runner": "scoped-run-v1",
            "command": [sys.executable, "-m", "unittest", "tests.test_acceptance"],
            "source_snapshot": "commit:fedcba9876543210",
            "adapter": "unittest",
        }
        (workspace / "task-1-attempt.json").write_text(json.dumps(identity), encoding="utf-8")
        failed_test = "test_missing_module (unittest.loader._FailedTest.test_missing_module)"
        evidence = dict(identity)
        evidence.update({
            "tests_run": 1,
            "executed_tests": [failed_test],
            "failures": [],
            "errors": [failed_test],
            "exit_code": 1,
        })
        (workspace / "task-1-red.txt").write_text(json.dumps(evidence), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "red-form-check"), str(workspace), "1", "unittest"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_red_form_check_requires_attempt_identity_when_runner_manifest_exists(self):
        workspace = self.temp / "unbound-red-workspace"
        workspace.mkdir()
        identity = {
            "version": 1,
            "task_id": 1,
            "task_family_id": "family-1",
            "attempt_id": "attempt-9",
            "toolchain_id": "python-unittest",
            "runner": "scoped-run-v1",
            "command": [sys.executable, "-m", "unittest", "tests.test_acceptance"],
            "source_snapshot": "commit:fedcba9876543210",
            "adapter": "unittest",
        }
        (workspace / "task-1-attempt.json").write_text(json.dumps(identity), encoding="utf-8")
        unbound = {
            "adapter": "unittest",
            "tests_run": 1,
            "executed_tests": ["test_acceptance"],
            "failures": ["test_acceptance"],
            "errors": [],
            "tests": [{"id": "test_acceptance", "outcome": "failure"}],
            "exit_code": 1,
        }
        (workspace / "task-1-red.txt").write_text(json.dumps(unbound), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "red-form-check"), str(workspace), "1", "unittest"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_red_form_check_does_not_accept_bound_unittest_failedtest_collection_error(self):
        workspace = self.temp / "bound-collection-workspace"
        workspace.mkdir()
        failed_test = "test_missing_module (unittest.loader._FailedTest.test_missing_module)"
        identity = {
            "task_id": 1,
            "attempt_id": "attempt-9",
            "toolchain_id": "python-unittest",
            "runner": "scoped-run-v1",
            "command": [sys.executable, "-m", "unittest", "tests.test_acceptance"],
            "source_snapshot": "commit:fedcba9876543210",
            "adapter": "unittest",
        }
        (workspace / "task-1-attempt.json").write_text(json.dumps(identity), encoding="utf-8")
        legacy_evidence = dict(identity, **{
            "adapter": "unittest",
            "tests_run": 1,
            "executed_tests": [failed_test],
            "failures": [],
            "errors": [failed_test],
            "tests": [{"id": failed_test, "outcome": "error"}],
            "exit_code": 1,
        })
        (workspace / "task-1-red.txt").write_text(json.dumps(legacy_evidence), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "red-form-check"), str(workspace), "1", "unittest"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
