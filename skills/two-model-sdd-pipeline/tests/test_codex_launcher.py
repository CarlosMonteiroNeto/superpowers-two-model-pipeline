"""Public Codex launcher contract and pinned run binding."""
import importlib.util
import pathlib
import subprocess
from unittest import mock
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[3]
SCRIPTS=ROOT/"skills"/"two-model-sdd-pipeline"/"scripts"
spec=importlib.util.spec_from_file_location("r3_codex_launcher",SCRIPTS/"codex_launcher.py")
launcher=importlib.util.module_from_spec(spec); spec.loader.exec_module(launcher)


class CodexLauncherTests(unittest.TestCase):
    def test_launcher_requires_a_named_integration_branch(self):
        with mock.patch.object(
                launcher.subprocess, "run",
                return_value=subprocess.CompletedProcess(
                    ["git"], 1, "", "detached")):
            with self.assertRaisesRegex(ValueError, "detached HEAD"):
                launcher._integration_branch(pathlib.Path("/repo"))

    def test_launcher_returns_the_named_integration_branch(self):
        with mock.patch.object(
                launcher.subprocess, "run",
                return_value=subprocess.CompletedProcess(
                    ["git"], 0, "codex/feature\n", "")):
            self.assertEqual(
                launcher._integration_branch(pathlib.Path("/repo")),
                "codex/feature")

    def test_public_shell_entrypoint_selects_codex_and_never_mentions_opencode(self):
        path=SCRIPTS/"run-codex-pipeline"
        self.assertTrue(path.is_file())
        help_result=subprocess.run(["bash",str(path),"--help"],capture_output=True,text=True)
        self.assertEqual(help_result.returncode,0,help_result.stderr)
        self.assertIn("--config",help_result.stdout)
        self.assertTrue((SCRIPTS/"run-codex-pipeline.ps1").is_file())

    def test_runtime_manifest_binds_the_minted_run_id(self):
        config={"plan_path":"plans/p.json","publication":"local","max_parallel":1,"dispatch_timeout_seconds":60}
        report={"manifest":{"bundle_hash":"a","role_hashes":{},"project_path":"/repo"},
            "roles":{"operator":{},"reviewer":{},"director":{}},"executable":{"path":"codex"}}
        runtime=launcher._compose_runtime(config,report,pathlib.Path("/repo"),pathlib.Path("/ws"),
            pathlib.Path("/manifest"),"run-123",True,"base","main")
        self.assertEqual(runtime["manifest"]["run_id"],"run-123")
        self.assertTrue(runtime["capabilities"]["hooks_trusted"])
        self.assertEqual(runtime["attempt_root"], str(pathlib.Path("/ws") / "attempts"))
        self.assertEqual(runtime["session_dir"], str(pathlib.Path("/ws") / "sessions"))
        self.assertEqual(runtime["process_registry_path"], str(pathlib.Path("/ws") / "run-control.json"))

    def test_runtime_wraps_windows_cmd_launcher_for_owned_process_start(self):
        config={"plan_path":"plans/p.json","publication":"local","max_parallel":1,"dispatch_timeout_seconds":60}
        report={"manifest":{"bundle_hash":"a","role_hashes":{},"project_path":"/repo"},
            "roles":{"operator":{},"reviewer":{},"director":{}},
            "executable":{"path":r"C:\\Tools With Spaces\\codex.cmd","kind":"shell-wrapper"}}
        runtime=launcher._compose_runtime(config,report,pathlib.Path("/repo"),pathlib.Path("/ws"),
            pathlib.Path("/manifest"),"run-123",True,"base","main")
        self.assertEqual(runtime["executable"], [
            __import__("os").environ.get("COMSPEC", "cmd.exe"),
            "/d","/s","/c",report["executable"]["path"]])


if __name__=="__main__": unittest.main()
