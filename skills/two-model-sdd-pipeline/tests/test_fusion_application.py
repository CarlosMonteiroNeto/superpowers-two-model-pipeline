import copy
import hashlib
import json
import pathlib
import sys
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import fusion_apply


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def task(identifier, *, touches, depends_on=None, **extra):
    value = {
        "id": identifier,
        "title": "Task {}".format(identifier),
        "summary": "A complete task summary.",
        "touches": touches,
        "acceptance": ["Acceptance {}.".format(identifier)],
        "spec_refs": ["docs/spec-{}.md#contract".format(identifier)],
        "depends_on": depends_on or [],
    }
    value.update(extra)
    return value


class FusionApplicationTests(unittest.TestCase):
    def report_for(self, plan, pairs):
        return {"draft_hash": digest(plan), "policy_version": "site5-v1", "source_snapshot": copy.deepcopy(plan), "pairs": [
            {"ids": ids, "candidate_hash": fusion_apply.candidate_hash(plan, ids),
             "choice": "same_shape_fuse", "confidence": .95,
             "probabilities": {"same_shape_fuse": .95, "keep_separate": .05}}
            for ids in pairs
        ]}

    def test_apply_consecutively_renumbers_and_preserves_fusion_provenance(self):
        plan = {"feature": "fusion", "tasks": [
            task(10, touches=["scripts/a.py"]),
            task(20, touches=["scripts/b.py"]),
            task(40, touches=["scripts/c.py"], depends_on=[10, 20]),
        ]}
        report = self.report_for(plan, [[10, 20]])
        selection = {"draft_hash": digest(plan), "report_hash": digest(report), "pairs": [{
            "ids": [10, 20], "title": "Fused", "summary": "Combined", "rationale": "Same shape.",
        }]}
        output, source_id_map = fusion_apply.apply_selection(plan, report, selection)
        self.assertEqual([item["id"] for item in output["tasks"]], [1, 2])
        self.assertEqual(output["tasks"][0]["fused_from"], [10, 20])
        self.assertEqual(output["tasks"][1]["depends_on"], [1])
        self.assertEqual(source_id_map, {"10": 1, "20": 1, "40": 2})
        self.assertEqual(output["tasks"][0]["acceptance"], ["Acceptance 10.", "Acceptance 20."])

    def test_apply_rejects_stale_or_nonqualifying_selection_without_mutating_source(self):
        plan = {"tasks": [task(1, touches=["scripts/a.py"]), task(2, touches=["scripts/b.py"])]}
        original = copy.deepcopy(plan)
        report = {"draft_hash": "stale", "policy_version": "site5-v1", "pairs": []}
        selection = {"draft_hash": digest(plan), "report_hash": digest(report), "pairs": []}
        with self.assertRaisesRegex(ValueError, "stale"):
            fusion_apply.apply_selection(plan, report, selection)
        self.assertEqual(plan, original)

    def test_apply_uses_both_source_dependency_sets_and_rejects_collective_cycle(self):
        plan = {"tasks": [
            task(1, touches=["scripts/a.py"]), task(2, touches=["scripts/b.py"], depends_on=[1]),
            task(3, touches=["scripts/c.py"]), task(4, touches=["scripts/d.py"], depends_on=[3]),
        ]}
        report = self.report_for(plan, [[1, 4], [2, 3]])
        selection = {"draft_hash": digest(plan), "report_hash": digest(report), "pairs": [
            {"ids": [1, 4], "title": "First", "summary": "First fused", "rationale": "Same shape."},
            {"ids": [2, 3], "title": "Second", "summary": "Second fused", "rationale": "Same shape."},
        ]}
        with self.assertRaisesRegex(ValueError, "cycle"):
            fusion_apply.apply_selection(plan, report, selection)

    def test_apply_revalidates_snapshot_candidate_and_raw_judgment_instead_of_selectable_flag(self):
        plan = {"tasks": [task(1, touches=["scripts/a.py"]), task(2, touches=["scripts/b.py"])]}
        report = self.report_for(plan, [[1, 2]])
        report["pairs"][0]["candidate_hash"] = "forged"
        report["pairs"][0]["selectable"] = True
        selection = {"draft_hash": digest(plan), "report_hash": digest(report), "pairs": [{
            "ids": [1, 2], "title": "Fused", "summary": "Combined", "rationale": "Same shape.",
        }]}
        with self.assertRaisesRegex(ValueError, "candidate"):
            fusion_apply.apply_selection(plan, report, selection)

    def test_apply_rejects_nonfinite_or_invalid_raw_choice_probabilities(self):
        plan = {"tasks": [task(1, touches=["scripts/a.py"]), task(2, touches=["scripts/b.py"])]}
        report = self.report_for(plan, [[1, 2]])
        report["pairs"][0]["confidence"] = float("inf")
        report["pairs"][0]["probabilities"] = {"same_shape_fuse": 1.2, "keep_separate": -0.2}
        selection = {"draft_hash": digest(plan), "report_hash": digest(report), "pairs": [{
            "ids": [1, 2], "title": "Fused", "summary": "Combined", "rationale": "Same shape.",
        }]}
        with self.assertRaisesRegex(ValueError, "qualifying"):
            fusion_apply.apply_selection(plan, report, selection)

    def test_apply_rejects_unknown_task_metadata_in_a_selected_pair(self):
        plan = {"tasks": [
            task(1, touches=["scripts/a.py"], unmergeable={"keep": True}),
            task(2, touches=["scripts/b.py"]),
        ]}
        report = self.report_for(plan, [[1, 2]])
        selection = {"draft_hash": digest(plan), "report_hash": digest(report), "pairs": [{
            "ids": [1, 2], "title": "Fused", "summary": "Combined", "rationale": "Same shape.",
        }]}
        with self.assertRaisesRegex(ValueError, "metadata"):
            fusion_apply.apply_selection(plan, report, selection)
