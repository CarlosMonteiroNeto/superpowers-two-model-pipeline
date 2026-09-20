import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
SCHEMAS = pathlib.Path(__file__).resolve().parent.parent / "schemas"
sys.path.insert(0, str(SCRIPTS))

import review_guidance


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def schema_hash():
    schema = json.loads((SCHEMAS / "jev-site-4.json").read_text(encoding="utf-8"))
    return hashlib.sha256(canonical(schema).encode("utf-8")).hexdigest()


def active_policy():
    return {
        "site": "site4",
        "mode": "active",
        "model": "jev",
        "schema_hash": schema_hash(),
        "threshold": 0.9,
        "evaluator": "test-evaluator",
        "calibration_report": {
            "site": "site4",
            "model": "jev",
            "schema_hash": schema_hash(),
            "threshold": 0.9,
            "evaluator": "test-evaluator",
        },
    }


def answer(choice, confidence=0.95):
    probabilities = {
        "focused_review": 0.95 if choice == "focused_review" else 0.05,
        "standard_review": 0.95 if choice == "standard_review" else 0.05,
    }
    return {
        "status": "answered",
        "model": "jev",
        "schema_hash": schema_hash(),
        "usage": {"input_tokens": 12, "output_tokens": 4},
        "cache_hit": False,
        "answers": {
            "review_depth": {
                "type": "choice",
                "choice": choice,
                "probabilities": probabilities,
                "confidence": confidence,
            }
        },
    }


class ReviewGuidanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jev review guidance ")
        self.workspace = pathlib.Path(self.tmp.name)
        self.package = self.workspace / "task-4-review-package.diff"
        self.package.write_bytes(
            b"# Review package: BASE..HEAD\n\n"
            b"## Task Brief\n# Task 4 Brief\nPreserve reviewer authority.\n\n"
            b"## Commits\nabc change\n\n"
            b"## Files changed\napp.py | 2 +\n\n"
            b"## Diff\ndiff --git a/app.py b/app.py\n+value = 1\n"
        )
        (self.workspace / "plan.json").write_text(json.dumps({
            "tasks": [{
                "id": 4,
                "title": "Review guidance",
                "summary": "Preserve the mandatory reviewer.",
                "spec_refs": ["docs/spec.md#site-4"],
                "touches": ["app.py"],
                "acceptance": ["the reviewer remains authoritative"],
            }],
        }), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def prepare(self, policy=None):
        policy_path = None
        if policy is not None:
            policy_path = self.workspace / "policy.json"
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
        return review_guidance.prepare(
            str(self.package), workspace=str(self.workspace), task_id=4,
            policy_path=str(policy_path) if policy_path else None,
        )

    def test_active_calibrated_confident_choice_adds_focus_without_losing_package(self):
        original = self.package.read_bytes()
        with mock.patch.object(
            review_guidance.jev_classify, "classify",
            return_value=(0, answer("focused_review", 0.9)),
        ) as classify:
            result = self.prepare(active_policy())
        self.assertEqual(result["actual_action"], "focused_review")
        self.assertEqual(result["choice"], "focused_review")
        classify.assert_called_once()
        rendered = self.package.read_bytes()
        self.assertTrue(rendered.startswith(original))
        text = rendered.decode("utf-8")
        self.assertIn("## Review Guidance", text)
        self.assertIn("all four mandatory review duties", text)
        self.assertNotIn("approval probability", text.lower())
        self.assertNotIn("predicted verdict", text.lower())

    def test_policy_threshold_below_nine_cannot_enable_focused_review(self):
        policy = active_policy()
        policy["threshold"] = 0.8
        policy["calibration_report"]["threshold"] = 0.8
        with mock.patch.object(
            review_guidance.jev_classify, "classify",
            return_value=(0, answer("focused_review", 0.85)),
        ) as classify:
            result = self.prepare(policy)
        self.assertEqual(result["actual_action"], "standard_review")
        self.assertEqual(result["choice"], "standard_review")
        self.assertEqual(result["fallback_reason"], "uncertain")
        classify.assert_called_once()

    def test_shadow_records_hypothetical_choice_but_keeps_standard_review(self):
        with mock.patch.object(
            review_guidance.jev_classify, "classify",
            return_value=(0, answer("focused_review")),
        ) as classify:
            result = self.prepare({"site": "site4", "mode": "shadow", "threshold": 0.9})
        self.assertEqual(result["actual_action"], "standard_review")
        self.assertEqual(result["hypothetical_choice"], "focused_review")
        classify.assert_called_once()
        self.assertEqual(result["fallback_reason"], "shadow")

    def test_off_makes_no_classifier_call(self):
        with mock.patch.object(review_guidance.jev_classify, "classify") as classify:
            result = self.prepare({"site": "site4", "mode": "off", "threshold": 0.9})
        self.assertEqual(result["actual_action"], "standard_review")
        self.assertIsNone(result["hypothetical_choice"])
        classify.assert_not_called()
        self.assertEqual(result["fallback_reason"], "policy_off")

    def test_uncertain_and_unavailable_fall_back_to_standard(self):
        cases = ((0, answer("focused_review", 0.8999)),
                 (3, {"status": "unavailable", "answers": {}, "error": "offline"}))
        for code, envelope in cases:
            with self.subTest(code=code):
                self.package.write_bytes(self.package.read_bytes().split(b"\n## Review Guidance", 1)[0])
                with mock.patch.object(
                    review_guidance.jev_classify, "classify", return_value=(code, envelope),
                ):
                    result = self.prepare(active_policy())
                self.assertEqual(result["actual_action"], "standard_review")

    def test_deterministic_exclusions_never_call_classifier(self):
        for field, value in (("corrects", 1), ("fused_from", [1, 2])):
            with self.subTest(field=field):
                self.package.write_bytes(self.package.read_bytes().split(b"\n## Review Guidance", 1)[0])
                plan = json.loads((self.workspace / "plan.json").read_text(encoding="utf-8"))
                plan["tasks"][0][field] = value
                (self.workspace / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
                with mock.patch.object(review_guidance.jev_classify, "classify") as classify:
                    result = self.prepare(active_policy())
                self.assertEqual(result["actual_action"], "standard_review")
                self.assertEqual(result["fallback_reason"], "deterministic_exclusion")
                classify.assert_not_called()
                plan["tasks"][0].pop(field)
                (self.workspace / "plan.json").write_text(json.dumps(plan), encoding="utf-8")

        (self.workspace / "ledger.jsonl").write_text(json.dumps({
            "type": "interface_touched", "task": 4,
        }) + "\n", encoding="utf-8")
        with mock.patch.object(review_guidance.jev_classify, "classify") as classify:
            result = self.prepare(active_policy())
        self.assertEqual(result["actual_action"], "standard_review")
        self.assertEqual(result["fallback_reason"], "deterministic_exclusion")
        classify.assert_not_called()

    def test_oversized_or_incomplete_evidence_skips_inference(self):
        self.package.write_bytes(self.package.read_bytes().split(b"\n## Review Guidance", 1)[0] + b"x" * (65536 + 1))
        with mock.patch.object(review_guidance.jev_classify, "classify") as classify:
            result = self.prepare(active_policy())
        self.assertEqual(result["actual_action"], "standard_review")
        self.assertEqual(result["fallback_reason"], "evidence_too_large")
        classify.assert_not_called()

        self.package.write_text("# Review package\n## Commits\n", encoding="utf-8")
        with mock.patch.object(review_guidance.jev_classify, "classify") as classify:
            result = self.prepare(active_policy())
        self.assertEqual(result["actual_action"], "standard_review")
        self.assertEqual(result["fallback_reason"], "incomplete_evidence")
        classify.assert_not_called()

    def test_advisory_record_does_not_touch_authoritative_ledger(self):
        with mock.patch.object(
            review_guidance.jev_classify, "classify",
            return_value=(0, answer("standard_review")),
        ):
            result = self.prepare({"site": "site4", "mode": "shadow", "threshold": 0.9})
        self.assertTrue(list((self.workspace / ".jev" / "site4" / "advisory").glob("*.json")))
        self.assertFalse((self.workspace / "ledger.jsonl").exists())
        self.assertEqual(result["actual_action"], "standard_review")


if __name__ == "__main__":
    unittest.main()
