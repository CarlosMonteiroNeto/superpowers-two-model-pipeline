import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from template_score import compute_score


def tdata(**overrides):
    base = {
        "template": "fluttercommunity/awesome-flutter",
        "stars": 1000,
        "recency_days": 30,
        "flutter_ready": "current",
        "open_issues": 10,
        "closed_issues": 90,
        "stars_per_year": 10.0,
        "license": "mit",
        "readme": "full",
    }
    base.update(overrides)
    return base


class TestStarsBuckets(unittest.TestCase):
    def test_buckets(self):
        cases = {1000: 30, 999: 24, 300: 24, 299: 18, 100: 18, 99: 12, 30: 12, 29: 6, 10: 6, 9: 0}
        for stars, expected in cases.items():
            result = compute_score(tdata(stars=stars))
            self.assertEqual(result["criteria"]["stars"], expected, f"stars={stars}")


class TestRecencyBands(unittest.TestCase):
    def test_bands(self):
        cases = {89: 20, 90: 12, 179: 12, 180: 5, 364: 5, 365: 0}
        for days, expected in cases.items():
            result = compute_score(tdata(recency_days=days))
            self.assertEqual(result["criteria"]["recency"], expected, f"days={days}")


class TestFlutterReadiness(unittest.TestCase):
    def test_readiness_scores(self):
        cases = {"current": 20, "dated": 10, "none": 0}
        for ready, expected in cases.items():
            result = compute_score(tdata(flutter_ready=ready))
            self.assertEqual(result["criteria"]["flutter_ready"], expected, f"flutter_ready={ready}")


class TestIssueRatioBands(unittest.TestCase):
    def test_bands(self):
        cases = {(10, 90): 10, (20, 80): 5, (40, 60): 5, (41, 59): 0}
        for (open_, closed), expected in cases.items():
            result = compute_score(tdata(open_issues=open_, closed_issues=closed))
            self.assertEqual(result["criteria"]["issue_ratio"], expected, f"open={open_}")


class TestSustainedInterest(unittest.TestCase):
    def test_stars_per_year_buckets(self):
        cases = {10.0: 10, 9.9: 6, 1.0: 6, 0.9: 2, 0.0: 2}
        for spy, expected in cases.items():
            result = compute_score(tdata(stars_per_year=spy))
            self.assertEqual(result["criteria"]["sustained_interest"], expected, f"spy={spy}")


class TestLicense(unittest.TestCase):
    def test_license_scores(self):
        cases = {"mit": 5, "apache": 5, "bsd": 5, "other": 3, "none": 0}
        for lic, expected in cases.items():
            result = compute_score(tdata(license=lic))
            self.assertEqual(result["criteria"]["license"], expected, f"license={lic}")


class TestReadmeQuality(unittest.TestCase):
    def test_readme_scores(self):
        cases = {"full": 5, "partial": 2, "none": 0}
        for readme, expected in cases.items():
            result = compute_score(tdata(readme=readme))
            self.assertEqual(result["criteria"]["readme"], expected, f"readme={readme}")


class TestTotals(unittest.TestCase):
    def test_perfect_template_totals_100(self):
        result = compute_score(tdata())
        self.assertEqual(result["total"], 100.0)

    def test_total_never_exceeds_100(self):
        result = compute_score(tdata())
        self.assertLessEqual(result["total"], 100.0)

    def test_heaviest_criterion_is_stars(self):
        """Stars (30) must be the heaviest-weight criterion: the primary sort
        key of the template search."""
        result = compute_score(tdata())
        weights = result["criteria"]
        self.assertGreaterEqual(weights["stars"], weights["recency"])
        self.assertGreaterEqual(weights["stars"], weights["flutter_ready"])


class TestGateVerdicts(unittest.TestCase):
    def test_auto_approve_at_70(self):
        """70.0 sits exactly on the AUTO_APPROVE threshold (24+20+20+0+6+0+0)."""
        result = compute_score(tdata(
            stars=300, recency_days=89, flutter_ready="current",
            open_issues=41, closed_issues=59, stars_per_year=5.0,
            license="none", readme="none",
        ))
        self.assertEqual(result["total"], 70.0)
        self.assertEqual(result["verdict"], "AUTO_APPROVE")

    def test_auto_approve_above_70(self):
        result = compute_score(tdata())
        self.assertEqual(result["verdict"], "AUTO_APPROVE")

    def test_developer_decision_band(self):
        # 18+0+20+5+6+3+2 = 54
        result = compute_score(tdata(
            stars=100, recency_days=365, flutter_ready="current",
            open_issues=40, closed_issues=60, stars_per_year=1.0,
            license="other", readme="partial",
        ))
        self.assertGreaterEqual(result["total"], 50)
        self.assertLess(result["total"], 70)
        self.assertEqual(result["verdict"], "DEVELOPER_DECISION")

    def test_auto_reject_below_50(self):
        result = compute_score(tdata(
            stars=9, recency_days=400, flutter_ready="none",
            open_issues=41, closed_issues=59, stars_per_year=0.5,
            license="none", readme="none",
        ))
        self.assertLess(result["total"], 50)
        self.assertEqual(result["verdict"], "AUTO_REJECT")


if __name__ == "__main__":
    unittest.main()