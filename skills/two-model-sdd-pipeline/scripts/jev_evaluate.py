"""Offline Jev evaluation. It reports evidence and never changes policies."""
import json


def evaluate(reports, labels):
    answers = {}
    usage = {"input_tokens": 0, "output_tokens": 0}
    timings = []
    for report in reports:
        request = report.get("request_hash")
        for question, answer in report.get("answers", {}).items():
            answers[(request, question)] = answer
        reported_usage = report.get("usage")
        if not isinstance(reported_usage, dict):
            reported_usage = {}
        for key in usage:
            usage[key] += reported_usage.get(key, 0) or 0
        if isinstance(report.get("duration_ms"), (int, float)):
            timings.append(report["duration_ms"])
    agreement = 0
    false_positive = []
    executed = 0
    missing = []
    for label in labels:
        key = (label.get("request_hash"), label.get("question_id"))
        answer = answers.get(key)
        identity = "%s:%s" % key
        if answer is None:
            missing.append(identity + ": recommendation missing")
            continue
        if label.get("actual_decision") == answer.get("choice"):
            agreement += 1
        elif answer.get("choice") not in (None, "needs_review"):
            false_positive.append(identity)
        if label.get("actual_action") in ("selected-apply", "applied", "executed"):
            if label.get("outcome") is None or not label.get("evidence_refs"):
                missing.append(identity + ": execution evidence missing")
            else:
                executed += 1
        else:
            missing.append(identity + ": no executed outcome")
    matched_labels = sum(1 for label in labels if (label.get("request_hash"), label.get("question_id")) in answers)
    return {"recommendation_agreement": {"count": matched_labels, "agreements": agreement, "coverage": {"answered": len(answers), "labeled": len(labels), "matched": matched_labels}},
            "executed_outcomes": {"count": executed, "labeled": sum(1 for label in labels if label.get("actual_action") in ("selected-apply", "applied", "executed"))}, "false_positive_labels": false_positive,
            "usage": usage, "timing_ms": timings, "missing_evidence": missing}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="jev-evaluate")
    parser.add_argument("reports_json")
    parser.add_argument("labels_json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        with open(args.reports_json, encoding="utf-8") as h: reports = json.load(h)
        with open(args.labels_json, encoding="utf-8") as h: labels = json.load(h)
        if not isinstance(reports, list) or not isinstance(labels, list): raise ValueError("inputs must be arrays")
        with open(args.output, "w", encoding="utf-8") as h: json.dump(evaluate(reports, labels), h, indent=2); h.write("\n")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("jev-evaluate: " + str(exc), file=__import__("sys").stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
