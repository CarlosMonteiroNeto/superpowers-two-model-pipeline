"""Policy parsing and conservative action selection for Jev advisory sites."""
import json
import math


VALID_SITES = {"site1", "site2", "site3", "site4", "site5"}


def read_policy(path, site):
    if site not in VALID_SITES:
        raise ValueError("unknown Jev site")
    policy = {"site": site, "mode": "shadow", "threshold": 0.9}
    if not path:
        return policy
    try:
        with open(path, encoding="utf-8") as handle:
            configured = json.load(handle)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        policy["policy_error"] = str(exc)
        return policy
    if not isinstance(configured, dict):
        policy["policy_error"] = "policy must be an object"
        return policy
    policy.update(configured)
    if policy.get("site") != site:
        policy["mode"] = "shadow"
        policy["policy_error"] = "policy site mismatch"
    allowed = {"shadow", "selected-apply"} if site == "site5" else {"off", "shadow", "active"}
    if policy.get("mode") not in allowed:
        policy["mode"] = "shadow"
        policy["policy_error"] = "invalid mode"
    return policy


def _calibrated(policy, envelope):
    report = policy.get("calibration_report")
    required = ("site", "model", "schema_hash", "threshold", "evaluator")
    threshold = policy.get("threshold")
    if (not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or not 0 <= threshold <= 1
            or not isinstance(report, dict) or any(not report.get(key) for key in required)):
        return False
    return (report["site"] == policy.get("site") and policy.get("model") == envelope.get("model")
            and policy.get("schema_hash") == envelope.get("schema_hash")
            and report["model"] == envelope.get("model") and report["schema_hash"] == envelope.get("schema_hash")
            and report["threshold"] == policy.get("threshold")
            and report["evaluator"] == policy.get("evaluator"))


def select_action(policy, question_id, envelope, fallback):
    mode = policy.get("mode", "shadow")
    if mode == "off":
        return fallback
    if policy.get("site") == "site5":
        return "selected-apply" if mode == "selected-apply" else fallback
    if mode != "active" or not _calibrated(policy, envelope):
        policy["effective_mode"] = "shadow"
        return fallback
    answer = envelope.get("answers", {}).get(question_id, {})
    confidence = answer.get("confidence")
    if not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or confidence < policy["threshold"]:
        return fallback
    return answer.get("choice", fallback)
