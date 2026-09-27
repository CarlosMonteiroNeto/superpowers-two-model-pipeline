"""Public Codex launcher contract and pinned run binding."""
import importlib.util
import pathlib
import subprocess
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[3]
SCRIPTS=ROOT/"skills"/"two-model-sdd-pipeline"/"scripts"
spec=importlib.util.spec_from_file_location("r3_codex_launcher",SCRIPTS/"codex_launcher.py")
launcher=importlib.util.module_from_spec(spec); spec.loader.exec_module(launcher)


class CodexLauncherTests(unittest.TestCase):
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


if __name__=="__main__": unittest.main()
