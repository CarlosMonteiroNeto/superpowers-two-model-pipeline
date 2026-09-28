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
    def test_task_run_delegates_codex_review_to_orchestrator(self):
        task_run=(SCRIPTS / "task-run").read_text(encoding="utf-8")
        review_case=task_run.split("      REVIEW)",1)[1].split("      CORRECTIVE)",1)[0]
        self.assertIn('PIPELINE_BACKEND:-opencode',review_case)
        self.assertIn('continue',review_case)
        codex_branch=review_case.split('if [ "${PIPELINE_BACKEND:-opencode}" = codex ]',1)[1].split('fi',1)[0]
        self.assertNotIn('task-$n-reviewer.log',codex_branch)

    def test_task_run_refreshes_canonical_plan_from_repository_root(self):
        task_run=(SCRIPTS / "task-run").read_text(encoding="utf-8")
        refresh=task_run.split("refresh_plan()",1)[1].split("refresh_plan_strict()",1)[0]
        self.assertIn('cd "$repo_root"',refresh)
        self.assertIn('pipeline-workspace" --refresh "$canonical"',refresh)

    def test_generic_and_flutter_red_gates_pass_explicit_codex_backend_to_operator_dispatch(self):
        for gate in (SCRIPTS / "red-gate", ROOT / "skills" / "flutter-app-pipeline" / "scripts" / "red-gate"):
            with self.subTest(gate=gate.name), tempfile.TemporaryDirectory() as temp:
                ws = pathlib.Path(temp) / "workspace"; ws.mkdir()
                (ws / "plan.json").write_text(json.dumps({"tasks":[{"id":1,"toolchain_id":"go"}]}), encoding="utf-8")
                (ws / "ledger.jsonl").write_text(json.dumps({"type":"gate","task":"-","summary":"fixture",
                    "toolchain_id":"go","lang":"go","test_cmd":"go test ./...","analyze_cmd":"go vet ./..."}) + "\n", encoding="utf-8")
                (ws / "task-1-brief.md").write_text("operator brief", encoding="utf-8")
                args_log = pathlib.Path(temp) / "dispatch-args.txt"
                dispatch = pathlib.Path(temp) / "dispatch-retry.sh"
                dispatch.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" > "$ARGS_LOG"\nexit 0\n', encoding="utf-8")
                coder = pathlib.Path(temp) / "coder-gate.sh"
                coder.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
                if os.name != "nt": dispatch.chmod(0o755); coder.chmod(0o755)
                env = dict(os.environ, PIPELINE_BACKEND="codex", CODEX_RUNTIME_JSON="runtime.json",
                    DISPATCH_RETRY_BIN=str(dispatch), CODER_GATE_BIN=str(coder), ARGS_LOG=str(args_log))
                result = subprocess.run([BASH, str(gate), str(ws), "1"], env=env,
                    capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("--backend codex", args_log.read_text(encoding="utf-8"))

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
            (ws / "task-1-review-state.json").write_text(json.dumps({
                "status": "review_pending", "identity": {
                    "base_commit": base, "candidate_commit": candidate,
                },
            }), encoding="utf-8")
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
            self.assertNotIn("candidate/base binding changed", result.stderr,
                "matching candidate state must survive Windows stdout CRLF: " + result.stderr)
            self.assertIn("strict Codex review request", result.stderr)
            self.assertNotIn("no verdict in task 1 reviewer log", result.stderr)
