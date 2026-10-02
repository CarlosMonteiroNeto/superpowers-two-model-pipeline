"""Task 6 RED: agent-autonomy integration across the new boundaries."""

import hashlib
import json
import os
import pathlib
import sys
import tempfile
import unittest


SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import scope_grants
import working_areas
import prepare_prompt


def make_repo():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="autonomy-"))
    root = tmp / "repo"
    for directory in ("src/a", "src/b"):
        (root / directory).mkdir(parents=True)
    (root / "src" / "a" / "x.py").write_text("x = 1\n", encoding="utf-8")
    (root / "src" / "b" / "y.py").write_text("y = 2\n", encoding="utf-8")
    (root / "src" / "a" / "x_test.py").write_text(
        "import unittest\n\n\nclass T(unittest.TestCase):\n"
        "    def test_x(self):\n        self.assertTrue(True)\n",
        encoding="utf-8")
    (root / "package-lock.json").write_text("{}\n", encoding="utf-8")
    return tmp, root


def context(**overrides):
    value = {
        "role_protocol": "ROLE-PROTOCOL-7",
        "authority": "AUTHORITY-ORDER-3",
        "task_acceptance": "TASK-ACCEPTANCE-11",
        "output_contract": "OUTPUT-CONTRACT-5",
        "budget_chars": 200000,
    }
    value.update(overrides)
    return value


def skills_for(role):
    return {"role": role, "skills": [{
        "id": "domain-test-skill", "revision": "sha256:domain-r1",
        "source_sha256": "sha256:domain-r1", "content": "DOMAIN-SKILL-9"}]}


TASKS = [
    {"id": 1, "working_areas": ["src/a"], "touches": []},
    {"id": 2, "working_areas": ["src/b"], "touches": []},
    {"id": 3, "working_areas": ["src/a"], "touches": []},
]


class AreaSchedulingIntegrationTests(unittest.TestCase):
    def test_disjoint_tasks_run_concurrently_overlapping_serializes(self):
        _tmp, root = make_repo()
        scopes = [working_areas.normalize(task, str(root)) for task in TASKS]
        self.assertFalse(
            working_areas.overlap(scopes[0], scopes[1], str(root)))
        self.assertTrue(
            working_areas.overlap(scopes[0], scopes[2], str(root)))
        registry = str(_tmp / "reservations.json")
        first = working_areas.reserve(
            registry, {"run_id": "run-1", "family_id": 1, "task_id": 1},
            scopes[0])
        second = working_areas.reserve(
            registry, {"run_id": "run-1", "family_id": 2, "task_id": 2},
            scopes[1])
        self.assertEqual(first["decision"], "granted")
        self.assertEqual(second["decision"], "granted")
        blocked = working_areas.reserve(
            registry, {"run_id": "run-1", "family_id": 3, "task_id": 3},
            scopes[2])
        self.assertEqual(blocked["decision"], "conflict")
        working_areas.release(
            registry, {"run_id": "run-1", "family_id": 1, "task_id": 1,
                       "completed": True})
        retry = working_areas.reserve(
            registry, {"run_id": "run-1", "family_id": 3, "task_id": 3},
            scopes[2])
        self.assertEqual(retry["decision"], "granted")

    def test_unlisted_added_file_reaches_gates_and_review(self):
        _tmp, root = make_repo()
        ownership = {"run_id": "run-1", "family_id": 1,
                     "repo_root": str(root), "allowed_roots": ["src"],
                     "scope": {"mode": "areas", "roots": ["src/a"],
                               "exact_paths": []}}
        created = root / "src" / "a" / "extra_helper.py"
        granted = scope_grants.reserve(
            {"path": "src/a/extra_helper.py", "kind": "new_file"}, ownership)
        self.assertEqual(granted["decision"], "grant")
        created.write_text("def extra():\n    return 1\n", encoding="utf-8")
        test_file = root / "src" / "a" / "extra_test.py"
        test_file.write_text(
            "import unittest\n\n\nclass T(unittest.TestCase):\n"
            "    def test_extra(self):\n        self.assertTrue(True)\n",
            encoding="utf-8")
        import scoped_runner
        policy = {
            "project_root": str(root),
            "evidence_dir": str(_tmp / "ev"),
            "scope": ownership["scope"], "protected_paths": [],
            "toolchains": {
                "py": {"adapter": "unittest",
                       "commands": {
                           "test": {"argv": ["python", "-m", "unittest",
                                             "discover"],
                                    "cwd": "."}}}}}
        resolved = scoped_runner.resolve_capability(
            {"mode": "test", "toolchain_id": "py",
             "paths": ["src/a/extra_test.py"]}, policy)
        self.assertTrue(any("extra_test" in part for part in resolved["argv"]))

    def test_all_roles_receive_recorded_adapted_instructions(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="autonomy-roles-"))
        hashes = {}
        for role, core in (("operator", "Operator core"),
                           ("reviewer", "Reviewer core"),
                           ("director", "Director core")):
            out = tmp / role
            out.mkdir()
            package = prepare_prompt.prepare(
                role, context(), skills_for(role),
                "BACKEND-POLICY-42", out)
            text = pathlib.Path(package["prompt_path"]).read_text(
                encoding="utf-8")
            self.assertIn(core, text)
            self.assertEqual(text.count("TASK-ACCEPTANCE-11"), 1)
            envelope = json.loads((out / "envelope.json").read_text(
                encoding="utf-8"))
            self.assertEqual(envelope["instruction_envelope_hash"],
                             package["instruction_envelope_hash"])
            hashes[role] = package["instruction_envelope_hash"]
        self.assertEqual(len(set(hashes.values())), 3)

    def test_protected_changes_fail_before_acceptance(self):
        _tmp, root = make_repo()
        ownership = {"run_id": "run-1", "family_id": 1,
                     "repo_root": str(root),
                     "allowed_roots": ["package-lock.json", ".git"],
                     "scope": {"mode": "areas", "roots": ["."],
                               "exact_paths": []}}
        blocked = scope_grants.reserve(
            {"path": "package-lock.json", "kind": "existing_file"}, ownership)
        self.assertEqual(blocked["decision"], "block")
        import scoped_runner
        policy = {
            "project_root": str(root),
            "evidence_dir": str(_tmp / "ev"),
            "scope": ownership["scope"], "protected_paths": [],
            "toolchains": {
                "py": {"adapter": "unittest",
                       "commands": {
                           "test": {"argv": ["python", "-m", "unittest"],
                                    "cwd": "."}}}}},
        with self.assertRaises(ValueError):
            scoped_runner.resolve_capability(
                {"mode": "test", "toolchain_id": "py",
                 "paths": ["package-lock.json"]}, policy)

    def test_old_plans_retain_exact_path_authority(self):
        _tmp, root = make_repo()
        old = working_areas.normalize(
            {"id": 1, "touches": ["src/a/x.py"]}, str(root))
        self.assertEqual(old["mode"], "legacy")
        same = working_areas.normalize(
            {"id": 2, "touches": ["src/a/x.py"]}, str(root))
        other = working_areas.normalize(
            {"id": 3, "touches": ["src/b/y.py"]}, str(root))
        self.assertTrue(working_areas.overlap(old, same, str(root)))
        self.assertFalse(working_areas.overlap(old, other, str(root)))

    def test_resume_replays_recorded_package_without_new_dispatches(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="autonomy-resume-"))
        first_dir, second_dir = tmp / "a", tmp / "b"
        first_dir.mkdir()
        second_dir.mkdir()
        first = prepare_prompt.prepare(
            "operator", context(), skills_for("operator"),
            "BACKEND-POLICY-42", first_dir)
        replay = prepare_prompt.prepare(
            "operator", context(), skills_for("operator"),
            "BACKEND-POLICY-42", second_dir)
        self.assertEqual(first["instruction_envelope_hash"],
                         replay["instruction_envelope_hash"])

    def test_correction_family_retains_reservation_until_integration(self):
        _tmp, root = make_repo()
        registry = str(_tmp / "reservations.json")
        scope_a = working_areas.normalize(TASKS[0], str(root))
        parent = working_areas.reserve(
            registry, {"run_id": "run-1", "family_id": 1, "task_id": 1},
            scope_a)
        self.assertEqual(parent["decision"], "granted")
        child = working_areas.reserve(
            registry, {"run_id": "run-1", "family_id": 1, "task_id": 4},
            scope_a)
        self.assertEqual(child["decision"], "granted")
        self.assertEqual(child["owner"]["task_id"], 4)
        outsider = working_areas.reserve(
            registry, {"run_id": "run-1", "family_id": 2, "task_id": 2},
            working_areas.normalize(TASKS[1], str(root)))
        self.assertEqual(outsider["decision"], "granted")
        clash = working_areas.reserve(
            registry, {"run_id": "run-1", "family_id": 5, "task_id": 5},
            scope_a)
        self.assertEqual(clash["decision"], "conflict")
        working_areas.release(
            registry, {"run_id": "run-1", "family_id": 1, "task_id": 4,
                       "completed": True})
        recovered = working_areas.reserve(
            registry, {"run_id": "run-1", "family_id": 5, "task_id": 5},
            scope_a)
        self.assertEqual(recovered["decision"], "granted")


if __name__ == "__main__":
    unittest.main()
