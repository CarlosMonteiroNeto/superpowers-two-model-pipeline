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
    def test_perfect_package_scores_20(self):
        """Re-weighted: pub points now weight 20 of 100 (was 30)."""
        result = compute_score(data(granted_points=160, max_points=160))
        self.assertEqual(result["criteria"]["pub_points"], 20.0, "pub_points must be 20.0 (re-weighted)")

    def test_partial_points_normalize_by_160(self):
        result = compute_score(data(granted_points=140, max_points=160))
        self.assertAlmostEqual(result["criteria"]["pub_points"], 17.5, places=2)

    def test_perfect_package_total_is_exactly_100(self):
        result = compute_score(data())
        self.assertEqual(result["total"], 100.0)


class TestPopularityScoring(unittest.TestCase):
    def test_popularity_scales_to_10(self):
        result = compute_score(data(popularity=0.5))
        self.assertEqual(result["criteria"]["popularity"], 5.0, "popularity must scale to 10 max (re-weighted)")


class TestRecencyBands(unittest.TestCase):
    def test_bands(self):
        cases = {89: 20, 90: 12, 179: 12, 180: 5, 364: 5, 365: 0}
        for days, expected in cases.items():
            result = compute_score(data(recency_days=days))
            self.assertEqual(result["criteria"]["recency"], expected, f"days={days}")


class TestSdkCompatibility(unittest.TestCase):
    def test_sdk_scores(self):
        cases = {"compatible": 20, "needs_override": 7, "incompatible": 0}
        for sdk, expected in cases.items():
            result = compute_score(data(sdk=sdk))
            self.assertEqual(result["criteria"]["sdk"], expected, f"sdk={sdk} must be {expected}")


class TestDependentsBuckets(unittest.TestCase):
    def test_buckets(self):
        cases = {50: 15, 49: 9, 10: 9, 9: 4, 1: 4, 0: 0}
        for count, expected in cases.items():
            result = compute_score(data(dependents=count))
            self.assertEqual(result["criteria"]["dependents"], expected, f"dependents={count} must be {expected}")


class TestIssueRatioBands(unittest.TestCase):
    def test_bands(self):
        cases = {(10, 90): 15, (20, 80): 7, (40, 60): 7, (41, 59): 0}
        for (open_, closed), expected in cases.items():
            result = compute_score(data(open_issues=open_, closed_issues=closed))
            self.assertEqual(result["criteria"]["issue_ratio"], expected, f"open={open_} must be {expected}")


class TestHealthWeight(unittest.TestCase):
    def test_health_signals_sum_to_55(self):
        """Recency (20) + SDK (20) + issue ratio (15) = 55 of 100."""
        result = compute_score(data())
        health = (
            result["criteria"]["recency"]
            + result["criteria"]["sdk"]
            + result["criteria"]["issue_ratio"]
        )
        self.assertEqual(health, 55, "health signals must sum to 55")


class TestGateVerdicts(unittest.TestCase):
    def _total(self, **over):
        return compute_score(data(**over))["total"]

    def test_auto_approve_at_70(self):
        """70.0 sits exactly on the AUTO_APPROVE threshold (0+0+20+20+15+15)."""
        result = compute_score(data(granted_points=0, max_points=160, popularity=0.0))
        self.assertEqual(result["total"], 70.0)
        self.assertEqual(result["verdict"], "AUTO_APPROVE")

    def test_auto_approve_above_70(self):
        result = compute_score(data())
        self.assertEqual(result["verdict"], "AUTO_APPROVE")

    def test_developer_decision_band(self):
        # pub 15 + popularity 10 + recency 5 + sdk 7 + dep 0 + issues 15 = 52
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