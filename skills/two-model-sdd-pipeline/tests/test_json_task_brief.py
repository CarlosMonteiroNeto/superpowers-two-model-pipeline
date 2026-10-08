import importlib.util
import json
import pathlib
import subprocess
import tempfile
import unittest

path = pathlib.Path(__file__).resolve().parents[2] / "subagent-driven-development/scripts/json_task_brief.py"
spec = importlib.util.spec_from_file_location("json_task_brief", path)
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


class JsonTaskBriefTests(unittest.TestCase):
    def test_exact_task_and_all_shared_contracts_survive(self):
        task = {"id": 1, "title": "One", "steps": ["RED", "GREEN"], "files": {"modify": ["a.dart"]}}
        plan = {"global_constraints": ["No production writes"], "verification": {"argv": ["flutter", "test"]}, "custom_contract": {"locale": "pt-BR"}, "tasks": [task, {"id": 2}]}
        actual = json.loads(subject.extract(plan, "1"))
        self.assertEqual(actual, dict(plan, tasks=[task]))

    def test_missing_or_duplicate_ids_are_rejected(self):
        for tasks in ([], [{"id": 1}, {"id": "1"}]):
            with self.assertRaises(ValueError):
                subject.extract({"tasks": tasks}, "1")

    def test_shell_entrypoint_dispatches_json_and_preserves_markdown(self):
        script = path.parent / "task-brief"
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for name, content in (("plan.json", json.dumps({"tasks": [{"id": 1, "title": "One"}]})),
                                  ("plan.md", "# Plan\n## Task 1: One\nDo work.\n## Task 2: Two\nOther work.\n")):
                plan = root / name
                plan.write_text(content, encoding="utf-8")
                output = root / "brief.md"
                result = subprocess.run(["bash", str(script), str(plan), "1", str(output)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                actual = output.read_text(encoding="utf-8")
                if name.endswith("json"):
                    self.assertEqual(json.loads(actual)["tasks"][0]["id"], 1)
                else:
                    self.assertIn("Do work.", actual)
                    self.assertNotIn("Other work.", actual)


if __name__ == "__main__":
    unittest.main()
