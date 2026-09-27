"""Controller-owned R3.3 canonical plan transaction tests."""
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import tempfile
import unittest

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
                "task_family":1,"workspace":str(repo / ".superpowers" / "two-model" / "fixture")}
            result = transaction.apply_director_proposal(proposal, manifest)
            updated = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(result["assigned_ids"], [2])
            self.assertEqual(updated["tasks"][-1]["id"], 2)
            self.assertNotEqual(git(repo, "rev-parse", "HEAD").stdout.strip(), result.get("parent_commit"))

    def test_stale_source_hash_and_dependency_cycle_leave_plan_unchanged(self):
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
                "task_family":1,"workspace":str(repo / ".superpowers" / "two-model" / "fixture")}
            before = plan_path.read_bytes()
            stale = {"mode":"correction","decision":"propose","reason":"stale","source_plan_hash":"0"*64,
                "target_task":1,"proposal":{"title":"Second","summary":"x","acceptance":["ok"],"touches":[]}}
            with self.assertRaises(ValueError): transaction.apply_director_proposal(stale, manifest)
            self.assertEqual(plan_path.read_bytes(), before)
