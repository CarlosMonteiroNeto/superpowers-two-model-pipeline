"""Validity tests for the benchmark fixture and its 10-task plan.

These are deterministic (no Flutter, no LLM): they assert the structural
properties the benchmark depends on -- 10 independent tasks, pairwise
disjoint touches, real stub files, resolvable spec refs -- and then validate
the plan against the engine's own ``brief-scaffold`` so it cannot be rejected
downstream.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

BENCH = pathlib.Path(__file__).resolve().parent.parent
FIXTURE = BENCH / "fixture"
PLAN = BENCH / "plans" / "2026-09-16-parallelism-benchmark-plan.json"
REPO = BENCH.parent
BRIEF_SCAFFOLD = REPO / "skills" / "two-model-sdd-pipeline" / "scripts" / "brief-scaffold"

REQUIRED_FIELDS = ("id", "title", "summary", "spec_refs", "touches",
                   "depends_on", "acceptance")


def is_test_path(path):
    normalized = path.replace("\\", "/")
    return "/test/" in normalized or normalized.startswith("test/")


class FixturePlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = json.loads(PLAN.read_text(encoding="utf-8"))
        cls.tasks = cls.plan["tasks"]

    def test_plan_declares_ten_tasks_numbered_one_to_ten(self):
        ids = sorted(task["id"] for task in self.tasks)
        self.assertEqual(ids, list(range(1, 11)))

    def test_every_task_has_the_required_fields(self):
        for task in self.tasks:
            for field in REQUIRED_FIELDS:
                self.assertIn(field, task, "task %s missing %s" % (task.get("id"), field))
            self.assertTrue(task["title"])
            self.assertTrue(task["summary"])
            self.assertTrue(task["acceptance"], "task %s has empty acceptance" % task["id"])
            self.assertTrue(task["spec_refs"], "task %s has empty spec_refs" % task["id"])
            self.assertTrue(task["touches"], "task %s has empty touches" % task["id"])

    def test_all_tasks_are_independent(self):
        for task in self.tasks:
            self.assertEqual(
                task["depends_on"], [],
                "task %s must have no predecessors so it is wave-ready" % task["id"],
            )

    def test_touches_are_pairwise_disjoint(self):
        seen = {}
        for task in self.tasks:
            for path in task["touches"]:
                self.assertNotIn(
                    path, seen,
                    "touch %s shared by tasks %s and %s" % (path, seen.get(path), task["id"]),
                )
                seen[path] = task["id"]

    def test_touches_are_implementation_paths_not_tests(self):
        for task in self.tasks:
            for path in task["touches"]:
                self.assertFalse(
                    is_test_path(path),
                    "task %s lists a test path in touches: %s" % (task["id"], path),
                )

    def test_touched_files_exist_and_are_stubs(self):
        for task in self.tasks:
            for path in task["touches"]:
                target = FIXTURE / path
                self.assertTrue(target.is_file(), "missing fixture file: %s" % path)
                text = target.read_text(encoding="utf-8")
                self.assertIn(
                    "UnimplementedError", text,
                    "fixture file %s is not an unimplemented stub" % path,
                )

    def test_spec_refs_resolve_in_the_fixture_spec(self):
        spec = (FIXTURE / "docs" / "spec.md").read_text(encoding="utf-8")
        for task in self.tasks:
            for ref in task["spec_refs"]:
                marker = ref.lstrip("#").strip()
                self.assertIn(
                    marker, spec,
                    "spec_ref %s of task %s not found in fixture spec" % (ref, task["id"]),
                )

    def test_fixture_pubspec_matches_package_name(self):
        pubspec = (FIXTURE / "pubspec.yaml").read_text(encoding="utf-8")
        self.assertIn("name: bench_fixture", pubspec)

    def test_fixture_ships_a_smoke_test(self):
        tests = list((FIXTURE / "test").glob("*_test.dart"))
        self.assertTrue(tests, "fixture needs at least one test so the suite loads")

    def test_fixture_gitignore_excludes_toolchain_artifacts(self):
        # Without this the gates' `git add -A` would stage .dart_tool/ and the
        # report files, and keep-discard would DISCARD every task as
        # out-of-scope.
        gitignore = (FIXTURE / ".gitignore").read_text(encoding="utf-8")
        for pattern in (".dart_tool/", "pubspec.lock", "green-gate-report.txt"):
            self.assertIn(pattern, gitignore)

    def test_plan_brief_scaffolds_every_task(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="bench-plan-"))
        try:
            ws = tmp / "ws"
            ws.mkdir()
            (ws / "plan.json").write_text(json.dumps(self.plan), encoding="utf-8")
            for task in self.tasks:
                result = subprocess.run(
                    [sys.executable, str(BRIEF_SCAFFOLD), str(ws), str(task["id"])],
                    capture_output=True, text=True,
                )
                self.assertEqual(
                    result.returncode, 0,
                    "brief-scaffold rejected task %s: %s" % (task["id"], result.stderr),
                )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
