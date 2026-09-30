"""R4.5 metrics preserve observed cost dimensions and unknowns."""
import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"


def load_metrics(test):
    path = SCRIPTS / "dispatch_metrics.py"
    test.assertTrue(path.is_file(), "R4.5 requires dispatch_metrics.py")
    spec = importlib.util.spec_from_file_location("r45_dispatch_metrics", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DispatchMetricsTests(unittest.TestCase):
    def test_codex_and_opencode_fixtures_keep_invocations_turns_and_retries_distinct(self):
        metrics = load_metrics(self)
        records = [
            {"backend": "codex", "dispatch_id": "c1", "semantic_invocations": 1,
             "backend_model_turns": 2, "transport_retries": 1, "jev_calls": 0,
             "usage": {"input_tokens": 100, "output_tokens": 20,
                       "cached_tokens": 30}, "latency_ms": 250.5,
             "escaped_defects": 0},
            {"backend": "opencode", "dispatch_id": "o1", "semantic_invocations": 1,
             "backend_model_turns": 1, "transport_retries": 0, "jev_calls": 1,
             "usage": {"input_tokens": 50, "output_tokens": 10,
                       "cached_tokens": None}, "latency_ms": 500,
             "escaped_defects": 1},
        ]
        result = metrics.summarize(records)
        self.assertEqual(result["semantic_invocations"], 2)
        self.assertEqual(result["backend_model_turns"], 3)
        self.assertEqual(result["transport_retries"], 1)
        self.assertEqual(result["jev_calls"], 1)
        self.assertEqual(result["tokens"], {"input": 150, "output": 30,
                                           "cached": None})
        self.assertEqual(result["latency_ms_total"], 750.5)
        self.assertEqual(result["escaped_defects"], 1)
        self.assertEqual(result["by_backend"]["codex"]["semantic_invocations"], 1)
        self.assertEqual(result["by_backend"]["opencode"]["semantic_invocations"], 1)

    def test_missing_cost_evidence_stays_null_and_invocation_drop_is_not_savings(self):
        metrics = load_metrics(self)
        current = metrics.summarize([{"backend": "codex", "dispatch_id": "c1",
                                      "semantic_invocations": 1}])
        baseline = metrics.summarize([{"backend": "codex", "dispatch_id": "old",
                                       "semantic_invocations": 4}])
        self.assertIsNone(current["tokens"]["input"])
        self.assertIsNone(current["tokens"]["output"])
        self.assertIsNone(current["tokens"]["cached"])
        self.assertIsNone(current["latency_ms_total"])
        self.assertIsNone(current["escaped_defects"])
        decision = metrics.compare_cost(baseline, current)
        self.assertEqual(decision["status"], "insufficient_evidence")
        self.assertFalse(decision["savings_claim_allowed"])

    def test_malformed_records_and_duplicate_dispatch_ids_are_rejected(self):
        metrics = load_metrics(self)
        with self.assertRaises(ValueError):
            metrics.summarize([{"backend": "codex", "dispatch_id": "x",
                                "semantic_invocations": -1}])
        record = {"backend": "codex", "dispatch_id": "same",
                  "semantic_invocations": 1}
        with self.assertRaises(ValueError):
            metrics.summarize([record, record])

    def test_malformed_comparison_evidence_is_rejected(self):
        metrics = load_metrics(self)
        with self.assertRaises(ValueError):
            metrics.compare_cost({"tokens": {"input": "many"}}, {})


if __name__ == "__main__":
    unittest.main()
