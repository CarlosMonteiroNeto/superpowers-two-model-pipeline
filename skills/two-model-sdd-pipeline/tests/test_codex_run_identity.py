"""Controller-owned R3.1 tests for canonical run and plan identities."""
import importlib.util
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"


def module(test, name, function):
    path = SCRIPTS / name
    test.assertTrue(path.is_file(), "R3.1 requires scripts/" + name)
    spec = importlib.util.spec_from_file_location("r31_" + name.replace(".", "_"), path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    test.assertTrue(callable(getattr(value, function, None)))
    return value


class RunIdentityTests(unittest.TestCase):
    def test_same_basename_in_different_repositories_has_distinct_identity(self):
        identities = module(self, "run_identity.py", "create_identity")
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            repos = [root / "one", root / "two"]
            for repo in repos:
                (repo / "docs").mkdir(parents=True)
                (repo / "docs" / "plan.json").write_text("{}", encoding="utf-8")
            left = identities.create_identity(str(repos[0]), str(repos[0] / "docs" / "plan.json"), "run-1")
            right = identities.create_identity(str(repos[1]), str(repos[1] / "docs" / "plan.json"), "run-1")
            self.assertNotEqual(left, right)
            self.assertEqual(left["run_id"], right["run_id"])
            self.assertNotEqual(left["repository_id"], right["repository_id"])

    def test_plan_path_is_canonical_and_identity_is_stable_for_equivalent_paths(self):
        identities = module(self, "run_identity.py", "create_identity")
        with tempfile.TemporaryDirectory() as temp:
            repo = pathlib.Path(temp) / "repo with spaces"
            repo.mkdir()
            plan = repo / "plans" / "plan.json"
            plan.parent.mkdir()
            plan.write_text("{}", encoding="utf-8")
            first = identities.create_identity(str(repo), str(plan), "r")
            second = identities.create_identity(str(repo), str(plan.parent / "." / plan.name), "r")
            self.assertEqual(first, second)
            self.assertTrue(first["plan_path"].endswith("plans/plan.json"))

