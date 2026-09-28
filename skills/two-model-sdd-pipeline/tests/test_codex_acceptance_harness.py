"""R3.7 acceptance harness contract and evidence output."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"
TESTS = ROOT / "skills" / "two-model-sdd-pipeline" / "tests"
ENTRY = SCRIPTS / "codex-acceptance"


class CodexAcceptanceHarnessTests(unittest.TestCase):
    def test_live_role_result_requires_nonapproval_probe_semantics(self):
        sys.path.insert(0, str(SCRIPTS))
        import codex_acceptance
        reviewer = {"terminal_status": "completed", "final_output": {"verdict": "SEND_BACK"}}
        director = {"terminal_status": "completed", "final_output": {"verdict": "BLOCKED"}}
        self.assertEqual(codex_acceptance._validate_live_role_result("reviewer", reviewer), "SEND_BACK")
        self.assertEqual(codex_acceptance._validate_live_role_result("director", director), "BLOCKED")
        reviewer["final_output"]["verdict"] = "APPROVED"
        with self.assertRaisesRegex(ValueError, "expected SEND_BACK"):
            codex_acceptance._validate_live_role_result("reviewer", reviewer)

    def test_live_session_and_attempt_evidence_use_shallow_run_paths(self):
        sys.path.insert(0, str(SCRIPTS))
        import codex_acceptance
        with tempfile.TemporaryDirectory() as temp:
            run_dir = pathlib.Path(temp) / "run"
            workspace = run_dir / "live-project" / ".acceptance"
            runtime = codex_acceptance._bind_live_paths({}, run_dir, workspace)
            self.assertEqual(pathlib.Path(runtime["attempt_root"]), run_dir / "attempts")
            self.assertEqual(pathlib.Path(runtime["session_dir"]), run_dir / "sessions")

    def test_scenario_environment_does_not_inject_windows_pythonpath_into_git_bash(self):
        sys.path.insert(0, str(SCRIPTS))
        import codex_acceptance
        with mock.patch.dict("os.environ", {"PYTHONPATH": str(ROOT)}, clear=True):
            environment = codex_acceptance._scenario_environment()
        self.assertNotIn("PYTHONPATH", environment)

    def test_scenario_catalog_covers_the_round_lifecycle_with_existing_fixtures(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "codex_acceptance.py"), "--list-scenarios"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        catalog = json.loads(result.stdout)
        required = {
            "artifact_handoff_and_preflight",
            "operator_red_green_and_review",
            "director_correction_and_arbitration",
            "parallel_integration_and_recovery",
            "strict_closing_and_publication",
            "resume_cancellation_and_retention",
            "worker_policy_and_distribution",
        }
        self.assertEqual(set(catalog), required)
        self.assertIn("test_foundation_harness_install",
                      catalog["worker_policy_and_distribution"])
        self.assertIn("test_foundation_project_binding",
                      catalog["worker_policy_and_distribution"])
        for name, modules in catalog.items():
            with self.subTest(scenario=name):
                self.assertTrue(modules)
                for module in modules:
                    self.assertTrue((TESTS / (module + ".py")).is_file(), module)

    def test_offline_scenario_writes_raw_evidence_and_candidate_bound_report(self):
        self.assertTrue(ENTRY.is_file(), "R3.7 requires the codex-acceptance entrypoint")
        with tempfile.TemporaryDirectory() as temp:
            output = pathlib.Path(temp) / "acceptance"
            result = subprocess.run(
                ["bash", str(ENTRY), "--output", str(output),
                 "--scenario", "artifact_handoff_and_preflight"],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report_path = pathlib.Path(result.stdout.strip())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["mode"], "offline")
            self.assertEqual(report["candidate_commit"],
                             subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip())
            self.assertEqual(report["scenarios"][0]["name"], "artifact_handoff_and_preflight")
            self.assertEqual(report["scenarios"][0]["status"], "passed")
            log_path = report_path.parent / report["scenarios"][0]["log"]
            self.assertIn("Ran ", log_path.read_text(encoding="utf-8"))
            self.assertEqual(report["live_validation"], "not_run")

    def test_live_mode_requires_an_explicit_config(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "codex_acceptance.py"), "--live", "--output", "unused"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--config is required with --live", result.stderr)


if __name__ == "__main__":
    unittest.main()
