import json
import hashlib
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
FINAL_GATE = ROOT / "skills/two-model-sdd-pipeline/scripts/final-gate"
CLOSING_WAIVER = ROOT / "skills/two-model-sdd-pipeline/scripts/closing_waiver.py"
RUN_PIPELINE = ROOT / "skills/two-model-sdd-pipeline/scripts/run-pipeline"


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True).stdout.strip()


class FinalSuiteTests(unittest.TestCase):
    def _workspace(self, root, task_count=2, real_repo=False):
        if real_repo:
            git(root, "init", "-q")
            git(root, "config", "user.email", "test@example.invalid")
            git(root, "config", "user.name", "Test")
            (root / ".gitignore").write_text(".superpowers/\n", encoding="utf-8")
            git(root, "add", ".gitignore")
            git(root, "commit", "-qm", "fixture")
            candidate = git(root, "rev-parse", "HEAD")
        else:
            candidate = "abc1234"
        workspace = root / ".superpowers" / "workspace"
        workspace.mkdir(parents=True)
        toolchains = ["python", "flutter"][:task_count]
        (workspace / "plan.json").write_text(json.dumps({"tasks": [
            {"id": index + 1, "toolchain_id": value} for index, value in enumerate(toolchains)
        ]}), encoding="utf-8")
        entries = [{"type": "gate", "task": "-", "summary": "gate", "toolchain_id": value}
                   for value in toolchains]
        for entry in entries:
            entry["toolchain_descriptor"] = {"language":"python","red_adapter":"unittest","commands":{
                "test":{"argv":["python","-c","pass"],"cwd":str(root),"env":{}},
                "analyze":{"argv":["python","-c","pass"],"cwd":str(root),"env":{}},
                "format":{"argv":["python","-c","pass"],"cwd":str(root),"env":{}}}}
        entries.extend({"type": "task_complete", "task": str(index + 1), "summary": "done"}
                       for index in range(task_count))
        entries.append({"type": "integrated", "task": str(task_count), "summary": "integrated", "commits": candidate})
        (workspace / "ledger.jsonl").write_text("".join(json.dumps(x) + "\n" for x in entries), encoding="utf-8")
        return workspace

    def _fake_runner(self, root, exit_code):
        fake_root = root / ".superpowers" / "workspace"
        fake_root.mkdir(parents=True, exist_ok=True)
        calls = fake_root / "calls.txt"
        fake = fake_root / "run-gates"
        fake.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" > '" + str(calls).replace("'", "'\\''") + "'\nexit " + str(exit_code) + "\n", encoding="utf-8")
        fake.chmod(0o755)
        return fake, calls

    def test_final_gate_reruns_mixed_configured_toolchains_after_cached_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "repo"
            root.mkdir()
            workspace = self._workspace(root, real_repo=True)
            fake, calls = self._fake_runner(root, 0)
            result = subprocess.run(["bash", str(FINAL_GATE), str(workspace), "2"], cwd=root,
                                    env=dict(os.environ, RUN_GATES_BIN=str(fake)), text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(calls.exists(), "closing must revalidate all toolchains even when a prior gate was green")
            self.assertIn("--tasks 1 2", calls.read_text(encoding="utf-8"))

    def test_pipeline_does_not_refresh_or_publish_graphify_output(self):
        text = (ROOT / "skills/two-model-sdd-pipeline/scripts/run-pipeline").read_text(encoding="utf-8")
        self.assertNotIn("graph_publication.py", text)
        self.assertNotIn("graphify-out", text)
        closing = text.index('"$SCRIPT_DIR/closing-gate"')
        review = text.index('"$SCRIPT_DIR/review-package"', closing)
        publish = text.index('"$SCRIPT_DIR/publication.py"')
        self.assertLess(closing, review)
        self.assertLess(review, publish)

    def test_final_gate_blocks_new_closing_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            root.mkdir(exist_ok=True)
            workspace = self._workspace(root, task_count=1)
            fake, _ = self._fake_runner(root, 1)
            result = subprocess.run(["bash", str(FINAL_GATE), str(workspace), "1"], cwd=root,
                                    env=dict(os.environ, RUN_GATES_BIN=str(fake)), text=True, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("one or more configured test/analyze commands failed", result.stderr)

    def test_final_gate_accepts_exact_supervisor_approved_baseline_as_non_green(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            workspace = self._workspace(root, task_count=1, real_repo=True)
            baseline, current = self._evidence(root, inherited=True)
            self._approve(workspace, baseline, current)
            fake, calls = self._fake_runner(root, 1)
            ledger_hash = hashlib.sha256((workspace / "ledger.jsonl").read_bytes()).hexdigest()
            result = subprocess.run(["bash", str(FINAL_GATE), str(workspace), "1"], cwd=root,
                                    env=dict(os.environ, RUN_GATES_BIN=str(fake)), text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            status = json.loads((workspace / "supervisor/completion-status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["status"], "completed_with_waived_baseline")
            self.assertFalse(calls.exists(), "exact candidate evidence should be reused")
            self.assertEqual(hashlib.sha256((workspace / "ledger.jsonl").read_bytes()).hexdigest(), ledger_hash,
                             "waiver validation must leave the approved ledger revision unchanged")
            ledger = [json.loads(line) for line in (workspace / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertFalse(any(row.get("type") == "integration_failed" for row in ledger))

    def test_final_gate_rejects_new_failure_even_with_approval_event(self):
        self._assert_invalid_waiver_blocks("new")

    def test_final_gate_rejects_ambiguous_failure_even_with_approval_event(self):
        self._assert_invalid_waiver_blocks("ambiguous")

    def _assert_invalid_waiver_blocks(self, mode):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            workspace = self._workspace(root, task_count=1, real_repo=True)
            baseline, current = self._evidence(root, inherited=False)
            if mode == "ambiguous":
                current["environment_hash"] = "f" * 64
            self._approve(workspace, baseline, current, fabricate_approval=True)
            fake, _ = self._fake_runner(root, 1)
            result = subprocess.run(["bash", str(FINAL_GATE), str(workspace), "1"], cwd=root,
                                    env=dict(os.environ, RUN_GATES_BIN=str(fake)), text=True, capture_output=True)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertFalse((workspace / "supervisor/completion-status.json").exists())

    def _evidence(self, root, inherited):
        helper = root / ".superpowers/workspace/read-candidate.py"
        helper.write_text("import json,sys;sys.path.insert(0,sys.argv[1]);import gate_evidence;print(json.dumps(gate_evidence.create_workspace_manifest(sys.argv[2],['1'],'tasks')))\n", encoding="utf-8")
        result = subprocess.run(["bash","-c","python3 \"$1\" \"$2\" \"$3\"","bash",
                                 str(helper),str(ROOT / "skills/two-model-sdd-pipeline/scripts"),
                                 str(root / ".superpowers/workspace")],cwd=root,text=True,capture_output=True)
        if result.returncode: raise AssertionError(result.stdout+result.stderr)
        candidate_manifest = json.loads(result.stdout)
        identity = candidate_manifest["identity"]
        import sys
        sys.path.insert(0, str(ROOT / "skills/two-model-sdd-pipeline/scripts"))
        from toolchain_gate import _descriptor
        from suite_evidence import _hash as evidence_hash
        gate_rows = [json.loads(line) for line in (root / ".superpowers/workspace/ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        descriptor = _descriptor(next(row for row in gate_rows if row.get("type")=="gate"))
        baseline = {"source_hash":"a"*64,"environment_hash":"b"*64,"command_hash":"c"*64,
                    "suites":[{"id":"python","tests":["test_mod.test_case"],"failures":[
                        {"test":"test_mod.test_case","signature":"d"*64,"raw":"AssertionError: old"}],
                        "raw_result":{"status":"completed","exit_code":1}}]}
        current = json.loads(json.dumps(baseline))
        baseline["environment_hash"] = identity["environment_hash"]
        current["environment_hash"] = identity["environment_hash"]
        baseline["command_hash"] = evidence_hash({"python":descriptor})
        current["command_hash"] = baseline["command_hash"]
        current.update({"head_commit":identity["head_commit"],"tree_hash":identity["tree_hash"],
                        "config_hash":identity["config_hash"],"environment_hash":identity["environment_hash"],
                        "source_hash":hashlib.sha256(identity["tree_hash"].encode()).hexdigest(),
                        "impact_selection_hash":candidate_manifest["selection_hash"]})
        if not inherited:
            current["suites"][0]["failures"][0]["signature"] = "e"*64
            current["suites"][0]["failures"][0]["raw"] = "AssertionError: changed"
        state = pathlib.Path(root / ".superpowers/workspace/supervisor")
        state.mkdir(parents=True)
        (state / "baseline-evidence.json").write_text(json.dumps(baseline), encoding="utf-8")
        (state / "current-evidence.json").write_text(json.dumps(current), encoding="utf-8")
        return baseline, current

    def _approve(self, workspace, baseline, current, fabricate_approval=False):
        from pathlib import Path
        import sys
        sys.path.insert(0, str(ROOT / "skills/two-model-sdd-pipeline/scripts"))
        from baseline_failures import compare
        comparison = compare(baseline, current)
        comparison_hash = hashlib.sha256(json.dumps(comparison, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        ledger_path = workspace / "ledger.jsonl"
        impact_record = {"type":"impact_gate_evidence","task":"-","phase":"closing","gate_status":"FAIL",
            "candidate_commit":current["head_commit"],"tree_hash":current["tree_hash"],
            "config_hash":current["config_hash"],"environment_hash":current["environment_hash"],
            "impact_selection_hash":current["impact_selection_hash"]}
        with ledger_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(impact_record) + "\n")
        for phase, filename in (("baseline", "baseline-evidence.json"), ("closing", "current-evidence.json")):
            evidence_hash = hashlib.sha256((workspace / "supervisor" / filename).read_bytes()).hexdigest()
            with ledger_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"type":"suite_evidence","task":"-","phase":phase,"evidence_hash":evidence_hash}) + "\n")
        event = {"type":"baseline_waiver_approved","task":"-","actor":"user",
                 "approval_record":"approval-1","candidate_commit":git(workspace.parent.parent, "rev-parse", "HEAD"),
                 "comparison_hash":comparison_hash}
        if not fabricate_approval and comparison["status"] != "baseline_only":
            event["comparison_hash"] = comparison_hash
        with ledger_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event) + "\n")
        failure = comparison.get("inherited", [])[0] if comparison.get("inherited") else {"suite":"python","test":"test_mod.test_case","signature":"d"*64}
        waiver = {"approved_by":"user","approval_record":"approval-1","candidate_commit":event["candidate_commit"],
                  "source_hash":comparison["source_hash"],"environment_hash":comparison["environment_hash"],
                  "command_hash":comparison["command_hash"],"baseline_source_hash":comparison["baseline_source_hash"],
                  "failures":[{key:failure[key] for key in ("suite","test","signature")}]}
        (workspace / "supervisor/waiver.json").write_text(json.dumps(waiver), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
