import json
import pathlib
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import jev_evaluate


class EvaluationTests(unittest.TestCase):
    def test_keeps_recommendation_and_execution_populations_distinct(self):
        reports = [{"request_hash": "r1", "answers": {"q": {"choice": "yes", "confidence": .95}}, "usage": None, "duration_ms": 9}]
        labels = [{"request_hash": "r1", "question_id": "q", "actual_decision": "no", "actual_action": "baseline", "outcome": "passed", "evidence_refs": ["x"]}]
        result = jev_evaluate.evaluate(reports, labels)
        self.assertEqual(result["recommendation_agreement"]["count"], 1)
        self.assertEqual(result["executed_outcomes"]["count"], 0)
        self.assertEqual(result["false_positive_labels"], ["r1:q"])
        self.assertTrue(result["missing_evidence"])

    def test_executed_population_requires_executed_outcome(self):
        result = jev_evaluate.evaluate([{"request_hash": "r", "answers": {"q": {"choice": "yes"}}, "usage": None}], [{"request_hash": "r", "question_id": "q", "actual_decision": "yes", "actual_action": "executed", "outcome": "passed", "evidence_refs": ["e"]}])
        self.assertEqual(result["recommendation_agreement"]["count"], 1)
        self.assertEqual(result["executed_outcomes"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
