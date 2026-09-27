"""Controller-owned R3.3 canonical plan transaction tests."""
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock
from concurrent.futures import ThreadPoolExecutor
import threading

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
        capture_output=True, text=True)


def load(test):
    path = SCRIPTS / "plan_transaction.py"
    test.assertTrue(path.is_file(), "R3.3 requires scripts/plan_transaction.py")
    spec = importlib.util.spec_from_file_location("r33_plan_transaction", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    test.assertTrue(callable(getattr(module, "apply_director_proposal", None)))
    return module


class PlanTransactionTests(unittest.TestCase):
    def test_validated_closing_reopen_creates_script_owned_followup_task(self):
        transaction=load(self)
        with tempfile.TemporaryDirectory() as temp:
            repo=pathlib.Path(temp)/"repo"; repo.mkdir(); git(repo,"init","-q")
            git(repo,"config","user.email","test@example.invalid"); git(repo,"config","user.name","test")
            (repo/"docs").mkdir(); (repo/"docs"/"spec.md").write_text("# Contract\n",encoding="utf-8")
            path=repo/"plan.json"; plan={"version":1,"title":"Fixture","spec_doc":"docs/spec.md","global_constraints":["Safe"],
                "tasks":[{"id":1,"title":"First","summary":"Existing","spec_refs":["docs/spec.md#Contract"],"touches":["src/a.py"],"depends_on":[],
                    "acceptance":["Works"],"interfaces":{"produces":[],"consumes":[]},"verification":{"new_test_files":["tests/test_a.py"]}}]}
            path.write_text(json.dumps(plan),encoding="utf-8"); git(repo,"add","-A"); git(repo,"commit","-qm","plan")
            source=hashlib.sha256(path.read_bytes()).hexdigest()
            closing={"verdict":"REOPEN","summary":"Add omitted coverage","findings":[],"parked_minors":[],
                "proposed_tasks":[{"title":"Add coverage","summary":"Cover omitted behavior","acceptance":["Behavior is verified"]}]}
            manifest={"repository_root":str(repo),"plan_path":str(path),"run_id":"run-a","ledger_path":str(repo/"ledger.jsonl")}
            result=transaction.apply_closing_reopen(closing,source,manifest)
            updated=json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(result["assigned_ids"],[2])
            self.assertEqual(updated["tasks"][1]["depends_on"],[1])
            self.assertEqual(updated["tasks"][1]["spec_refs"],["docs/spec.md#Contract"])

    def test_proposal_updates_and_commits_canonical_plan(self):
        transaction = load(self)
        with tempfile.TemporaryDirectory() as temp:
            repo = pathlib.Path(temp) / "repo"
            repo.mkdir(); git(repo, "init", "-q")
            git(repo, "config", "user.email", "test@example.invalid")
            git(repo, "config", "user.name", "test")
            (repo / "docs").mkdir(); (repo / "docs" / "spec.md").write_text("# Contract\n", encoding="utf-8")
            plan_path = repo / "plan.json"
            plan = {"version":1,"title":"Fixture","spec_doc":"docs/spec.md", "global_constraints":["Safe"],
                "tasks":[{"id":1,"title":"First","summary":"Existing","spec_refs":["docs/spec.md#Contract"],
                    "touches":["src/a.py"],"depends_on":[],"acceptance":["Works"],
                    "interfaces":{"produces":[],"consumes":[]},"verification":{"new_test_files":["tests/test_a.py"]}}]}
            plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
            git(repo, "add", "-A"); git(repo, "commit", "-qm", "plan")
            source_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()
            proposal = {"mode":"correction","decision":"propose","reason":"add missing case",
                "source_plan_hash":source_hash,"target_task":1,
                "proposal":{"title":"Second","summary":"Add missing case","acceptance":["Case passes"],"touches":["src/b.py"]}}
            manifest = {"repository_root":str(repo),"plan_path":str(plan_path),"run_id":"run-a",
                "task_family":1,"workspace":str(repo / ".superpowers" / "two-model" / "fixture"),
                "scope_paths":["src/b.py"],
                "ledger_path":str(repo / ".superpowers" / "two-model" / "fixture" / "ledger.jsonl")}
            result = transaction.apply_director_proposal(proposal, manifest)
            updated = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(result["assigned_ids"], [2])
            self.assertEqual(updated["tasks"][-1]["id"], 2)
            self.assertEqual(git(repo, "rev-parse", "HEAD").stdout.strip(), result["commit"])

    def test_replay_recovers_commit_when_ledger_append_was_interrupted(self):
        transaction = load(self)
        with tempfile.TemporaryDirectory() as temp:
            repo = pathlib.Path(temp) / "repo"
            repo.mkdir(); git(repo, "init", "-q")
            git(repo, "config", "user.email", "test@example.invalid"); git(repo, "config", "user.name", "test")
            (repo / "docs").mkdir(); (repo / "docs" / "spec.md").write_text("# Contract\n", encoding="utf-8")
            plan_path = repo / "plan.json"
            plan = {"version":1,"title":"Fixture","spec_doc":"docs/spec.md","global_constraints":["Safe"],
                "tasks":[{"id":1,"title":"First","summary":"Existing","spec_refs":["docs/spec.md#Contract"],
                    "touches":["src/a.py"],"depends_on":[],"acceptance":["Works"],
                    "interfaces":{"produces":[],"consumes":[]},"verification":{"new_test_files":["tests/test_a.py"]}}]}
            plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
            git(repo, "add", "-A"); git(repo, "commit", "-qm", "plan")
            source_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()
            proposal = {"mode":"correction","decision":"propose","reason":"add missing case",
                "source_plan_hash":source_hash,"target_task":1,
                "proposal":{"title":"Second","summary":"Add missing case","acceptance":["Case passes"],"touches":["src/b.py"]}}
            ledger = repo / ".superpowers" / "ledger.jsonl"
            manifest = {"repository_root":str(repo),"plan_path":str(plan_path),"run_id":"run-a",
                "scope_paths":["src/b.py"],"ledger_path":str(ledger)}
            with mock.patch.object(transaction, "_append_ledger", side_effect=OSError("simulated crash")):
                with self.assertRaises(OSError): transaction.apply_director_proposal(proposal, manifest)
            self.assertEqual(len(json.loads(plan_path.read_text(encoding="utf-8"))["tasks"]), 2)
            recovered = transaction.apply_director_proposal(proposal, manifest)
            self.assertTrue(recovered["recovered"])
            self.assertEqual(recovered["assigned_ids"], [2])
            events = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(events), 1)
            self.assertTrue(events[0]["recovered"])

    def test_concurrent_worker_proposals_cannot_reuse_stale_snapshot_or_duplicate_id(self):
        transaction=load(self)
        with tempfile.TemporaryDirectory() as temp:
            repo=pathlib.Path(temp)/"repo"; repo.mkdir(); git(repo,"init","-q")
            git(repo,"config","user.email","test@example.invalid"); git(repo,"config","user.name","test")
            (repo/"docs").mkdir(); (repo/"docs"/"spec.md").write_text("# Contract\n",encoding="utf-8")
            path=repo/"plan.json"
            plan={"version":1,"title":"Fixture","spec_doc":"docs/spec.md","global_constraints":["Safe"],
                "tasks":[{"id":1,"title":"First","summary":"Existing","spec_refs":["docs/spec.md#Contract"],"touches":["src/a.py"],
                    "depends_on":[],"acceptance":["Works"],"interfaces":{"produces":[],"consumes":[]},"verification":{"new_test_files":["tests/test_a.py"]}}]}
            path.write_text(json.dumps(plan),encoding="utf-8"); git(repo,"add","-A"); git(repo,"commit","-qm","plan")
            snapshot=hashlib.sha256(path.read_bytes()).hexdigest()
            manifest={"repository_root":str(repo),"plan_path":str(path),"run_id":"run-a","ledger_path":str(repo/"ledger.jsonl"),"scope_paths":["src/b.py","src/c.py"]}
            worker2=pathlib.Path(temp)/"worker-two"
            git(repo,"worktree","add","-q","--detach",str(worker2),"HEAD")
            def proposal(name,touch): return {"mode":"correction","decision":"propose","reason":name,"source_plan_hash":snapshot,"target_task":1,
                "proposal":{"title":name,"summary":"Correct issue","acceptance":["Case passes"],"touches":[touch]}}
            barrier=threading.Barrier(2)
            def dispatch(name,touch,worker):
                barrier.wait()
                local=dict(manifest,workspace=str(worker/".superpowers"),worker_worktree=str(worker))
                try: return transaction.apply_director_proposal(proposal(name,touch),local)
                except (ValueError,RuntimeError) as exc: return str(exc)
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes=[pool.submit(dispatch,"A","src/b.py",repo),pool.submit(dispatch,"B","src/c.py",worker2)]
                outcomes=[future.result() for future in outcomes]
            self.assertEqual(sum(isinstance(value,dict) for value in outcomes),1)
            transient=[value for value in outcomes if isinstance(value,str) and "integration state is owned" in value]
            stale=[value for value in outcomes if isinstance(value,str) and "stale source plan hash" in value]
            self.assertEqual(len(transient)+len(stale),1)
            if transient:
                with self.assertRaisesRegex(ValueError,"stale source plan hash"):
                    transaction.apply_director_proposal(proposal("retry","src/c.py"),manifest)
            self.assertEqual([t["id"] for t in json.loads(path.read_text(encoding="utf-8"))["tasks"]],[1,2])

    def test_correction_cannot_expand_beyond_reviewed_affected_paths(self):
        transaction=load(self)
        with tempfile.TemporaryDirectory() as temp:
            repo=pathlib.Path(temp)/"repo"; repo.mkdir(); git(repo,"init","-q")
            git(repo,"config","user.email","test@example.invalid"); git(repo,"config","user.name","test")
            (repo/"docs").mkdir(); (repo/"docs"/"spec.md").write_text("# Contract\n",encoding="utf-8")
            path=repo/"plan.json"; plan={"version":1,"title":"Fixture","spec_doc":"docs/spec.md","global_constraints":["Safe"],
                "tasks":[{"id":1,"title":"First","summary":"Existing","spec_refs":["docs/spec.md#Contract"],"touches":["src/a.py"],"depends_on":[],
                    "acceptance":["Works"],"interfaces":{"produces":[],"consumes":[]},"verification":{"new_test_files":["tests/test_a.py"]}}]}
            path.write_text(json.dumps(plan),encoding="utf-8"); git(repo,"add","-A"); git(repo,"commit","-qm","plan")
            proposal={"mode":"correction","decision":"propose","reason":"out of scope","source_plan_hash":hashlib.sha256(path.read_bytes()).hexdigest(),
                "target_task":1,"proposal":{"title":"Extra","summary":"Outside finding","acceptance":["Done"],"touches":["src/unrelated.py"]}}
            manifest={"repository_root":str(repo),"plan_path":str(path),"run_id":"run-a","ledger_path":str(repo/"ledger.jsonl"),"scope_paths":["src/reviewed.py"]}
            with self.assertRaisesRegex(ValueError,"reviewed affected paths"):
                transaction.apply_director_proposal(proposal,manifest)
            self.assertEqual(len(json.loads(path.read_text(encoding="utf-8"))["tasks"]),1)

    def test_stale_source_hash_leaves_plan_unchanged(self):
        transaction = load(self)
        with tempfile.TemporaryDirectory() as temp:
            repo = pathlib.Path(temp) / "repo"
            repo.mkdir(); git(repo, "init", "-q")
            git(repo, "config", "user.email", "test@example.invalid"); git(repo, "config", "user.name", "test")
            (repo / "docs").mkdir(); (repo / "docs" / "spec.md").write_text("# Contract\n", encoding="utf-8")
            plan_path = repo / "plan.json"
            plan = {"version":1,"title":"Fixture","spec_doc":"docs/spec.md","global_constraints":["Safe"],
                "tasks":[{"id":1,"title":"First","summary":"Existing","spec_refs":["docs/spec.md#Contract"],
                    "touches":["src/a.py"],"depends_on":[],"acceptance":["Works"],
                    "interfaces":{"produces":[],"consumes":[]},"verification":{"new_test_files":["tests/test_a.py"]}}]}
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            git(repo, "add", "-A"); git(repo, "commit", "-qm", "plan")
            manifest = {"repository_root":str(repo),"plan_path":str(plan_path),"run_id":"run-a",
                "task_family":1,"workspace":str(repo / ".superpowers" / "two-model" / "fixture"),
                "ledger_path":str(repo / ".superpowers" / "two-model" / "fixture" / "ledger.jsonl")}
            before = plan_path.read_bytes()
            stale = {"mode":"correction","decision":"propose","reason":"stale","source_plan_hash":"0"*64,
                "target_task":1,"proposal":{"title":"Second","summary":"x","acceptance":["ok"],"touches":[]}}
            with self.assertRaises(ValueError): transaction.apply_director_proposal(stale, manifest)
            self.assertEqual(plan_path.read_bytes(), before)
