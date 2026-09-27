"""Controller-owned R3.1 durable worktree and writer ownership tests."""
import importlib.util
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"


def load(test, name, function):
    path = SCRIPTS / name
    test.assertTrue(path.is_file(), "R3.1 requires scripts/" + name)
    spec = importlib.util.spec_from_file_location("r31_" + name.replace(".", "_"), path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    test.assertTrue(callable(getattr(value, function, None)))
    return value


class WorktreeLifecycleTests(unittest.TestCase):
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

