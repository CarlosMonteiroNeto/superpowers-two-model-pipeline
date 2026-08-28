import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from pkg_score import compute_score


def data(**overrides):
    base = {
        "package": "url_launcher",
        "granted_points": 160,
        "max_points": 160,
        "popularity": 1.0,
        "recency_days": 30,
        "recency_source": "github",
        "sdk": "compatible",
        "dependents": 120,
        "open_issues": 10,
        "closed_issues": 90,
    }
    base.update(overrides)
    return base


class TestPubPointsNormalization(unittest.TestCase):
    def test_perfect_package_scores_30_not_34(self):
        """The /140 bug would give a perfect package 34.3 on this criterion.
        The corrected formula normalizes by max_points (160)."""
        result = compute_score(data(granted_points=160, max_points=160))
        self.assertEqual(result["criteria"]["pub_points"], 30.0)

    def test_partial_points_normalize_by_160(self):
        result = compute_score(data(granted_points=140, max_points=160))
        self.assertAlmostEqual(result["criteria"]["pub_points"], 26.25, places=2)

    def test_perfect_package_total_is_exactly_100(self):
        result = compute_score(data())
        self.assertEqual(result["total"], 100.0)


class TestPopularityScoring(unittest.TestCase):
    def test_popularity_scales_to_15(self):
        result = compute_score(data(popularity=0.5))
        self.assertEqual(result["criteria"]["popularity"], 7.5)


class TestRecencyBands(unittest.TestCase):
    def test_bands(self):
        cases = {89: 20, 90: 12, 179: 12, 180: 5, 364: 5, 365: 0}
        for days, expected in cases.items():
            result = compute_score(data(recency_days=days))
            self.assertEqual(result["criteria"]["recency"], expected, f"days={days}")


class TestSdkCompatibility(unittest.TestCase):
    def test_sdk_scores(self):
        cases = {"compatible": 15, "needs_override": 5, "incompatible": 0}
        for sdk, expected in cases.items():
            result = compute_score(data(sdk=sdk))
            self.assertEqual(result["criteria"]["sdk"], expected, f"sdk={sdk}")


class TestDependentsBuckets(unittest.TestCase):
    def test_buckets(self):
        cases = {50: 10, 49: 6, 10: 6, 9: 3, 1: 3, 0: 0}
        for count, expected in cases.items():
            result = compute_score(data(dependents=count))
            self.assertEqual(result["criteria"]["dependents"], expected, f"dependents={count}")


class TestIssueRatioBands(unittest.TestCase):
    def test_bands(self):
        cases = {(10, 90): 10, (20, 80): 5, (40, 60): 5, (41, 59): 0}
        for (open_, closed), expected in cases.items():
            result = compute_score(data(open_issues=open_, closed_issues=closed))
            self.assertEqual(result["criteria"]["issue_ratio"], expected, f"open={open_}")


class TestGateVerdicts(unittest.TestCase):
    def _total(self, **over):
        return compute_score(data(**over))["total"]

    def test_auto_approve_at_70(self):
        """70.0 sits exactly on the AUTO_APPROVE threshold."""
        # zero out pub_points only: total == 70.0 (15+20+15+10+10)
        result = compute_score(data(granted_points=0, max_points=160))
        self.assertEqual(result["total"], 70.0)
        self.assertEqual(result["verdict"], "AUTO_APPROVE")

    def test_auto_approve_above_70(self):
        result = compute_score(data())
        self.assertEqual(result["verdict"], "AUTO_APPROVE")

    def test_developer_decision_band(self):
        # middling package: pub 22.5 + popularity 15 + recency 5 + sdk 5 + dep 0 + issues 10 = 57.5
        result = compute_score(data(granted_points=120, max_points=160, recency_days=200, sdk="needs_override", dependents=0))
        self.assertGreaterEqual(result["total"], 50)
        self.assertLess(result["total"], 70)
        self.assertEqual(result["verdict"], "DEVELOPER_DECISION")

    def test_auto_reject_below_50(self):
        result = compute_score(data(granted_points=0, max_points=160, popularity=0.0, recency_days=400, sdk="incompatible", dependents=0))
        self.assertLess(result["total"], 50)
        self.assertEqual(result["verdict"], "AUTO_REJECT")


class TestVerdictRounding(unittest.TestCase):
    def test_total_never_exceeds_100(self):
        result = compute_score(data())
        self.assertLessEqual(result["total"], 100.0)


if __name__ == "__main__":
    unittest.main()