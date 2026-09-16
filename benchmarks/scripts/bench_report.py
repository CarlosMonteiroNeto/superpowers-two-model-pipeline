#!/usr/bin/env python3
"""Benchmark analyzer: turn pipeline artifacts into per-stage metrics.

Reads one pipeline run's workspace (the JSONL ledger plus the per-task
dispatch JSON event logs) and derives, per task and per role:

  * tokens split into uncached input, output, reasoning, cache read, and
    cache write (the ``tokens`` block of each ``step_finish`` event);
  * the number of LLM requests (one ``step_finish`` event == one API call);
  * the role's wall-clock span (first to last event in the log);
  * stage durations reconstructed from the ledger timeline
    (brief, gate) and correction rounds.

It also aggregates per role and overall, and computes the cache-hit
percentage and the "pure" uncached token count. No LLM, no network: the
analyzer only reads files, so it can never perturb a run it measures.

The result is a plain dict (JSON-serializable); ``render_markdown`` turns
it into the human report. ``analyze_workspace`` raises ``OSError`` when the
workspace has no ledger.
"""
import datetime
import glob
import json
import os
import re

ROLES = ("coder", "reviewer", "director")
LOG_RE = re.compile(r"task-(\d+)-(coder|reviewer)\.log$")


def _zero():
    return {
        "input": 0,
        "output": 0,
        "reasoning": 0,
        "cache_read": 0,
        "cache_write": 0,
        "cost": 0.0,
        "requests": 0,
        "span_s": 0.0,
    }


def _add(dst, src):
    dst["input"] += src["input"]
    dst["output"] += src["output"]
    dst["reasoning"] += src["reasoning"]
    dst["cache_read"] += src["cache_read"]
    dst["cache_write"] += src["cache_write"]
    dst["cost"] += src["cost"]
    dst["requests"] += src["requests"]
    dst["span_s"] = round(dst["span_s"] + src["span_s"], 3)


def _scan_log(path):
    """Return (metrics, first_ms, last_ms) for one dispatch JSON event log."""
    metrics = _zero()
    first_ts = None
    last_ts = None
    if not path or not os.path.isfile(path):
        return metrics, None, None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            ts = event.get("timestamp")
            if isinstance(ts, (int, float)):
                first_ts = ts if first_ts is None else min(first_ts, ts)
                last_ts = ts if last_ts is None else max(last_ts, ts)
            if event.get("type") != "step_finish":
                continue
            # opencode nests tokens/cost inside `part`; tolerate a top-level
            # shape too so the analyzer is robust to either emission.
            part = event.get("part")
            part = part if isinstance(part, dict) else {}
            tokens = event.get("tokens") or part.get("tokens") or {}
            cache = tokens.get("cache") or {}
            metrics["input"] += int(tokens.get("input") or 0)
            metrics["output"] += int(tokens.get("output") or 0)
            metrics["reasoning"] += int(tokens.get("reasoning") or 0)
            metrics["cache_read"] += int(cache.get("read") or 0)
            metrics["cache_write"] += int(cache.get("write") or 0)
            cost = event.get("cost")
            if cost is None:
                cost = part.get("cost")
            metrics["cost"] += float(cost or 0.0)
            metrics["requests"] += 1
    if first_ts is not None and last_ts is not None:
        metrics["span_s"] = round((last_ts - first_ts) / 1000.0, 3)
    return metrics, first_ts, last_ts


def parse_log(path):
    """Derive usage metrics from one dispatch JSON event log."""
    metrics, _, _ = _scan_log(path)
    return metrics


def _parse_ts(value):
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.datetime.fromisoformat(text)
    except ValueError:
        return None


def load_ledger(path):
    entries = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict):
                entries.append(entry)
    return entries


def _entry_ts(entry):
    return _parse_ts(entry.get("ts"))


def _last_round(entries):
    best = 0
    for entry in entries:
        if entry.get("type") != "coder_round":
            continue
        try:
            best = max(best, int(entry.get("ROUND") or 0))
        except (TypeError, ValueError):
            continue
    return best


def _status(entries):
    verdict = ""
    for entry in entries:
        if entry.get("type") == "review_outcome":
            verdict = str(entry.get("verdict") or entry.get("summary") or "")
    if not verdict:
        for entry in entries:
            if entry.get("type") == "task_complete":
                verdict = str(entry.get("verdict") or "COMPLETE")
    return verdict or "UNKNOWN"


def _delta_s(start_entry, end_entry):
    start = _entry_ts(start_entry) if start_entry else None
    end = _entry_ts(end_entry) if end_entry else None
    if start is None or end is None:
        return None
    return round((end - start).total_seconds(), 3)


def _first_of(entries, type_):
    for entry in entries:
        if entry.get("type") == type_:
            return entry
    return None


def _last_of(entries, type_):
    found = None
    for entry in entries:
        if entry.get("type") == type_:
            found = entry
    return found


def analyze_workspace(workspace, total_seconds=None, side=None):
    workspace = str(workspace)
    ledger_path = os.path.join(workspace, "ledger.jsonl")
    if not os.path.isfile(ledger_path):
        raise OSError("no ledger at %s" % ledger_path)
    entries = load_ledger(ledger_path)

    by_task = {}
    for entry in entries:
        task = str(entry.get("task") or "")
        if task.isdigit():
            by_task.setdefault(task, []).append(entry)

    task_ids = {int(k) for k in by_task}
    for path in glob.glob(os.path.join(workspace, "task-*-coder.log")):
        match = LOG_RE.search(path.replace("\\", "/"))
        if match:
            task_ids.add(int(match.group(1)))

    tasks = []
    role_totals = {role: _zero() for role in ROLES}
    for task_id in sorted(task_ids):
        task_entries = by_task.get(str(task_id), [])
        coder_path = os.path.join(workspace, "task-%d-coder.log" % task_id)
        coder, _, coder_end_ms = _scan_log(coder_path)
        reviewer = parse_log(os.path.join(workspace, "task-%d-reviewer.log" % task_id))
        _add(role_totals["coder"], coder)
        _add(role_totals["reviewer"], reviewer)

        rounds = _last_round(task_entries)
        commit = _last_of(task_entries, "commit")
        brief = _first_of(task_entries, "brief_ready")
        red = _first_of(task_entries, "red_check")

        # The script gate window: from the operador dispatch ending (its log's
        # last event) to the commit. coder-gate ledgers coder_round AFTER the
        # flutter green-gate commits, so the round entry cannot bound it.
        gate_s = None
        commit_dt = _entry_ts(commit) if commit else None
        if commit_dt is not None and coder_end_ms is not None:
            delta = round(commit_dt.timestamp() - coder_end_ms / 1000.0, 3)
            gate_s = delta if delta >= 0 else None

        tasks.append({
            "id": task_id,
            "status": _status(task_entries),
            "correction_rounds": max(0, rounds - 1),
            "brief_s": _delta_s(brief, red),
            "gate_s": gate_s,
            "roles": {"coder": coder, "reviewer": reviewer},
        })

    for path in sorted(glob.glob(os.path.join(workspace, "task-generator-*.log"))):
        _add(role_totals["director"], parse_log(path))

    totals = _zero()
    for role in ROLES:
        _add(totals, role_totals[role])

    denom = totals["cache_read"] + totals["input"]
    cache_hit_pct = round(100.0 * totals["cache_read"] / denom, 1) if denom else 0.0
    uncached_tokens = totals["input"] + totals["output"] + totals["reasoning"]

    if total_seconds is None:
        stamps = [_entry_ts(e) for e in entries]
        stamps = [s for s in stamps if s is not None]
        total_seconds = round((max(stamps) - min(stamps)).total_seconds(), 3) if stamps else 0.0
    else:
        total_seconds = round(float(total_seconds), 3)

    return {
        "side": side or os.path.basename(workspace),
        "workspace": workspace,
        "total_wall_clock_s": total_seconds,
        "cache_hit_pct": cache_hit_pct,
        "uncached_tokens": uncached_tokens,
        "totals": totals,
        "roles": role_totals,
        "tasks": tasks,
    }


def render_markdown(result):
    lines = []
    lines.append("# Benchmark report — %s" % result["side"])
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append("| Total wall-clock (s) | %.1f |" % result["total_wall_clock_s"])
    lines.append("| LLM requests | %d |" % result["totals"]["requests"])
    lines.append("| Cache-hit %% | %.1f |" % result["cache_hit_pct"])
    lines.append("| Uncached tokens (in+out+reasoning) | %d |" % result["uncached_tokens"])
    lines.append("| Cache read tokens | %d |" % result["totals"]["cache_read"])
    lines.append("| Cache write tokens | %d |" % result["totals"]["cache_write"])
    lines.append("| Cost | %.6f |" % result["totals"]["cost"])
    lines.append("")
    lines.append("## Per role")
    lines.append("")
    lines.append("| Role | Requests | Input | Output | Reasoning | Cache read | Span (s) |")
    lines.append("|---|---|---|---|---|---|---|")
    for role in ROLES:
        data = result["roles"][role]
        lines.append("| %s | %d | %d | %d | %d | %d | %.1f |" % (
            role, data["requests"], data["input"], data["output"],
            data["reasoning"], data["cache_read"], data["span_s"]))
    lines.append("")
    lines.append("## Per task")
    lines.append("")
    lines.append("| Task | Status | Rounds | Brief (s) | Gate (s) | Coder req | Coder span (s) | Reviewer req | Reviewer span (s) |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for task in result["tasks"]:
        coder = task["roles"]["coder"]
        reviewer = task["roles"]["reviewer"]
        lines.append("| %s | %s | %d | %s | %s | %d | %.1f | %d | %.1f |" % (
            task["id"], task["status"], task["correction_rounds"],
            _fmt(task["brief_s"]), _fmt(task["gate_s"]),
            coder["requests"], coder["span_s"],
            reviewer["requests"], reviewer["span_s"]))
    lines.append("")
    return "\n".join(lines)


def _fmt(value):
    return "-" if value is None else "%.1f" % value


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(description="Benchmark analyzer")
    parser.add_argument("workspace")
    parser.add_argument("--side", default=None)
    parser.add_argument("--total-seconds", type=float, default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--json", dest="emit_json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = analyze_workspace(args.workspace, args.total_seconds, args.side)
    except OSError as exc:
        print("REPORT: %s" % exc, file=os.sys.stderr)
        return 2

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
            fh.write("\n")
    if args.emit_json:
        print(json.dumps(result, indent=2))
    else:
        print(render_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(os.sys.argv[1:]))
