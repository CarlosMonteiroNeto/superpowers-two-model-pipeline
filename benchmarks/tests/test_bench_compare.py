"""Tests for the benchmark comparator (bench_compare).

The comparator diffs two side reports (serial vs parallel) into a delta
table plus the headline speedup factor. Pure arithmetic over the reports,
so the expected values are hand-derived.
"""
import os
import pathlib
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from bench_compare import compare_reports, render_compare_markdown  # noqa: E402


def report(total, requests, input_t, output_t, cache_read, cost):
    return {
        "side": "x",
        "total_wall_clock_s": total,
        "cache_hit_pct": (round(100.0 * cache_read / (cache_read + input_t), 1)
                          if (cache_read + input_t) else 0.0),
        "uncached_tokens": input_t + output_t,
        "totals": {
            "input": input_t, "output": output_t, "reasoning": 0,
            "cache_read": cache_read, "cache_write": 0,
            "cost": cost, "requests": requests, "span_s": 0.0,
        },
        "roles": {},
        "tasks": [],
    }


class CompareTest(unittest.TestCase):
    def setUp(self):
        self.serial = report(total=600.0, requests=40, input_t=2000,
                             output_t=500, cache_read=18000, cost=0.5)
        self.parallel = report(total=250.0, requests=60, input_t=2600,
                               output_t=700, cache_read=15000, cost=0.7)

    def test_speedup_is_serial_over_parallel(self):
        out = compare_reports(self.serial, self.parallel)
        self.assertAlmostEqual(out["speedup"], 2.4, places=2)

    def test_wall_clock_delta(self):
        out = compare_reports(self.serial, self.parallel)
        self.assertAlmostEqual(out["wall_clock_delta_s"], -350.0, places=2)

    def test_token_and_request_deltas(self):
        out = compare_reports(self.serial, self.parallel)
        self.assertEqual(out["requests_delta"], 20)
        # parallel - serial: (2600+700) - (2000+500)
        self.assertEqual(out["uncached_tokens_delta"], 800)

    def test_cache_hit_delta(self):
        out = compare_reports(self.serial, self.parallel)
        # serial 18000/(18000+2000)=90.0 ; parallel 15000/(15000+2600)=85.2
        self.assertAlmostEqual(out["cache_hit_delta_pct"], -4.8, places=1)

    def test_markdown_reports_speedup(self):
        out = compare_reports(self.serial, self.parallel)
        md = render_compare_markdown(out)
        self.assertIn("speedup", md.lower())
        self.assertIn("2.40", md)

    def test_zero_parallel_time_is_not_a_division_error(self):
        out = compare_reports(self.serial, report(0.0, 0, 0, 0, 0, 0.0))
        self.assertIsNone(out["speedup"])


if __name__ == "__main__":
    unittest.main()
