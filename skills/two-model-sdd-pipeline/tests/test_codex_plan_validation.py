"""Controller-owned R3.1 strict canonical plan validation tests."""
import importlib.util
import pathlib
import tempfile
import unittest
import copy

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"


def load(test):
    path = SCRIPTS / "plan_validation.py"
    test.assertTrue(path.is_file(), "R3.1 requires scripts/plan_validation.py")
    spec = importlib.util.spec_from_file_location("r31_plan_validation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    test.assertTrue(callable(getattr(module, "validate_plan", None)))
    return module


def valid_plan():
    return {"version": 1, "title": "Example", "spec_doc": "docs/spec.md",
        "global_constraints": ["Preserve evidence"], "interfaces": {},
        "verification": {"toolchains": [{"id": "python", "language": "python",
            "test": {"argv": ["python", "-m", "unittest"], "cwd": "."}}],
            "new_test_files": ["tests/test_new.py"]},
        "tasks": [{"id": 1, "title": "First task", "summary": "Do work",
            "spec_refs": ["docs/spec.md#Contract"], "touches": ["src/a.py"],
            "depends_on": [], "acceptance": ["Output is valid"],
            "interfaces": {"produces": [], "consumes": []},
            "verification": {"new_test_files": ["tests/test_new.py"]},
            "extension": {"non_authoritative": "preserved"}}]}


class PlanValidationTests(unittest.TestCase):
    def test_valid_plan_preserves_non_authoritative_extensions(self):
        validator = load(self)
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / "docs").mkdir()
            (root / "docs" / "spec.md").write_text("# Contract\nDetails\n", encoding="utf-8")
            (root / "src").mkdir()
            plan = valid_plan()
            result = validator.validate_plan(plan, str(root))
            self.assertEqual(result["tasks"][0]["extension"], {"non_authoritative": "preserved"})

    def test_rejects_duplicate_or_nonconsecutive_ids_and_dependency_cycles(self):
        validator = load(self)
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / "docs").mkdir()
            (root / "docs" / "spec.md").write_text("# Contract\n", encoding="utf-8")
            plan = valid_plan()
            plan["tasks"].append({**copy.deepcopy(plan["tasks"][0]), "id": 3, "depends_on": [1]})
            with self.assertRaises(ValueError):
                validator.validate_plan(plan, str(root))

    def test_validates_actual_canonical_plan_and_requires_task_contract_fields(self):
        validator = load(self)
        canonical_path = ROOT / "docs" / "superpowers" / "plans" / "2026-09-25-r3-pipeline-integration" / "plan.json"
        result = validator.validate_plan(__import__("json").loads(canonical_path.read_text(encoding="utf-8")), str(ROOT))
        self.assertEqual(result["round_id"], "R3")
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / "docs").mkdir()
            (root / "docs" / "spec.md").write_text("# Contract\n", encoding="utf-8")
            for field in ("interfaces", "verification"):
                plan = valid_plan()
                del plan["tasks"][0][field]
                with self.subTest(field=field), self.assertRaises(ValueError):
                    validator.validate_plan(plan, str(root))
            plan = valid_plan()
            plan["tasks"][0]["depends_on"] = [1]
            with self.assertRaises(ValueError):
                validator.validate_plan(plan, str(root))

    def test_rejects_multi_task_dependency_cycle(self):
        validator=load(self)
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp); (root/"docs").mkdir()
            (root/"docs"/"spec.md").write_text("# Contract\n",encoding="utf-8")
            plan=valid_plan(); first=plan["tasks"][0]; first["depends_on"]=[2]
            second=copy.deepcopy(first); second.update(id=2,title="Second",depends_on=[1])
            plan["tasks"].append(second)
            with self.assertRaisesRegex(ValueError,"cycle"):
                validator.validate_plan(plan,str(root))

    def test_rejects_traversal_case_aliases_unsupported_runtime_controls_and_bad_anchors(self):
        validator = load(self)
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / "docs").mkdir()
            (root / "docs" / "spec.md").write_text("# Contract\n", encoding="utf-8")
            cases = []
            plan = valid_plan(); plan["tasks"][0]["touches"] = ["../outside.py"]; cases.append(plan)
            plan = valid_plan(); plan["tasks"][0]["touches"] = ["src/Foo.py", "src/foo.py"]; cases.append(plan)
            plan = valid_plan(); plan["runtime"] = {"force_approve": True}; cases.append(plan)
            plan = valid_plan(); plan["tasks"][0]["spec_refs"] = ["docs/spec.md#Missing"]; cases.append(plan)
            for candidate in cases:
                with self.subTest(candidate=candidate):
                    with self.assertRaises(ValueError):
                        validator.validate_plan(candidate, str(root))
