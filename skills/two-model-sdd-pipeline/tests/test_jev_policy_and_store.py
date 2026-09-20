import json
import pathlib
import sys
import tempfile
import concurrent.futures
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import jev_policy
import jev_store


class PolicyAndStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jev policy ")
        self.path = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sites_one_to_four_default_to_shadow(self):
        self.assertEqual(jev_policy.read_policy(None, "site1")["mode"], "shadow")
        self.assertEqual(jev_policy.read_policy(None, "site4")["mode"], "shadow")

    def test_active_without_bound_calibration_degrades_to_shadow(self):
        policy = {"mode": "active", "site": "site3", "model": "m", "schema_hash": "s", "threshold": 0.9, "evaluator": "e"}
        self.assertEqual(jev_policy.select_action(policy, "q", {"model": "m", "schema_hash": "s", "answers": {"q": {"confidence": .95}}}, "baseline"), "baseline")
        self.assertEqual(policy["effective_mode"], "shadow")

    def test_site_five_only_allows_selected_apply(self):
        policy = jev_policy.read_policy(None, "site5")
        self.assertEqual(policy["mode"], "shadow")
        self.assertEqual(jev_policy.select_action({"mode": "selected-apply", "site": "site5"}, "q", {}, "baseline"), "selected-apply")

    def test_invalid_policy_values_degrade_to_shadow(self):
        policy = {"mode": "active", "site": "site3", "threshold": "broken"}
        self.assertEqual(jev_policy.select_action(policy, "q", {"answers": {}}, "baseline"), "baseline")
        self.assertEqual(policy["effective_mode"], "shadow")

    def test_active_policy_top_level_model_and_schema_must_match(self):
        policy = {"mode": "active", "site": "site3", "model": "wrong", "schema_hash": "wrong", "threshold": .9, "evaluator": "eval", "calibration_report": {"site": "site3", "model": "model", "schema_hash": "schema", "threshold": .9, "evaluator": "eval"}}
        envelope = {"model": "model", "schema_hash": "schema", "answers": {"q": {"confidence": .95, "choice": "focused"}}}
        self.assertEqual(jev_policy.select_action(policy, "q", envelope, "baseline"), "baseline")
        self.assertEqual(policy["effective_mode"], "shadow")

    def test_advisory_records_are_site_isolated_and_atomic_json(self):
        record = {"state_identity": "state-a", "policy_identity": "policy-a", "decision": "shadow", "actual_action": "baseline", "fallback": "baseline", "timing": {"duration_ms": 1}, "usage": None}
        a = jev_store.write_record(self.tmp.name, "site1", "state-a", record)
        b = jev_store.write_record(self.tmp.name, "site2", "state-a", record)
        self.assertNotEqual(a, b)
        self.assertEqual(json.loads(pathlib.Path(a).read_text(encoding="utf-8"))["site"], "site1")
        self.assertFalse(list(self.path.rglob("*.tmp")))

    def test_advisory_records_require_complete_evidence(self):
        with self.assertRaises(ValueError):
            jev_store.write_record(self.tmp.name, "site1", "state-a", {"decision": "shadow"})

    def test_concurrent_circuit_failures_are_not_lost(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: jev_store.record_failure(self.tmp.name, "site1"), range(16)))
        self.assertEqual(jev_store.circuit_state(self.tmp.name, "site1")["failures"], 16)


if __name__ == "__main__":
    unittest.main()
