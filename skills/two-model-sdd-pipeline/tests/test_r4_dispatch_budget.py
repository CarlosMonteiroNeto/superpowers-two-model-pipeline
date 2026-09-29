"""R4 black box checks for durable, identity-based coder dispatch budgets."""
import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"


def load_budget(testcase):
    path = SCRIPTS / "dispatch_budget.py"
    testcase.assertTrue(path.is_file(), "R4 requires the dispatch budget API")
    spec = importlib.util.spec_from_file_location("dispatch_budget", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    testcase.assertTrue(callable(getattr(module, "reserve", None)))
    return module


class DispatchBudgetTests(unittest.TestCase):
    def test_opencode_cycle_limits_can_be_set_before_run_and_then_freeze(self):
        budget = load_budget(self)
        with tempfile.TemporaryDirectory() as temp, mock.patch.dict(
                "os.environ", {"PIPELINE_CODER_CYCLE_LIMITS": "[2, 1, 1]"}):
            policy = budget.opencode_policy(temp)
            self.assertEqual(policy["cycle_allowances"], [2, 1, 1])
            state = {}
            identity = {"run_id": "run", "task_family": "one", "task_id": 1,
                        "role": "operator", "dispatch_id": "first"}
            budget.reserve(identity, policy, state=state)
            with self.assertRaises(ValueError):
                budget.reserve(dict(identity, dispatch_id="second"),
                               {"cycle_allowances": [5, 3, 3]}, state=state)

    def test_durable_reservation_requires_director_assessment_before_next_cycle(self):
        budget = load_budget(self)
        identity = {"run_id": "run", "task_family": "family-1", "task_id": 1,
                    "role": "operator", "dispatch_id": "dispatch-1"}
        policy = {"cycle_allowances": [1, 1, 1], "max_cycles": 3,
                  "require_assessment": True, "director_assessments": 0}
        with tempfile.TemporaryDirectory() as temp:
            path = str(pathlib.Path(temp) / "budget.json")
            first = budget.reserve(identity, policy, state_path=path)
            self.assertTrue(first["director_required"])
            self.assertEqual(budget.reserve(identity, policy, state_path=path), first)
            identity["dispatch_id"] = "dispatch-2"
            with self.assertRaises(RuntimeError):
                budget.reserve(identity, policy, state_path=path)
            policy["director_assessments"] = 1
            self.assertEqual(budget.reserve(identity, policy, state_path=path)["cycle"], 2)

    def test_confirmed_prestart_failure_releases_charge_but_records_transport(self):
        budget = load_budget(self)
        identity = {"run_id": "run", "task_family": "family-1", "task_id": 1,
                    "role": "operator", "dispatch_id": "dispatch-1"}
        policy = {"cycle_allowances": [1], "max_cycles": 1}
        state = {}
        budget.reserve(identity, policy, state=state)
        budget.record_prestart_failure(identity, state=state)
        identity["dispatch_id"] = "dispatch-2"
        result = budget.reserve(identity, policy, state=state)
        self.assertEqual(result["coder_invocations"], 1)
        self.assertEqual(result["transport_attempts"], 1)

    def test_three_configured_cycles_never_allow_a_twelfth_invocation(self):
        budget = load_budget(self)
        state = {}
        policy = {"cycle_allowances": [5, 3, 3], "max_cycles": 3,
                  "require_assessment": True, "director_assessments": 0}
        identity = {"run_id": "run", "task_family": "family-1", "task_id": 1,
                    "role": "operator", "dispatch_id": ""}
        for number in range(1, 12):
            identity["dispatch_id"] = "dispatch-%d" % number
            if number == 6:
                with self.assertRaises(RuntimeError):
                    budget.reserve(identity, policy, state=state)
                policy["director_assessments"] = 1
            if number == 9:
                with self.assertRaises(RuntimeError):
                    budget.reserve(identity, policy, state=state)
                policy["director_assessments"] = 2
            result = budget.reserve(identity, policy, state=state)
            self.assertEqual(result["coder_invocations"], number)
        self.assertEqual(result["cycle"], 3)
        self.assertTrue(result["pause"])
        identity["dispatch_id"] = "dispatch-12"
        policy["director_assessments"] = 3
        with self.assertRaises(ValueError):
            budget.reserve(identity, policy, state=state)

    def test_defaults_allow_five_then_three_then_three_external_invocations(self):
        budget = load_budget(self)
        state = {}
        identity = {"run_id": "run", "task_family": "family-1", "task_id": 1,
                    "role": "operator", "dispatch_id": "dispatch-1"}
        policy = {"cycle_allowances": [5, 3, 3], "max_cycles": 3}
        first = budget.reserve(identity, policy, state=state)
        self.assertEqual(first.get("cycle_allowances"), [5, 3, 3])
        self.assertEqual(first.get("cycle"), 1)

    def test_reservation_replay_is_idempotent_and_transport_is_not_coder_failure(self):
        budget = load_budget(self)
        state = {}
        identity = {"run_id": "run", "task_family": "family-1", "task_id": 1,
                    "role": "operator", "dispatch_id": "dispatch-1"}
        policy = {"cycle_allowances": [5, 3, 3], "max_cycles": 3}
        first = budget.reserve(identity, policy, state=state)
        replay = budget.reserve(identity, policy, state=state)
        self.assertEqual(first, replay)
        self.assertEqual(replay.get("coder_invocations"), 1)
        self.assertEqual(replay.get("transport_attempts"), 0)

    def test_budget_exhaustion_pauses_after_third_assessment_without_double_charge(self):
        budget = load_budget(self)
        state = {}
        policy = {"cycle_allowances": [1, 1, 1], "max_cycles": 3}
        last = None
        for number in range(1, 4):
            last = budget.reserve({"run_id": "run", "task_family": "family-1",
                                  "task_id": 1, "role": "operator",
                                  "dispatch_id": "dispatch-%d" % number}, policy, state=state)
        self.assertEqual(last.get("coder_invocations"), 3)
        self.assertTrue(last.get("pause"))
        with self.assertRaises((ValueError, RuntimeError)):
            budget.reserve({"run_id": "run", "task_family": "family-1",
                           "task_id": 1, "role": "operator",
                           "dispatch_id": "dispatch-4"}, policy, state=state)

    def test_corrective_child_and_scope_change_share_family_budget(self):
        budget = load_budget(self)
        state = {}
        policy = {"cycle_allowances": [5, 3, 3], "max_cycles": 3}
        root = budget.reserve({"run_id": "run", "task_family": "family-1", "task_id": 1,
                              "role": "operator", "dispatch_id": "dispatch-1"}, policy, state=state)
        child = budget.reserve({"run_id": "run", "task_family": "family-1", "task_id": 2,
                               "role": "operator", "dispatch_id": "dispatch-2",
                               "scope_revision": "rev-2"}, policy, state=state)
        self.assertEqual(root.get("coder_invocations"), 1)
        self.assertEqual(child.get("coder_invocations"), 2)
        self.assertEqual(child.get("cycle"), 1)


if __name__ == "__main__":
    unittest.main()
