"""Controller-owned R3.3 validation for semantic director proposals."""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"


def load(test):
    path = SCRIPTS / "director_result.py"
    test.assertTrue(path.is_file(), "R3.3 requires scripts/director_result.py")
    spec = importlib.util.spec_from_file_location("r33_director_result", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    test.assertTrue(callable(getattr(module, "validate_proposal", None)))
    return module


def proposal():
    return {"mode": "correction", "decision": "propose", "reason": "close missing edge",
        "source_plan_hash": "a" * 64, "target_task": 1,
        "proposal": {"title": "Add guard", "summary": "Handle unsafe input",
            "acceptance": ["Unsafe input is rejected"], "touches": ["src/app.py"]}}


class DirectorProposalTests(unittest.TestCase):
    def test_accepts_only_matching_proposal_and_target(self):
        validator = load(self)
        expected = {"mode": "correction", "source_plan_hash": "a" * 64, "target_task": 1}
        result = validator.validate_proposal(proposal(), expected)
        self.assertEqual(result["target_task"], 1)

    def test_rejects_stale_plan_hash_and_unsupported_director_mutation(self):
        validator = load(self)
        expected = {"mode": "correction", "source_plan_hash": "b" * 64, "target_task": 1}
        with self.assertRaises(ValueError):
            validator.validate_proposal(proposal(), expected)
        malicious = proposal()
        malicious["proposal"]["run_command"] = "approve"
        with self.assertRaises(ValueError):
            validator.validate_proposal(malicious, {**expected, "source_plan_hash": "a" * 64})

