"""R2.1 acceptance tests for complete, deterministic worker context packages."""

import importlib.util
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"


def load_context_package(testcase):
    path = SCRIPTS / "context_package.py"
    testcase.assertTrue(
        path.is_file(),
        "R2.1 requires context_package.py with the documented build_context API",
    )
    spec = importlib.util.spec_from_file_location("context_package", path)
    testcase.assertIsNotNone(spec)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    testcase.assertTrue(callable(getattr(module, "build_context", None)))
    return module


class ContextPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = pathlib.Path(tempfile.mkdtemp(prefix="context-ação com espaço-"))
        self.worktree = self.temp / "projeto com espaço-ação"
        self.bundle = self.temp / "bundle pinned"
        (self.worktree / "docs").mkdir(parents=True)
        (self.bundle / "skills" / "test-driven-development").mkdir(parents=True)
        (self.worktree / "docs" / "design.md").write_text(
            "# Required behavior\nPreserve the approved task boundary.\n",
            encoding="utf-8",
        )
        (self.bundle / "skills" / "test-driven-development" / "SKILL.md").write_text(
            "# Test Driven Development\nWrite a failing test first.\n",
            encoding="utf-8",
        )

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp, ignore_errors=True)

    def inputs(self, backend="codex"):
        task = {
            "id": 7,
            "title": "Carry complete context",
            "summary": "Build a fresh role package from versioned inputs.",
            "spec_refs": ["docs/design.md#required-behavior"],
            "touches": ["src/ação.py"],
            "interfaces": {"produces": ["context_package.build_context"]},
            "verification": {
                "command": "python3 -m unittest discover -s tests",
                "new_test_files": ["tests/test_ação.py"],
            },
            "acceptance": ["The mandatory acceptance marker stays present."],
            "skills": ["test-driven-development"],
        }
        plan = {
            "spec_doc": "docs/design.md",
            "global_constraints": ["GLOBAL-CONSTRAINT-7: keep the supervisor authoritative."],
            "tasks": [task],
        }
        request = {
            "backend": backend,
            "role": "operator",
            "task_id": 7,
            "task_family_id": "family-7",
            "attempt_id": "attempt-2",
            "repository_root": str(self.worktree),
            "worktree": str(self.worktree),
            "bundle_revision": "bundle-r1-7",
            "bundle_hash": "sha256:bundle-7",
            "allowed_roots": [str(self.worktree)],
            "evidence_paths": {"red": str(self.worktree / ".evidence" / "attempt-2-red.json")},
            "context_budget_chars": 20000,
        }
        return request, plan

    def test_build_context_carries_full_task_and_pinned_provenance_for_both_backends(self):
        module = load_context_package(self)
        codex_request, plan = self.inputs("codex")
        opencode_request, _ = self.inputs("opencode")

        codex = module.build_context("operator", codex_request, plan, str(self.bundle))
        opencode = module.build_context("operator", opencode_request, plan, str(self.bundle))

        for package in (codex, opencode):
            self.assertIsInstance(package, dict)
            self.assertIn("prompt", package)
            self.assertIn("source_manifest", package)
            material = package["prompt"] + json.dumps(package["source_manifest"], ensure_ascii=False)
            for required in (
                "GLOBAL-CONSTRAINT-7",
                "Carry complete context",
                "context_package.build_context",
                "python3 -m unittest discover -s tests",
                "Preserve the approved task boundary.",
                "bundle-r1-7",
                "sha256:bundle-7",
                "family-7",
                "attempt-2",
                "attempt-2-red.json",
            ):
                self.assertIn(required, material)
            self.assertIn("GLOBAL-CONSTRAINT-7", package["prompt"])
            self.assertIn("The mandatory acceptance marker stays present.", package["prompt"])

    def test_context_is_deterministic_and_missing_spec_is_an_explicit_error(self):
        module = load_context_package(self)
        request, plan = self.inputs()
        first = module.build_context("reviewer", request, plan, str(self.bundle))
        second = module.build_context("reviewer", request, plan, str(self.bundle))
        self.assertEqual(first, second)

        missing_ref_plan = json.loads(json.dumps(plan))
        missing_ref_plan["tasks"][0]["spec_refs"] = ["docs/not-present.md#missing"]
        try:
            result = module.build_context("reviewer", request, missing_ref_plan, str(self.bundle))
        except (OSError, ValueError):
            return
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("error") or result.get("ok") is False,
                        "an unresolved mandatory spec reference must not disappear silently")

    def test_oversized_mandatory_context_is_rejected_instead_of_truncated(self):
        module = load_context_package(self)
        request, plan = self.inputs()
        request["context_budget_chars"] = 64
        try:
            result = module.build_context("operator", request, plan, str(self.bundle))
        except (OSError, ValueError):
            return
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("error") or result.get("ok") is False,
                        "mandatory context larger than the budget must produce an explicit error")

    def test_non_flutter_brief_uses_scoped_runner_and_quotes_unicode_paths(self):
        workspace = self.temp / "state with espaço-ação"
        workspace.mkdir()
        task = {
            "id": 3,
            "title": "Non Flutter task",
            "summary": "Run one Python test file.",
            "spec_refs": ["docs/design.md#required-behavior"],
            "touches": ["src/ação.py"],
            "depends_on": [],
            "acceptance": ["The task test runs from the project worktree."],
            "verification": {
                "new_test_files": ["tests/test ação.py"],
                "test_command": [sys.executable, "-m", "unittest", "tests.test_ação"],
            },
        }
        (workspace / "plan.json").write_text(json.dumps({"tasks": [task]}, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "brief-scaffold"), str(workspace), "3"],
            capture_output=True, text=True, env=dict(os.environ),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        brief = (workspace / "task-3-brief.md").read_text(encoding="utf-8")
        self.assertNotIn("flutter-app-pipeline", brief)
        runner_lines = [line.strip().replace("`", "") for line in brief.splitlines() if "scoped-run" in line]
        self.assertTrue(runner_lines, "the brief must invoke the shared scoped runner")
        red_line = next((line for line in runner_lines if "red" in line), runner_lines[0])
        tokens = shlex.split(red_line)
        self.assertIn(workspace.as_posix(), tokens)
        self.assertIn("tests/test ação.py", tokens)


if __name__ == "__main__":
    unittest.main()
