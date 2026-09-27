"""Controller-owned R3.2 normalized operator outcomes and route tests."""
import json
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"
BASH = r"C:\Program Files\Git\bin\bash.exe" if os.name == "nt" else "bash"


class GateResultRoutingTests(unittest.TestCase):
    def route(self, status):
        with tempfile.TemporaryDirectory() as temp:
            ws = pathlib.Path(temp)
            (ws / "plan.json").write_text(json.dumps({"tasks": [{"id": 1}, {"id": 2}]}), encoding="utf-8")
            events = [
                {"type": "brief_ready", "task": "1"},
                {"type": "red_check", "task": "1"},
                {"type": "operator_result", "task": "1", "status": status,
                 "final_output": {"status": status, "summary": "fixture", "changed_files": [],
                    "red_evidence": {"path": "red.json", "runner": "python", "exit_code": 1},
                    "concerns": []}},
            ]
            (ws / "ledger.jsonl").write_text("".join(json.dumps(x) + "\n" for x in events), encoding="utf-8")
            return subprocess.run([BASH, str(SCRIPTS / "route-next"), str(ws), "1", "2"],
                capture_output=True, text=True)

    def test_test_defect_routes_to_arbitration_from_normalized_final_object(self):
        result = self.route("TEST_DEFECT")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "ARBITRATE 1")

    def test_blocked_operator_status_preserves_actionable_block(self):
        result = self.route("BLOCKED")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BLOCKED", result.stderr)
