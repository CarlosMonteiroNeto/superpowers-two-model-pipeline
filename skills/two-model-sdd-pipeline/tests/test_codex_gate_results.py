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

    def test_codex_review_route_uses_normalized_candidate_request_not_legacy_log(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp) / "repo"
            root.mkdir()
            def git(*args):
                return subprocess.run(["git", "-C", str(root), *args], check=True,
                    capture_output=True, text=True)
            git("init", "-q"); git("config", "user.email", "test@example.invalid")
            git("config", "user.name", "test")
            (root / "code.txt").write_text("base\n", encoding="utf-8")
            git("add", "code.txt"); git("commit", "-qm", "base")
            base = git("rev-parse", "HEAD").stdout.strip()
            (root / "code.txt").write_text("candidate\n", encoding="utf-8")
            git("commit", "-qam", "candidate")
            candidate = git("rev-parse", "HEAD").stdout.strip()
            ws = root / ".superpowers" / "two-model" / "plan"
            ws.mkdir(parents=True)
            (root / ".superpowers" / "two-model" / ".gitignore").write_text("*\n", encoding="utf-8")
            (ws / "plan.json").write_text(json.dumps({"tasks":[{"id":1}]}), encoding="utf-8")
            (ws / "task-1-brief.md").write_text("brief", encoding="utf-8")
            (ws / ".pipeline-identity.json").write_text(json.dumps({"run_id":"run-a","repository_id":"repo-a"}), encoding="utf-8")
            (ws / "task-1-review-state.json").write_text(json.dumps({"base_commit":base,"candidate_commit":candidate}), encoding="utf-8")
            (ws / "ledger.jsonl").write_text("\n".join(json.dumps(e) for e in [
                {"type":"brief_ready","task":"1","summary":"ready"},
                {"type":"red_check","task":"1","summary":"red"},
                {"type":"commit","task":"1","summary":"committed"}]) + "\n", encoding="utf-8")
            runtime = root / "runtime.json"
            runtime.write_text(json.dumps({"manifest":{"backend":"codex"}}), encoding="utf-8")
            env = dict(os.environ, PIPELINE_BACKEND="codex", CODEX_RUNTIME_JSON=str(runtime))
            result = subprocess.run([BASH, str(SCRIPTS / "orchestrator"), str(ws), "1", "1"],
                cwd=root, env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue("candidate/base binding changed" in result.stderr or
                "strict Codex review request" in result.stderr,
                "state={} base={} candidate={} {}{}".format((ws / "task-1-review-state.json").read_text(encoding="utf-8"), base, candidate, result.stdout, result.stderr))
            self.assertNotIn("no verdict in task 1 reviewer log", result.stderr)
