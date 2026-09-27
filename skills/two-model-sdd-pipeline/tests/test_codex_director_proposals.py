"""Controller-owned R3.3 validation for semantic director proposals."""
import importlib.util
import pathlib
import json
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"


def load(test):
    path = SCRIPTS / "director_result.py"
    test.assertTrue(path.is_file(), "R3.3 requires scripts/director_result.py")
    spec = importlib.util.spec_from_file_location("r33_director_result", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    test.assertTrue(callable(getattr(module, "validate_proposal", None)))
    return module


def proposal():
    return {"mode": "correction", "decision": "propose", "reason": "close missing edge",
        "source_plan_hash": "a" * 64, "target_task": 1,
        "proposal": {"title": "Add guard", "summary": "Handle unsafe input",
            "acceptance": ["Unsafe input is rejected"], "touches": ["src/app.py"]}}


class DirectorProposalTests(unittest.TestCase):
    def test_accepts_only_matching_proposal_and_target(self):
        validator = load(self)
        expected = {"mode": "correction", "source_plan_hash": "a" * 64, "target_task": 1}
        result = validator.validate_proposal(proposal(), expected)
        self.assertEqual(result["target_task"], 1)

    def test_rejects_stale_plan_hash_and_unsupported_director_mutation(self):
        validator = load(self)
        expected = {"mode": "correction", "source_plan_hash": "b" * 64, "target_task": 1}
        with self.assertRaises(ValueError):
            validator.validate_proposal(proposal(), expected)
        malicious = proposal()
        malicious["proposal"]["run_command"] = "approve"
        with self.assertRaises(ValueError):
            validator.validate_proposal(malicious, {**expected, "source_plan_hash": "a" * 64})

    def test_rejects_unsupported_arbitration_fields(self):
        validator=load(self)
        value={"mode":"arbitration","decision":"amend","reason":"narrow acceptance",
            "source_plan_hash":"a"*64,"target_task":1,"proposal":{"field_changes":{"run_command":"approve"}}}
        with self.assertRaises(ValueError):
            validator.validate_proposal(value,{"mode":"arbitration","source_plan_hash":"a"*64,"target_task":1})

    def test_request_materializes_latest_full_plan_and_target_for_each_attempt(self):
        validator=load(self)
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp)/"repo"; root.mkdir()
            subprocess.run(["git","-C",str(root),"init","-q"],check=True)
            subprocess.run(["git","-C",str(root),"config","user.email","test@example.invalid"],check=True)
            subprocess.run(["git","-C",str(root),"config","user.name","test"],check=True)
            (root/"tracked.txt").write_text("x",encoding="utf-8")
            subprocess.run(["git","-C",str(root),"add","-A"],check=True)
            subprocess.run(["git","-C",str(root),"commit","-qm","init"],check=True)
            ws=root/".superpowers"/"workspace"; ws.mkdir(parents=True)
            plan={"tasks":[{"id":1,"title":"Parent","summary":"Root task","spec_refs":[],"touches":[],"depends_on":[],"acceptance":["Done"],"interfaces":{},"verification":{} }]}
            (ws/"plan.json").write_text(json.dumps(plan),encoding="utf-8")
            (ws/".pipeline-identity.json").write_text(json.dumps({"repository_root":str(root),"repository_id":"repo-id","run_id":"run-id"}),encoding="utf-8")
            prompt=root/"selected.md"; prompt.write_text("Plan path points to an earlier worker snapshot",encoding="utf-8")
            runtime=root/"runtime.json"; runtime.write_text(json.dumps({"manifest":{"backend":"codex","config_hash":"a"*64,"roles":{"director":{"model":"gpt-6-luna","settings":{"model_reasoning_effort":"medium"}}}}}),encoding="utf-8")
            request_path=ws/"request.json"
            with mock.patch.dict("os.environ",{"CODEX_RUNTIME_JSON":str(runtime)}):
                request=validator.build_request(str(ws),1,"correction",str(prompt),str(request_path))
            materialized=pathlib.Path(request["evidence_paths"]["prompt_path"]).read_text(encoding="utf-8")
            self.assertIn("supersedes any earlier plan path",materialized)
            self.assertIn("Current canonical plan snapshot",materialized)
            self.assertIn("Root task",materialized)
