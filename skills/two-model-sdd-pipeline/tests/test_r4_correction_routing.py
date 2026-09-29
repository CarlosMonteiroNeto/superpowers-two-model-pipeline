"""R4 black box checks for correction routing and single review ownership."""
import importlib.util
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"


def load_module(testcase, name):
    path = SCRIPTS / (name + ".py")
    testcase.assertTrue(path.is_file(), "R4 requires the shared " + name + " API")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CorrectionRoutingTests(unittest.TestCase):
    def finding(self, scope="in_scope", paths=None, contracts=None):
        return {"severity": "Important", "file": "src/a.py", "line": 4,
                "issue": "incorrect result", "fix": "correct result",
                "correction_scope": scope, "affected_paths": paths or ["src/a.py"],
                "affected_contracts": contracts or ["returns the expected value"]}

    def review(self, finding=None):
        return {"verdict": "SEND_BACK", "findings": [finding or self.finding()],
                "minors": [], "summary": "fix the finding"}

    def task(self):
        return {"id": 1, "touches": ["src/a.py"],
                "acceptance": ["returns the expected value"], "scope_grants": []}

    def test_in_scope_send_back_routes_directly_to_coder(self):
        policy = load_module(self, "correction_policy")
        result = policy.decide(self.review(), self.task())
        self.assertEqual(result.get("action"), "coder")

    def test_structural_or_uncertain_finding_requires_director(self):
        policy = load_module(self, "correction_policy")
        for scope in ("structural", "uncertain"):
            with self.subTest(scope=scope):
                result = policy.decide(self.review(self.finding(scope)), self.task())
                self.assertEqual(result.get("action"), "director")

    def test_out_of_scope_path_needs_valid_grant_and_malformed_metadata_blocks(self):
        policy = load_module(self, "correction_policy")
        finding = self.finding(paths=["src/extra.py"])
        result = policy.decide(self.review(finding), self.task())
        self.assertEqual(result.get("action"), "director")
        task = self.task()
        task["scope_grants"] = [{"paths": ["src/extra.py"],
                                  "contracts": ["returns the expected value"]}]
        self.assertEqual(policy.decide(self.review(finding), task).get("action"), "coder")
        malformed = self.review(finding)
        del malformed["findings"][0]["affected_paths"]
        self.assertEqual(policy.decide(malformed, task).get("action"), "block")

    def test_any_malformed_finding_blocks_even_when_another_is_structural(self):
        policy = load_module(self, "correction_policy")
        review = self.review(self.finding("structural"))
        malformed = self.finding()
        del malformed["affected_contracts"]
        review["findings"].append(malformed)
        self.assertEqual(policy.decide(review, self.task()).get("action"), "block")

    def test_flutter_gate_delegates_semantic_review_to_shared_owner(self):
        gate = (ROOT / "skills" / "flutter-app-pipeline" / "scripts" / "green-gate").read_text(encoding="utf-8")
        shared = (SCRIPTS / "review-dispatch").read_text(encoding="utf-8")
        self.assertIn("review-dispatch", gate)
        self.assertIn("ensure_review", (SCRIPTS / "review_dispatch.py").read_text(encoding="utf-8"))
        self.assertNotIn('DISPATCH_BIN"', gate)
        self.assertIn("ensure_review", shared)

    def test_reviewer_schema_rejects_missing_structured_scope(self):
        schema = json.loads((ROOT / "skills" / "two-model-sdd-pipeline" / "schemas" / "reviewer-result.schema.json").read_text(encoding="utf-8"))
        finding = schema["$defs"]["finding"]
        self.assertIn("correction_scope", finding["required"])
        self.assertIn("affected_paths", finding["required"])
        self.assertIn("affected_contracts", finding["required"])


if __name__ == "__main__":
    unittest.main()
