#!/usr/bin/env python3
"""Benchmark comparator: diff two side reports (serial vs parallel).

Takes the two ``bench_report`` results and produces the deltas plus the
headline speedup factor (serial wall-clock / parallel wall-clock). Delta
convention is ``parallel - serial`` so a negative wall-clock delta means the
parallel side was faster. No LLM, no network.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bench_report  # noqa: E402


def compare_reports(serial, parallel, serial_label=None, parallel_label=None):
    serial_s = float(serial.get("total_wall_clock_s") or 0.0)
    parallel_s = float(parallel.get("total_wall_clock_s") or 0.0)
    speedup = round(serial_s / parallel_s, 2) if parallel_s > 0 else None

    serial_totals = serial.get("totals", {})
    parallel_totals = parallel.get("totals", {})

    return {
        "serial_label": serial_label or serial.get("side", "serial"),
        "parallel_label": parallel_label or parallel.get("side", "parallel"),
        "serial_wall_clock_s": serial_s,
        "parallel_wall_clock_s": parallel_s,
        "speedup": speedup,
        "wall_clock_delta_s": round(parallel_s - serial_s, 3),
        "requests_serial": serial_totals.get("requests", 0),
        "requests_parallel": parallel_totals.get("requests", 0),
        "requests_delta": parallel_totals.get("requests", 0) - serial_totals.get("requests", 0),
        "uncached_tokens_serial": serial.get("uncached_tokens", 0),
        "uncached_tokens_parallel": parallel.get("uncached_tokens", 0),
        "uncached_tokens_delta": (parallel.get("uncached_tokens", 0)
                                  - serial.get("uncached_tokens", 0)),
        "cache_hit_pct_serial": serial.get("cache_hit_pct", 0.0),
        "cache_hit_pct_parallel": parallel.get("cache_hit_pct", 0.0),
        "cache_hit_delta_pct": round(parallel.get("cache_hit_pct", 0.0)
                                     - serial.get("cache_hit_pct", 0.0), 1),
        "cost_serial": serial_totals.get("cost", 0.0),
        "cost_parallel": parallel_totals.get("cost", 0.0),
        "cost_delta": round(parallel_totals.get("cost", 0.0)
                            - serial_totals.get("cost", 0.0), 6),
    }


def _speedup_text(speedup):
    return "n/a" if speedup is None else "%.2fx" % speedup


def render_compare_markdown(result):
    lines = []
    lines.append("# Benchmark comparison — %s vs %s"
                 % (result["serial_label"], result["parallel_label"]))
    lines.append("")
    lines.append("| Metric | Serial | Parallel | Delta (par - ser) |")
    lines.append("|---|---|---|---|")
    lines.append("| Wall-clock (s) | %.1f | %.1f | %.1f |" % (
        result["serial_wall_clock_s"], result["parallel_wall_clock_s"],
        result["wall_clock_delta_s"]))
    lines.append("| Speedup (serial/parallel) | - | - | %s |"
                 % _speedup_text(result["speedup"]))
    lines.append("| LLM requests | %d | %d | %+d |" % (
        result["requests_serial"], result["requests_parallel"],
        result["requests_delta"]))
    lines.append("| Uncached tokens | %d | %d | %+d |" % (
        result["uncached_tokens_serial"], result["uncached_tokens_parallel"],
        result["uncached_tokens_delta"]))
    lines.append("| Cache-hit %% | %.1f | %.1f | %+.1f |" % (
        result["cache_hit_pct_serial"], result["cache_hit_pct_parallel"],
        result["cache_hit_delta_pct"]))
    lines.append("| Cost | %.6f | %.6f | %+.6f |" % (
        result["cost_serial"], result["cost_parallel"], result["cost_delta"]))
    lines.append("")
    if result["speedup"] and result["speedup"] >= 1:
        lines.append("Parallel was **%.2fx faster** in wall-clock time."
                     % result["speedup"])
    elif result["speedup"]:
        lines.append("Parallel was **%.2fx slower** in wall-clock time."
                     % (1.0 / result["speedup"]))
    else:
        lines.append("No positive parallel wall-clock time recorded; "
                     "speedup not computable.")
    lines.append("")
    return "\n".join(lines)


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(description="Compare two benchmark reports")
    parser.add_argument("serial_json")
    parser.add_argument("parallel_json")
    parser.add_argument("--out", default=None)
    parser.add_argument("--json", dest="emit_json", action="store_true")
    args = parser.parse_args(argv)

    try:
        with open(args.serial_json, encoding="utf-8") as fh:
            serial = json.load(fh)
        with open(args.parallel_json, encoding="utf-8") as fh:
            parallel = json.load(fh)
    except (OSError, ValueError) as exc:
        print("COMPARE: %s" % exc, file=sys.stderr)
        return 2

    result = compare_reports(serial, parallel)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
            fh.write("\n")
    if args.emit_json:
        print(json.dumps(result, indent=2))
    else:
        print(render_compare_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
