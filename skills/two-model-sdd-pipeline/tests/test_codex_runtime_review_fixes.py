"""Focused regression tests for R2.5 review correction round."""
import importlib.util
import pathlib
import os
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"


def load(filename):
    spec = importlib.util.spec_from_file_location("reviewfix_" + filename.replace(".", "_"), SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class ReviewFixTests(unittest.TestCase):
    def test_task_id_separates_persisted_sessions(self):
        sessions = load("codex_sessions.py")
        with tempfile.TemporaryDirectory() as d:
            common = {"backend":"codex", "run_id":"r", "task_family":5, "role":"operator",
                      "worktree":d, "requested_model":"m", "requested_effort":"medium", "config_hash":"a"*64}
            first = dict(common, task_id=1); second = dict(common, task_id=2)
            sessions.store_session(first, {"status":"completed", "session_id":"one"})
            sessions.store_session(second, {"status":"completed", "session_id":"two"})
            self.assertEqual(sessions.load_session(first)["session_id"], "one")
            self.assertEqual(sessions.load_session(second)["session_id"], "two")

    def test_dispatch_exposes_owned_process_and_keeps_failure_unresolved(self):
        dispatch = load("codex_dispatch.py")
        with tempfile.TemporaryDirectory() as d:
            request = {"version":1,"backend":"codex","run_id":"r","dispatch_id":"d","task_id":1,
                "task_family":1,"episode_id":"e","role":"operator","repository_id":"repo","worktree":d,
                "plan_revision":"p","base_commit":"a"*40,"config_hash":"b"*64,
                "prompt_hash":""}
            prompt=pathlib.Path(d)/"prompt.md"; prompt.write_text("prompt", encoding="utf-8")
            import hashlib
            request["prompt_hash"]=hashlib.sha256(b"prompt").hexdigest()
            request["evidence_paths"]={k:str(pathlib.Path(d)/v) for k,v in (("request_path","req.json"),("prompt_path","prompt.md"),("events_path","ev.jsonl"),("stderr_path","err.log"),("final_path","final.json"),("result_path","res.json"))}
            flags={k:True for k in ("hooks_enabled","hooks_trusted","sandbox_enforced","bash_hook_covered","apply_patch_hook_covered")}
            flags.update({k:[] for k in ("unhooked_mutating_tools","managed_policy_conflicts","inherited_instruction_conflicts")})
            runtime={"manifest":{"backend":"codex","version":"v","roles":{"operator":{"model":"m","settings":{"model_reasoning_effort":"medium"},"policy":"workspace-write"}}},
                "capabilities":flags,"developer_instructions":"i","executable":["fake"],"process_registry":[]}
            request["requested_model"]="m"; request["requested_effort"]="medium"
            def started_callback(argv,cwd,stdin_text,timeout,env,on_start):
                on_start({"pid":42,"start_identity":"verified"})
                raise RuntimeError("capture failed")
            with mock.patch.object(dispatch.codex_process,"run_owned",side_effect=started_callback):
                with self.assertRaisesRegex(RuntimeError,"capture failed"):
                    dispatch.run_dispatch(request,runtime)
            self.assertEqual(runtime["process_registry"],[{"pid":42,"start_identity":"verified"}])
            identity={k:request[k] for k in ("backend","run_id","task_id","task_family","role","worktree","requested_model","requested_effort","config_hash")}
            identity["session_dir"]=d
            record=dispatch.codex_sessions.load_session(identity)
            self.assertEqual(record["status"],"unresolved")

    def test_explicit_fresh_recovery_drops_old_id_and_records_context_reset(self):
        dispatch = load("codex_dispatch.py")
        with tempfile.TemporaryDirectory() as d:
            import hashlib, json, subprocess
            request={"version":1,"backend":"codex","run_id":"r","dispatch_id":"d","task_id":2,
                "task_family":1,"episode_id":"e","role":"operator","repository_id":"repo","worktree":d,
                "plan_revision":"p","base_commit":"a"*40,"config_hash":"b"*64,
                "requested_model":"m","requested_effort":"medium","prompt_hash":hashlib.sha256(b"prompt").hexdigest()}
            prompt=pathlib.Path(d)/"prompt.md"; prompt.write_text("prompt",encoding="utf-8")
            request["evidence_paths"]={k:str(pathlib.Path(d)/v) for k,v in (("request_path","req.json"),("prompt_path","prompt.md"),("events_path","ev.jsonl"),("stderr_path","err.log"),("final_path","final.json"),("result_path","res.json"))}
            flags={k:True for k in ("hooks_enabled","hooks_trusted","sandbox_enforced","bash_hook_covered","apply_patch_hook_covered")}
            flags.update({k:[] for k in ("unhooked_mutating_tools","managed_policy_conflicts","inherited_instruction_conflicts")})
            runtime={"manifest":{"backend":"codex","version":"v","roles":{"operator":{"model":"m","settings":{"model_reasoning_effort":"medium"},"policy":"workspace-write"}}},
                "capabilities":flags,"developer_instructions":"i","executable":["fake"],"resume":True,
                "resume_session_id":"orphan-id","recovery":{"fresh":True}}
            payload={"status":"DONE","summary":"ok","changed_files":[],"red_evidence":{"path":"red.txt","runner":"unit","exit_code":1},"concerns":[]}
            def fake_run(argv,cwd,stdin_text,timeout,env,on_start):
                self.assertNotIn("resume",argv)
                output=pathlib.Path(argv[argv.index("--output-last-message")+1]); output.write_text(json.dumps(payload),encoding="utf-8")
                on_start({"pid":9,"start_identity":"start"})
                stream='{"type":"thread.started","thread_id":"fresh-thread"}\n{"type":"turn.completed","usage":{"input_tokens":1,"cached_input_tokens":0,"output_tokens":2}}\n'
                return {"stdout":stream,"stderr":"","returncode":0}
            with mock.patch.object(dispatch.codex_process,"run_owned",side_effect=fake_run), \
                 mock.patch.object(dispatch.subprocess,"run",return_value=subprocess.CompletedProcess([],0,"c"*40+"\n","")):
                result=dispatch.run_dispatch(request,runtime)
            self.assertIsNone(result["resumed_from"])
            identity={k:request[k] for k in ("backend","run_id","task_id","task_family","role","worktree","requested_model","requested_effort","config_hash")}
            identity["session_dir"]=d
            saved=dispatch.codex_sessions.load_session(identity)
            self.assertTrue(saved["context_reset"])
            self.assertEqual(saved["session_id"],"fresh-thread")

    def test_codex_cleanup_is_task_scoped_and_preserves_active_records(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d); store=root/".superpowers"/"sessions"; store.mkdir(parents=True)
            expired="2000-01-01T00:00:00+00:00"
            for name,task,status in (("one",1,"completed"),("two",2,"completed"),("active",1,"active")):
                ev=root/("evidence-"+name); ev.mkdir()
                (store/(name+".json")).write_text(json.dumps({"identity":{"task_id":task},"status":status,
                    "completed_at":expired,"evidence_dir":str(ev)}),encoding="utf-8")
            bash=r"C:\Program Files\Git\bin\bash.exe"
            if not pathlib.Path(bash).exists(): bash="bash"
            result=subprocess.run([bash,str(SCRIPTS/"session-clean"),d,"1","--backend","codex"],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertFalse((store/"one.json").exists())
            self.assertTrue((store/"two.json").exists())
            self.assertTrue((store/"active.json").exists())
            self.assertFalse((root/"evidence-one").exists())
            self.assertTrue((root/"evidence-two").exists())


if __name__ == "__main__": unittest.main()
