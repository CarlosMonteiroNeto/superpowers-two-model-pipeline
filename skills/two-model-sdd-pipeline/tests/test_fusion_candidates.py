import pathlib
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import fusion_candidates


def task(identifier, *, touches, depends_on=None, acceptance=None, **extra):
    value = {
        "id": identifier,
        "title": "Task {}".format(identifier),
        "summary": "A complete task summary.",
        "touches": touches,
        "acceptance": acceptance or ["Observable acceptance."],
        "spec_refs": ["docs/spec.md#contract"],
        "depends_on": depends_on or [],
    }
    value.update(extra)
    return value


class FusionCandidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="fusion candidates ")

    def tearDown(self):
        self.tmp.cleanup()

    def test_validation_rejects_noncanonical_and_test_touches(self):
        plan = {"tasks": [task(1, touches=["../scripts/unsafe.py"])]}
        with self.assertRaisesRegex(ValueError, "canonical"):
            fusion_candidates.validate_plan(plan)
        plan = {"tasks": [task(1, touches=["skills/tests/test_fusion.py"])]}
        with self.assertRaisesRegex(ValueError, "test"):
            fusion_candidates.validate_plan(plan)

    def test_build_candidates_excludes_indirect_dependencies_and_keeps_disjoint_pair(self):
        plan = {"tasks": [
            task(1, touches=["scripts/a.py"]),
            task(2, touches=["scripts/b.py"], depends_on=[1]),
            task(3, touches=["scripts/c.py"]),
            task(4, touches=["scripts/d.py"], corrects=2),
        ]}
        report = fusion_candidates.build_candidates(plan, self.tmp.name)
        pairs = [pair["ids"] for pair in report["pairs"]]
        self.assertIn([1, 3], pairs)
        self.assertNotIn([1, 2], pairs)
        self.assertNotIn([2, 4], pairs)
        self.assertTrue(any("corrective" in " ".join(reasons) for reasons in report["exclusions"].values()))

    def test_oversized_pair_is_unevaluated_without_losing_other_eligible_pairs(self):
        plan = {"tasks": [
            task(1, touches=["scripts/a.py", "scripts/b.py", "scripts/c.py", "scripts/d.py"]),
            task(2, touches=["scripts/e.py", "scripts/f.py", "scripts/g.py"]),
            task(3, touches=["scripts/h.py"]),
        ]}
        report = fusion_candidates.build_candidates(plan, self.tmp.name)
        self.assertNotIn([1, 2], [pair["ids"] for pair in report["pairs"]])
        self.assertIn([1, 3], [pair["ids"] for pair in report["pairs"]])
        self.assertIn("limits", " ".join(report["exclusions"]["1,2"]))

    def test_batches_are_stable_bounded_and_mark_individually_oversized_pairs(self):
        pairs = [{"ids": [index, index + 100], "left": {"id": index, "text": "x" * 100}, "right": {"id": index + 100, "text": "y" * 100}}
                 for index in range(1, 35)]
        pairs.append({"ids": [99, 199], "left": {"text": "x" * 70000}, "right": {"text": "y" * 70000}})
        batches, oversized = fusion_candidates.batch_pairs(pairs)
        self.assertEqual([pair["ids"] for batch in batches for pair in batch], [pair["ids"] for pair in pairs[:-1]])
        self.assertEqual(oversized, [[99, 199]])
        self.assertTrue(all(len(batch) <= 32 for batch in batches))
        self.assertTrue(all(len(fusion_candidates.canonical_json(batch).encode("utf-8")) <= 65536 for batch in batches))

    def test_build_candidates_propagates_touches_overlap_invalid_exit(self):
        plan = {"tasks": [task(1, touches=["scripts/a.py"]), task(2, touches=["scripts/b.py"])]}
        with self.assertRaisesRegex(ValueError, "touches-overlap"):
            fusion_candidates.build_candidates(plan, self.tmp.name, overlap_runner=lambda *_: 2)

    def test_batches_measure_exact_classifier_request_not_candidate_json(self):
        pair = {"ids": [1, 2], "left": {"text": "x" * 21000}, "right": {"text": "y" * 21000}, "candidate_hash": "hash"}
        batches, oversized = fusion_candidates.batch_pairs([pair], model="jev-model", schema_builder=lambda values: {"model": "jev-model", "questions": {"q": {"instructions": "z" * 24000, "criteria": {"same_shape_fuse": "yes", "keep_separate": "no"}}}})
        self.assertEqual(batches, [])
        self.assertEqual(oversized, [[1, 2]])
