"""Controller-owned candidate-bound director closing tests."""
import importlib.util
import hashlib
import json
import pathlib
import json
import unittest
import os
import tempfile
import subprocess
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"


def load(test):
    path = SCRIPTS / "codex_closing.py"
    test.assertTrue(path.is_file(), "R3.4 requires scripts/codex_closing.py")
    spec = importlib.util.spec_from_file_location("r34_codex_closing", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CodexClosingGateTests(unittest.TestCase):
    def test_closing_schema_defines_items_for_every_array(self):
        schema_path = ROOT / "skills" / "two-model-sdd-pipeline" / "schemas" / "closing-result.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        for name, descriptor in schema["properties"].items():
            if descriptor.get("type") == "array":
                with self.subTest(property=name):
                    self.assertIn("items", descriptor)

    def normalized(self, closing, snapshot, payload=None):
        import sys
        sys.path.insert(0,str(SCRIPTS))
        import dispatch_contract
        digest=hashlib.sha256(json.dumps(snapshot,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        request={"version":1,"backend":"codex","run_id":"run-a","dispatch_id":hashlib.sha256(("run-a\0closing\0"+digest).encode()).hexdigest()[:32],
            "task_id":1,"task_family":1,"episode_id":"run-a-closing-"+digest[:16],"role":"director","repository_id":"repo-a",
            "worktree":"C:/repo","plan_revision":snapshot["plan_hash"],"base_commit":snapshot["candidate_commit"],"config_hash":"e"*64,
            "prompt_hash":"f"*64,"requested_model":"gpt-6-luna","requested_effort":"medium",
            "evidence_paths":{"request_path":"a/request.json","prompt_path":"a/prompt.md","events_path":"a/events.jsonl","stderr_path":"a/stderr.log","final_path":"a/final.json","result_path":"a/result.json"}}
        payload=payload or {"verdict":"APPROVED","summary":"Complete","findings":[],"parked_minors":[],"proposed_tasks":[]}
        result={**{k:request[k] for k in ("version","backend","run_id","dispatch_id","task_id","task_family","role","episode_id","repository_id","worktree","plan_revision","base_commit","config_hash","requested_model","requested_effort")},
            "candidate_commit":snapshot["candidate_commit"],"runtime_version":"1","session_id":"thread-a","resumed_from":None,
            "process_exit":0,"terminal_status":"completed","output_schema":"closing-result-v1","final_output":payload,"usage":{"input_tokens":1,"cached_tokens":0,"output_tokens":1},"error":None}
        result["output_hash"]=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        return result, dispatch_contract.validate_request(request)

    def test_approval_is_bound_to_current_candidate_plan_spec_and_ledger(self):
        closing = load(self)
        snapshot = {"candidate_commit":"a"*40,"plan_hash":"b"*64,
            "spec_hash":"c"*64,"ledger_revision":"d"*64}
        result,request=self.normalized(closing,snapshot)
        self.assertEqual(closing.validate_closing_result(result,snapshot,request)["verdict"],"APPROVED")
        for key in snapshot:
            stale=dict(snapshot); stale[key]="e"*len(snapshot[key])
            with self.subTest(key=key), self.assertRaises(ValueError):
                closing.validate_closing_result(result,stale,request)

    def test_nonapproval_and_malformed_result_cannot_be_success(self):
        closing = load(self)
        snapshot = {"candidate_commit":"a"*40,"plan_hash":"b"*64,
            "spec_hash":"c"*64,"ledger_revision":"d"*64}
        payload={"verdict":"REOPEN","summary":"More work","findings":[],"parked_minors":[],"proposed_tasks":[]}
        result,request=self.normalized(closing,snapshot,payload)
        self.assertEqual(closing.validate_closing_result(result,snapshot,request)["verdict"],"REOPEN")
        for malformed in ({}, {**result,"candidate_commit":"f"*40},
                          {**result,"final_output":{**payload,"verdict":"BOGUS"}}):
            with self.subTest(malformed=malformed), self.assertRaises(ValueError):
                closing.validate_closing_result(malformed,snapshot,request)

    def test_final_gate_checks_recorded_base_range_not_origin_main(self):
        source=(SCRIPTS/"closing-gate").read_text(encoding="utf-8")
        self.assertIn("base_commit",source)
        self.assertIn("candidate_commit",source)
        self.assertNotIn("origin/main",source)

    def test_closing_result_path_stays_below_windows_max_path(self):
        closing=load(self)
        with tempfile.TemporaryDirectory(prefix="closing-path-") as temp:
            root=pathlib.Path(temp)/"repository with a long but realistic Windows path"
            root.mkdir()
            subprocess.run(["git","init","-q"],cwd=root,check=True)
            subprocess.run(["git","config","user.email","test@example.invalid"],cwd=root,check=True)
            subprocess.run(["git","config","user.name","Test"],cwd=root,check=True)
            (root/"tracked.txt").write_text("x",encoding="utf-8")
            subprocess.run(["git","add","-A"],cwd=root,check=True)
            subprocess.run(["git","commit","-qm","init"],cwd=root,check=True)
            ws=root/".superpowers"/"two-model"/"acceptance"; ws.mkdir(parents=True)
            (ws/".pipeline-identity.json").write_text(json.dumps({"run_id":"run-a","repository_id":"repo-a","repository_root":str(root)}),encoding="utf-8")
            prompt=ws/"closing.md"; prompt.write_text("close",encoding="utf-8")
            runtime=root/"runtime.json"; runtime.write_text(json.dumps({"attempt_root":str(root/".superpowers"/"attempts"),"manifest":{"backend":"codex","config_hash":"e"*64,"roles":{"director":{"model":"gpt-6-luna","settings":{"model_reasoning_effort":"medium"}}}}}),encoding="utf-8")
            snapshot={"candidate_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip(),"plan_hash":"a"*64,"spec_hash":"b"*64,"ledger_revision":"c"*64}
            request_path=ws/"closing-request.json"
            with mock.patch.dict(os.environ,{"CODEX_RUNTIME_JSON":str(runtime)}):
                request=closing.build_request(str(ws),str(prompt),snapshot,str(request_path))
            result_path=pathlib.Path(request["evidence_paths"]["result_path"])
            self.assertLess(len(str(result_path)+"."+"a"*32+".tmp"),260)
            self.assertIn("published",result_path.parts)


if __name__ == "__main__":
    unittest.main()
