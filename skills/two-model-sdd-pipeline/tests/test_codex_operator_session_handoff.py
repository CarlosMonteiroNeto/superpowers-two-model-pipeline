"""End-to-end proof that same-task Codex corrections resume the stored session."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_coder_gate import CoderGateTestBase, GO_TEST_FAILURE, run_script, write_stub

FAKE_CODEX = r'''import json, os, pathlib, sys
sys.stdin.read()
args = sys.argv[1:]
resume_id = args[args.index("resume") + 1] if "resume" in args else None
calls_path = pathlib.Path(os.environ["FAKE_CODEX_CALLS"])
calls_path.parent.mkdir(parents=True, exist_ok=True)
with calls_path.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({"argv": args, "resume_session_id": resume_id}) + "\n")
session_id = resume_id or "session-operator-1"
output_path = pathlib.Path(args[args.index("--output-last-message") + 1])
output_path.write_text(json.dumps({
    "status": "DONE",
    "summary": "Correction completed",
    "changed_files": ["file.txt"],
    "red_evidence": {"path": "task-1-red.txt", "runner": "go test -json", "exit_code": 1},
    "concerns": [],
}), encoding="utf-8")
print(json.dumps({"type": "thread.started", "thread_id": session_id}))
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 4}}))
'''


class OperatorSessionHandoffTests(CoderGateTestBase):
    def test_same_task_correction_resumes_persisted_operator_session(self):
        # Codex dispatch resolves the repository from the canonical pipeline workspace.
        self.ws = self.repo / ".superpowers" / "handoff-run"
        self.ws.mkdir(parents=True)
        exclude = self.repo / ".git" / "info" / "exclude"
        exclude.write_text(exclude.read_text(encoding="utf-8") + "\n.superpowers/\n", encoding="utf-8")
        self.ledger_path = self.ws / "ledger.jsonl"
        self.ledger_path.write_text(json.dumps({
            "ts": "2026-09-05T00:00:00Z", "type": "gate", "task": "-",
            "summary": "auto-detected: go (go.mod)", "test_cmd": "go test ./...",
            "analyze_cmd": "go vet ./...", "detected": "auto", "lang": "go",
        }) + "\n", encoding="utf-8")
        brief = self.brief()
        self.write_red_evidence(raw_output=GO_TEST_FAILURE)
        (self.repo / "file.txt").write_text("initial candidate\n", encoding="utf-8")
        (self.ws / "plan.json").write_text(json.dumps({"tasks": [{
            "id": 1,
            "title": "Correct the candidate",
            "summary": "Fix the failed gate result",
            "touches": ["file.txt"],
            "acceptance": ["the selected gate passes"],
            "depends_on": [],
            "verification": {},
        }]}), encoding="utf-8")
        (self.ws / ".pipeline-identity.json").write_text(json.dumps({
            "run_id": "run-f3-session-handoff",
            "repository_id": "repo-f3-session-handoff",
        }), encoding="utf-8")

        fake_codex = self.stub_dir / "fake-codex.py"
        fake_codex.write_text(FAKE_CODEX, encoding="utf-8")
        calls_path = self._tmp / "fake-codex-calls.jsonl"
        runtime_path = self._tmp / "runtime.json"
        runtime = {
            "manifest": {
                "backend": "codex",
                "version": "test-runtime",
                "config_hash": "c" * 64,
                "roles": {"operator": {
                    "model": "fake-model",
                    "settings": {"model_reasoning_effort": "medium"},
                    "policy": "workspace-write",
                    "instruction": "operator",
                }},
            },
            "capabilities": {
                "hooks_enabled": True,
                "hooks_trusted": True,
                "sandbox_enforced": True,
                "bash_hook_covered": True,
                "apply_patch_hook_covered": True,
                "unhooked_mutating_tools": [],
                "managed_policy_conflicts": [],
                "inherited_instruction_conflicts": [],
            },
            "developer_instructions": "test instructions",
            "role_instructions": {"operator": "Complete the requested correction."},
            "executable": [sys.executable, str(fake_codex)],
            "attempt_root": str(self._tmp / "attempts"),
            "session_dir": str(self.repo),
        }
        runtime_path.write_text(json.dumps(runtime), encoding="utf-8")
        common_env = {
            "CODEX_RUNTIME_JSON": str(runtime_path),
            "FAKE_CODEX_CALLS": str(calls_path),
            "PIPELINE_BACKEND": "codex",
            "RTK_ENABLED": "0",
        }

        initial = run_script(
            "dispatch-codex",
            ["--agent", "two-model-coder-go", "--task", "1",
             "--prompt-file", str(brief), "--log", str(self.ws / "task-1-coder.log")],
            cwd=self.repo,
            env_extra=common_env,
        )
        self.assertEqual(initial.returncode, 0, initial.stdout + initial.stderr)
        pointer = self.ws / "task-1-two-model-coder-go-session.txt"
        self.assertEqual(pointer.read_text(encoding="utf-8").strip(), "session-operator-1")

        gate_calls = self._tmp / "gate-calls.txt"
        gate = write_stub(self.stub_dir, "fail-once-gate", r'''
n=$(cat "$GATE_CALLS" 2>/dev/null || echo 0)
n=$((n + 1))
echo "$n" > "$GATE_CALLS"
if [ "$n" -eq 1 ]; then exit 1; fi
exit 0
''')
        corrected = run_script(
            "coder-gate", [str(self.ws), "1"],
            cwd=self.repo,
            env_extra=dict(common_env, RUN_GATES_BIN=gate, GATE_CALLS=str(gate_calls)),
        )

        self.assertEqual(corrected.returncode, 0, corrected.stdout + corrected.stderr)
        self.assertIn("ready for normalized Codex review", corrected.stdout)
        provider_calls = [json.loads(line) for line in calls_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(2, len(provider_calls), provider_calls)
        self.assertIsNone(provider_calls[0]["resume_session_id"])
        self.assertEqual("session-operator-1", provider_calls[1]["resume_session_id"])

        requests = []
        results = []
        for attempt in sorted((self._tmp / "attempts").glob("attempt-*")):
            request_path = attempt / "request.json"
            result_path = attempt / "result.json"
            if request_path.is_file() and result_path.is_file():
                requests.append(json.loads(request_path.read_text(encoding="utf-8")))
                results.append(json.loads(result_path.read_text(encoding="utf-8")))
        self.assertEqual(2, len(requests))
        identity_fields = ("run_id", "task_id", "task_family", "role", "worktree",
                           "requested_model", "requested_effort", "config_hash")
        self.assertEqual(
            {field: requests[0][field] for field in identity_fields},
            {field: requests[1][field] for field in identity_fields},
        )
        self.assertEqual("session-operator-1", results[1]["resumed_from"])

if __name__ == "__main__":
    import unittest
    unittest.main()




