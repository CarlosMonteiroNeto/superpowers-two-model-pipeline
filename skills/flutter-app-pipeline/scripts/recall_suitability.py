"""Batch Jev suitability judgments layered over deterministic template recall.

The catalog and freshness rules remain authoritative.  This module only
filters an already eligible, deterministic shortlist when Site 2 is explicitly
configured for calibrated active mode.  It never changes catalog rows,
timestamps, scoring verdicts, or the live-search boundary.
"""

import argparse
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path


_SHARED = Path(__file__).resolve().parents[2] / "two-model-sdd-pipeline" / "scripts"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

import jev_classify  # noqa: E402
import jev_policy  # noqa: E402
import jev_store  # noqa: E402


MAX_QUESTIONS = 32
MAX_PAYLOAD_BYTES = 64 * 1024
SITE = "site2"
SCHEMA_VERSION = "site2-v1"
CHOICES = ("suitable", "unsuitable", "needs_review")


class SuitabilitySetupError(ValueError):
    """The recall boundary or suitability input cannot be evaluated."""


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def schema_hash(schema):
    return hashlib.sha256(_canonical(schema).encode("utf-8")).hexdigest()


def _policy_identity(policy):
    return hashlib.sha256(_canonical(policy).encode("utf-8")).hexdigest()


def _normalise_input(candidates, context):
    """Return deterministic status and rows without changing caller data."""
    if isinstance(candidates, dict):
        deterministic_status = candidates.get("status", candidates.get("verdict"))
        rows = candidates.get("results", candidates.get("candidates", []))
        if deterministic_status == "SETUP_ERROR":
            raise SuitabilitySetupError("deterministic recall reported SETUP_ERROR")
        if deterministic_status not in (None, "HIT", "MISS"):
            raise SuitabilitySetupError("unknown deterministic recall status")
    else:
        deterministic_status = None
        rows = candidates
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise SuitabilitySetupError("candidates must be a list of objects")
    if not isinstance(context, dict):
        raise SuitabilitySetupError("context must be an object")
    if deterministic_status is None:
        deterministic_status = "HIT" if rows else "MISS"
    if deterministic_status == "HIT" and not rows:
        # A caller cannot claim a deterministic HIT with no shortlist.
        deterministic_status = "MISS"
    return deterministic_status, [dict(row) for row in rows]


def _candidate_id(index):
    return "candidate_{}".format(index)


def _candidate_state(rows, context):
    # Preserve complete evidence and context.  Questions point to these stable
    # paths instead of embedding or truncating candidate text in instructions.
    return {
        "request": context,
        "candidates": {
            _candidate_id(index): {
                "state_path": "state.candidates.{}".format(_candidate_id(index)),
                "candidate": row,
            }
            for index, row in enumerate(rows)
        },
    }


def build_schema(rows, context, *, model="jev"):
    """Build the versioned Choice schema for one deterministic shortlist."""
    del context  # Context travels in state so the request remains auditable.
    questions = {}
    for index in range(len(rows)):
        candidate_id = _candidate_id(index)
        questions[candidate_id] = {
            "type": "choice",
            "instructions": (
                "Assess the candidate at state.candidates.{} for the current project. "
                "Use the Category Skeleton, intended use, declared dependencies, and "
                "the candidate's stored scoring evidence. Judge suitability for this "
                "project, not freshness."
            ).format(candidate_id),
            "criteria": {
                "suitable": "The candidate fits the current project and its stated constraints.",
                "unsuitable": "The candidate does not fit the current project or violates a stated constraint.",
                "needs_review": "The available evidence is insufficient or ambiguous for a confident suitability judgment.",
            },
        }
    return {"version": SCHEMA_VERSION, "model": model, "questions": questions}


def _judgment_base(index, row):
    return {
        "candidate_index": index,
        "state_path": "state.candidates.{}".format(_candidate_id(index)),
        "owner_repo": row.get("owner_repo"),
        "choice": "needs_review",
        "confidence": None,
        "status": "unevaluated",
        "selected": False,
    }


def _policy_calibrated(policy, schema):
    threshold = policy.get("threshold")
    report = policy.get("calibration_report")
    required = ("site", "model", "schema_hash", "threshold", "evaluator")
    if (
        policy.get("site") != SITE
        or not isinstance(policy.get("model"), str)
        or policy.get("model") != schema.get("model")
        or not isinstance(threshold, (int, float))
        or isinstance(threshold, bool)
        or not math.isfinite(float(threshold))
        or not 0 <= threshold <= 1
        or not isinstance(policy.get("schema_hash"), str)
        or policy.get("schema_hash") != schema_hash(schema)
        or not isinstance(policy.get("evaluator"), str)
        or not policy.get("evaluator")
        or not isinstance(report, dict)
        or any(not report.get(key) for key in required)
    ):
        return False
    return (
        report.get("site") == SITE
        and report.get("model") == schema.get("model")
        and report.get("schema_hash") == schema_hash(schema)
        and report.get("threshold") == threshold
        and report.get("evaluator") == policy.get("evaluator")
    )


def _budget_reason(schema, state, rows):
    if len(rows) > MAX_QUESTIONS:
        return "question_budget_exceeded"
    payload = {"model": schema.get("model"), "state": state, "questions": schema.get("questions")}
    if len(_canonical(payload).encode("utf-8")) > MAX_PAYLOAD_BYTES:
        return "payload_budget_exceeded"
    return None


def _write_advisory(workspace, identity, policy, report, envelope, started):
    if not isinstance(workspace, str) or not workspace:
        return
    try:
        jev_store.write_record(workspace, SITE, identity, {
            "state_identity": identity,
            "policy_identity": _policy_identity(policy),
            "decision": report.get("verdict"),
            "actual_action": report.get("actual_action", "deterministic_recall"),
            "fallback": report.get("fallback_reason"),
            "timing": {"duration_ms": int((time.monotonic() - started) * 1000)},
            "usage": (envelope or {}).get("usage"),
        })
    except (OSError, TypeError, ValueError, RuntimeError):
        # Advisory persistence cannot turn an optional Jev hook into a
        # pipeline failure.  The returned report still carries telemetry.
        return


def _base_report(deterministic_status, rows, judgments, *, mode, fallback_reason=None):
    return {
        "site": SITE,
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "deterministic_verdict": deterministic_status,
        "deterministic_candidates": [dict(row) for row in rows],
        "verdict": deterministic_status,
        "status": deterministic_status,
        "candidates": [dict(row) for row in rows],
        "judgments": judgments,
        "fallback_reason": fallback_reason,
        "actual_action": "deterministic_recall",
        "inference_status": "not_run",
        "provider_error": None,
        "usage": None,
    }


def _finish(report, *, workspace, policy, identity, envelope, started):
    report["duration_ms"] = int((time.monotonic() - started) * 1000)
    report["request_hash"] = identity
    report["cache_hit"] = bool((envelope or {}).get("cache_hit"))
    if isinstance(envelope, dict) and envelope.get("schema_hash"):
        report["schema_hash"] = envelope["schema_hash"]
    _write_advisory(workspace, identity, policy, report, envelope, started)
    return report


def _response_config_mismatch(policy, schema, envelope):
    """Return response/policy identity mismatches before active filtering."""
    response = envelope if isinstance(envelope, dict) else {}
    expected_model = schema.get("model")
    expected_schema = schema_hash(schema)
    mismatches = {}
    if response.get("model") != expected_model:
        mismatches["model"] = {"expected": expected_model, "actual": response.get("model")}
    if response.get("schema_hash") != expected_schema:
        mismatches["schema_hash"] = {"expected": expected_schema, "actual": response.get("schema_hash")}
    if policy.get("model") != expected_model:
        mismatches["policy_model"] = {"expected": expected_model, "actual": policy.get("model")}
    if policy.get("schema_hash") != expected_schema:
        mismatches["policy_schema_hash"] = {"expected": expected_schema, "actual": policy.get("schema_hash")}
    return mismatches


def _finish_deterministic_fallback(report, *, workspace, policy, identity, envelope, started,
                                   fallback_reason, inference_status, error=None):
    """Keep deterministic recall authoritative when optional Jev cannot apply."""
    report["fallback_reason"] = fallback_reason
    report["inference_status"] = inference_status
    report["actual_action"] = "deterministic_recall"
    if error is not None:
        report["provider_error"] = error
    for judgment in report["judgments"]:
        judgment["status"] = fallback_reason
        judgment["selected"] = False
    return _finish(report, workspace=workspace, policy=policy, identity=identity, envelope=envelope, started=started)


def assess(candidates, context, *, workspace, policy_path=None):
    """Assess a deterministic shortlist using Site 2's conservative policy."""
    started = time.monotonic()
    deterministic_status, rows = _normalise_input(candidates, context)
    policy = jev_policy.read_policy(policy_path, SITE)
    mode = policy.get("mode", "shadow")
    model = policy.get("model", "jev")
    if not isinstance(model, str) or not model:
        model = "jev"
    schema = build_schema(rows, context, model=model)
    state = _candidate_state(rows, context)
    identity = hashlib.sha256(_canonical({"schema": schema, "state": state, "policy": policy}).encode("utf-8")).hexdigest()
    judgments = [_judgment_base(index, row) for index, row in enumerate(rows)]
    report = _base_report(deterministic_status, rows, judgments, mode=mode)
    report["schema_hash"] = schema_hash(schema)
    if policy.get("policy_error"):
        report["policy_error"] = policy["policy_error"]

    if not rows:
        report["fallback_reason"] = "zero_eligible_candidates"
        report["inference_status"] = "not_run"
        return _finish(report, workspace=workspace, policy=policy, identity=identity, envelope=None, started=started)

    if mode == "off":
        report["fallback_reason"] = "policy_off"
        report["inference_status"] = "off"
        for judgment in judgments:
            judgment["status"] = "off"
        return _finish(report, workspace=workspace, policy=policy, identity=identity, envelope=None, started=started)

    if mode == "active" and not _policy_calibrated(policy, schema):
        report["fallback_reason"] = "uncalibrated_policy"
        report["inference_status"] = "uncalibrated"
        for judgment in judgments:
            judgment["status"] = "uncalibrated"
        return _finish(report, workspace=workspace, policy=policy, identity=identity, envelope=None, started=started)

    budget_reason = _budget_reason(schema, state, rows)
    if budget_reason:
        report["fallback_reason"] = budget_reason
        report["inference_status"] = "unevaluated"
        for judgment in judgments:
            judgment["status"] = "unevaluated"
        return _finish(report, workspace=workspace, policy=policy, identity=identity, envelope=None, started=started)

    code, envelope = jev_classify.classify(
        schema,
        state,
        workspace=workspace,
        site=SITE,
        threshold=policy.get("threshold", 0.9),
    )
    if not isinstance(envelope, dict):
        envelope = {}
    report["classifier_exit_code"] = code
    report["usage"] = envelope.get("usage")
    if code == 2:
        return _finish_deterministic_fallback(
            report,
            workspace=workspace,
            policy=policy,
            identity=identity,
            envelope=envelope,
            started=started,
            fallback_reason="classifier_setup_error",
            inference_status="setup_error",
            error=envelope.get("error") or "invalid suitability input",
        )
    report["inference_status"] = envelope.get("status", "answered")
    report["provider_error"] = envelope.get("error")
    report["schema_hash"] = envelope.get("schema_hash") or report["schema_hash"]

    # ``jev_classify`` uses exit 1 for an open circuit as well as for valid
    # low-confidence answers.  The envelope status is authoritative for that
    # distinction: an open/unavailable provider must never turn a deterministic
    # HIT into a semantic MISS.
    provider_status = envelope.get("status") if isinstance(envelope, dict) else None
    if code == 3 or provider_status in {"unavailable", "circuit_open"}:
        report["fallback_reason"] = "provider_unavailable"
        for judgment in judgments:
            judgment["status"] = "provider_unavailable"
        return _finish(report, workspace=workspace, policy=policy, identity=identity, envelope=envelope, started=started)

    # Active mode may filter only a response bound to the calibrated policy
    # and the exact schema sent to the provider.  A mismatched envelope is an
    # optional-hook failure, so preserve deterministic recall and its rows.
    if mode == "active":
        mismatch = _response_config_mismatch(policy, schema, envelope)
        if mismatch:
            report["config_mismatch"] = mismatch
            return _finish_deterministic_fallback(
                report,
                workspace=workspace,
                policy=policy,
                identity=identity,
                envelope=envelope,
                started=started,
                fallback_reason="provider_config_mismatch",
                inference_status="config_mismatch",
                error="Jev response does not match the calibrated model or schema",
            )

    answers = envelope.get("answers") if isinstance(envelope, dict) else {}
    answers = answers if isinstance(answers, dict) else {}
    threshold = policy.get("threshold", 0.9)
    uncertain = False
    suitable_count = 0
    unsuitable_count = 0
    for index, row in enumerate(rows):
        judgment = judgments[index]
        answer = answers.get(_candidate_id(index))
        if not isinstance(answer, dict):
            judgment["status"] = "uncertain"
            uncertain = True
            continue
        choice = answer.get("choice")
        confidence = answer.get("confidence")
        judgment["choice"] = choice if choice in CHOICES else "needs_review"
        judgment["confidence"] = confidence
        judgment["probabilities"] = answer.get("probabilities")
        confident = isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and math.isfinite(float(confidence)) and confidence >= threshold
        if choice not in CHOICES or not confident:
            judgment["status"] = "uncertain"
            uncertain = True
            continue
        judgment["status"] = "answered"
        if choice == "suitable":
            suitable_count += 1
        elif choice == "unsuitable":
            unsuitable_count += 1
        if mode == "active" and choice == "suitable":
            judgment["selected"] = True

    if mode != "active":
        report["fallback_reason"] = "shadow"
        report["inference_status"] = "answered" if code == 0 else "uncertain"
        return _finish(report, workspace=workspace, policy=policy, identity=identity, envelope=envelope, started=started)

    selected = [row for index, row in enumerate(rows) if judgments[index]["selected"]]
    report["candidates"] = [dict(row) for row in selected]
    report["verdict"] = "HIT" if selected else "MISS"
    report["status"] = report["verdict"]
    report["actual_action"] = "active_suitability_filter"
    if selected:
        report["fallback_reason"] = "per_answer_uncertainty" if uncertain else None
    elif unsuitable_count == len(rows) and not uncertain:
        report["fallback_reason"] = "all_candidates_unsuitable_live_search"
    else:
        report["fallback_reason"] = "per_answer_uncertainty_live_search"
    return _finish(report, workspace=workspace, policy=policy, identity=identity, envelope=envelope, started=started)


def _write_output(path, report):
    Path(path).write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="recall-suitability")
    parser.add_argument("candidates_file")
    parser.add_argument("context_file")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--policy")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        candidates = json.loads(Path(args.candidates_file).read_text(encoding="utf-8"))
        context = json.loads(Path(args.context_file).read_text(encoding="utf-8"))
        report = assess(candidates, context, workspace=args.workspace, policy_path=args.policy)
        _write_output(args.output, report)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return {"HIT": 0, "MISS": 2, "SETUP_ERROR": 1}[report["verdict"]]
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print("recall-suitability: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
