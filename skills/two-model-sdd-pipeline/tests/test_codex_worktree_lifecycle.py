"""Controller-owned R3.1 durable worktree and writer ownership tests."""
import importlib.util
import pathlib
import json
import os
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"
BASH = (r"C:\Program Files\Git\bin\bash.exe" if os.name == "nt" else "bash")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
        capture_output=True, text=True)


def load(test, name, function):
    path = SCRIPTS / name
    test.assertTrue(path.is_file(), "R3.1 requires scripts/" + name)
    spec = importlib.util.spec_from_file_location("r31_" + name.replace(".", "_"), path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    test.assertTrue(callable(getattr(value, function, None)))
    return value


class WorktreeLifecycleTests(unittest.TestCase):
    def test_approved_canonical_noop_worktree_releases_from_owned_shard(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = pathlib.Path(temp) / "repo"
            repo.mkdir()
            git(repo, "init", "-q")
            git(repo, "config", "user.email", "test@example.invalid")
            git(repo, "config", "user.name", "test")
            (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
            git(repo, "add", "tracked.txt")
            git(repo, "commit", "-qm", "base")
            base = git(repo, "rev-parse", "HEAD").stdout.strip()
            ws = repo / ".superpowers" / "two-model" / "plan-a"
            (ws / "ownership").mkdir(parents=True)
            (ws / "plan.json").write_text("{}", encoding="utf-8")
            wt = repo / ".superpowers" / "two-model" / "worktrees" / "plan-key" / "run-1" / "task-1"
            wt.parent.mkdir(parents=True)
            branch = "codex/pipeline/plan-key/run-1/task-1"
            git(repo, "worktree", "add", "-q", str(wt), "-b", branch, base)
            owner = {"repository_root": str(repo), "workspace": str(ws), "worktree": str(wt),
                "branch": branch, "run_id": "run-1", "base": base, "task_id": 1}
            (ws / "ownership" / "task-1.json").write_text(json.dumps(owner), encoding="utf-8")
            (ws / "ledger.jsonl").write_text(json.dumps({"type":"worktree_alloc", "task":"1",
                "base":base, "branch":branch, "run_id":"run-1"}) + "\n", encoding="utf-8")
            shard = wt / ".superpowers" / "two-model" / "plan-a"
            shard.mkdir(parents=True)
            (shard / "ledger.jsonl").write_text(json.dumps({"type":"task_complete", "task":"1"}) + "\n", encoding="utf-8")
            result = subprocess.run([BASH, str(SCRIPTS / "worktree-release"), str(ws), "1"],
                cwd=repo, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(wt.exists())

    def test_release_rejects_persisted_worktree_from_another_run_namespace(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = pathlib.Path(temp) / "repo"
            repo.mkdir()
            git(repo, "init", "-q")
            git(repo, "config", "user.email", "test@example.invalid")
            git(repo, "config", "user.name", "test")
            (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
            git(repo, "add", "tracked.txt")
            git(repo, "commit", "-qm", "base")
            base = git(repo, "rev-parse", "HEAD").stdout.strip()
            ws = repo / ".superpowers" / "two-model" / "plan-a"
            (ws / "ownership").mkdir(parents=True)
            (ws / "plan.json").write_text("{}", encoding="utf-8")
            identity_module = load(self, "run_identity.py", "create_identity")
            plan_path = repo / "plans" / "plan-a.json"
            plan_path.parent.mkdir()
            plan_path.write_text("{}", encoding="utf-8")
            identity = identity_module.create_identity(str(repo), str(plan_path), "run-1")
            (ws / ".pipeline-identity.json").write_text(json.dumps(identity), encoding="utf-8")
            run1 = identity["run_id"]
            path1 = repo / ".superpowers" / "two-model" / "worktrees" / identity["workspace_key"] / run1 / "task-1"
            path1.parent.mkdir(parents=True)
            branch1 = "codex/pipeline/{}/{}/task-1".format(identity["workspace_key"], run1)
            git(repo, "worktree", "add", "-q", str(path1), "-b", branch1, base)
            identity2 = identity_module.create_identity(str(repo), str(plan_path), "run-2")
            path2 = repo / ".superpowers" / "two-model" / "worktrees" / identity2["workspace_key"] / "run-2" / "task-2"
            path2.parent.mkdir(parents=True)
            branch2 = "codex/pipeline/{}/run-2/task-2".format(identity2["workspace_key"])
            git(repo, "worktree", "add", "-q", str(path2), "-b", branch2, base)
            owner = {"repository_root": str(repo), "workspace": str(ws), "worktree": str(path2),
                "branch": branch2, "run_id": "run-2", "base": base, "task_id": 1}
            (ws / "ownership" / "task-1.json").write_text(json.dumps(owner), encoding="utf-8")
            (ws / "ledger.jsonl").write_text(json.dumps({"type":"worktree_alloc", "task":"1",
                "base":base, "branch":branch1, "run_id":run1}) + "\n", encoding="utf-8")
            shard = path2 / ".superpowers" / "two-model" / "plan-a"
            shard.mkdir(parents=True)
            (shard / "ledger.jsonl").write_text(json.dumps({"type":"task_complete", "task":"1"}) + "\n", encoding="utf-8")
            result = subprocess.run([BASH, str(SCRIPTS / "worktree-release"), str(ws), "1"],
                cwd=repo, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(path2.exists(), "release must not remove another run's worktree")

    def test_state_lock_records_owner_and_blocks_conflicting_owner(self):
        locks = load(self, "state_lock.py", "acquire_lock")
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "integration.lock"
            owner = {"repository_id": "repo-a", "branch": "codex/pipeline/a", "run_id": "r1"}
            with locks.acquire_lock(str(path), owner):
                self.assertTrue(path.exists())
                with self.assertRaises((ValueError, RuntimeError)):
                    with locks.acquire_lock(str(path), {**owner, "run_id": "r2"}):
                        pass
            self.assertFalse(path.exists())

    def test_evidence_archive_is_manifest_bound_and_refuses_incomplete_or_dirty_export(self):
        archive = load(self, "evidence_archive.py", "export_family")
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp) / "run"
            root.mkdir()
            (root / "result.json").write_text('{"verdict":"APPROVED"}', encoding="utf-8")
            out = pathlib.Path(temp) / "family.tar.gz"
            manifest = {"run_id": "run-a", "family_id": 1, "files": ["result.json"], "stopped": True}
            result = archive.export_family(str(root), str(out), manifest)
            self.assertTrue(out.is_file())
            self.assertEqual(result["run_id"], "run-a")
            with self.assertRaises(ValueError):
                archive.export_family(str(root), str(pathlib.Path(temp) / "bad.tar.gz"), {**manifest, "stopped": False})
