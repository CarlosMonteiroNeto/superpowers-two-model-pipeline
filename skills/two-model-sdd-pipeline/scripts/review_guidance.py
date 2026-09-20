"""Prepare advisory depth guidance for the mandatory Site 4 review.

The reviewer remains the only semantic approval authority.  This module only
chooses between procedural ``focused_review`` and ``standard_review``
instructions; it never emits a verdict, writes the pipeline ledger, or
changes the reviewer dispatch.
"""

import argparse
import hashlib
import json
import math
import os
import pathlib
import sys
import tempfile
import time

import jev_classify
import jev_policy
import jev_store


SITE = "site4"
QUESTION_ID = "review_depth"
CHOICES = ("focused_review", "standard_review")
# Site 4 has its own minimum confidence floor.  A runtime policy may use a
# lower classifier threshold for experimentation, but it cannot lower the
# confidence required before procedural focus guidance is appended.
MIN_FOCUSED_CONFIDENCE = 0.9
MAX_PAYLOAD_BYTES = 64 * 1024
SCHEMA_PATH = pathlib.Path(__file__).resolve().parent.parent / "schemas" / "jev-site-4.json"


class RequiredArtifactError(Exception):
    """The pre-existing review package could not be read or saved."""


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _digest(value):
    if isinstance(value, bytes):
        return hashlib.sha256(value).hexdigest()
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _task_id(value):
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("task must be a positive integer") from exc
    if number <= 0:
        raise ValueError("task must be a positive integer")
    return number


def _read_package(path):
    path = pathlib.Path(path)
    try:
        raw = path.read_bytes()
    except (OSError, ValueError) as exc:
        raise RequiredArtifactError(f"cannot read review package: {path}: {exc}") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw, None
    return raw, text


def _without_guidance(raw):
    """Return the original package bytes before a previous guidance append."""
    marker = b"\n## Review Guidance\n\nGuidance mode:"
    position = raw.rfind(marker)
    return raw if position < 0 else raw[:position]


def _read_json(path):
    try:
        with pathlib.Path(path).open(encoding="utf-8") as handle:
            value = json.load(handle)
        return value
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return None


def _find_task(plan, task_id):
    if not isinstance(plan, dict) or not isinstance(plan.get("tasks"), list):
        return None
    for task in plan["tasks"]:
        if isinstance(task, dict) and str(task.get("id")) == str(task_id):
            return task
    return None


def _ledger_entries(workspace, task_id=None):
    """Read advisory context without treating it as an authoritative input."""
    root = pathlib.Path(workspace)
    paths = [root / "ledger.jsonl"]
    if task_id is not None:
        paths.append(root / f"ledger-task-{task_id}.jsonl")
    paths.extend(sorted(root.glob("ledger-*.jsonl")))
    entries = []
    seen = set()
    for path in paths:
        try:
            key = path.resolve()
        except OSError:
            key = path
        if key in seen:
            continue
        seen.add(key)
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                value = json.loads(line)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                entries.append(value)
    return entries


def _extract_section(text, heading, next_heading=None):
    if not isinstance(text, str):
        return None
    marker = heading + "\n"
    start = text.find(marker)
    if start < 0:
        return None
    start += len(marker)
    end = len(text)
    if next_heading:
        candidate = text.find("\n" + next_heading, start)
        if candidate >= 0:
            end = candidate + 1
    value = text[start:end]
    return value.strip("\r\n")


def _evidence(raw, text, workspace, task_id):
    """Validate package shape while preserving all bytes for a valid request."""
    base = _without_guidance(raw)
    if text is None:
        return {
            "complete": False,
            "reason": "incomplete_evidence",
            "bytes": len(base),
            "package": None,
            "task_brief": None,
            "review_diff": None,
        }
    base_text = base.decode("utf-8")
    required = ("# Review package:", "## Commits", "## Files changed", "## Diff")
    complete = all(marker in base_text for marker in required)
    task_brief = _extract_section(base_text, "## Task Brief", "## Commits")
    # A package made by review-package has the brief inline.  If it was not
    # available, preserve the existing package but decline focused inference.
    brief_file = pathlib.Path(workspace) / f"task-{task_id}-brief.md"
    if brief_file.is_file() and not task_brief:
        complete = False
    if task_brief is None or not task_brief.strip():
        complete = False
    review_diff = _extract_section(base_text, "## Diff")
    if review_diff is None or not review_diff.strip():
        complete = False
    reason = None if complete else "incomplete_evidence"
    if len(base) > MAX_PAYLOAD_BYTES:
        reason = "evidence_too_large"
        complete = False
    return {
        "complete": complete,
        "reason": reason,
        "bytes": len(base),
        "package": base_text,
        "task_brief": task_brief,
        "review_diff": review_diff,
    }


def _exclusions(workspace, task_id, task, entries):
    reasons = []
    if isinstance(task, dict):
        if "corrects" in task and task.get("corrects") is not None:
            reasons.append("corrective_task")
        if "fused_from" in task and task.get("fused_from") is not None:
            reasons.append("fused_from")
        if task.get("interface_touched"):
            reasons.append("interface_touched")
    for entry in entries:
        if (str(entry.get("task")) == str(task_id)
                and entry.get("type") == "interface_touched"):
            reasons.append("interface_touched")
    # These markers are part of a generated plan/brief and provide a safe
    # fallback when a disposable workspace does not include plan.json.
    if isinstance(task, dict) and task.get("corrects") is not None:
        pass
    return sorted(set(reasons))


def _load_schema():
    schema = _read_json(SCHEMA_PATH)
    if not isinstance(schema, dict) or not isinstance(schema.get("questions"), dict):
        raise ValueError("Site 4 schema is invalid")
    question = schema["questions"].get(QUESTION_ID)
    if not isinstance(question, dict) or set(question.get("criteria", {})) != set(CHOICES):
        raise ValueError("Site 4 schema choices are invalid")
    return schema


def _policy_calibrated(policy, schema):
    """Check the active policy binding before spending an inference attempt."""
    threshold = policy.get("threshold")
    report = policy.get("calibration_report")
    required = ("site", "model", "schema_hash", "threshold", "evaluator")
    if (policy.get("site") != SITE or policy.get("mode") != "active"
            or not isinstance(policy.get("model"), str)
            or policy.get("model") != schema.get("model")
            or not isinstance(policy.get("schema_hash"), str)
            or policy.get("schema_hash") != _digest(schema)
            or not isinstance(policy.get("evaluator"), str)
            or not policy.get("evaluator")
            or not isinstance(threshold, (int, float))
            or isinstance(threshold, bool) or not math.isfinite(float(threshold))
            or not 0 <= threshold <= 1 or not isinstance(report, dict)
            or any(not report.get(key) for key in required)):
        return False
    return (
        report.get("site") == SITE
        and report.get("model") == schema.get("model")
        and report.get("schema_hash") == _digest(schema)
        and report.get("threshold") == threshold
        and report.get("evaluator") == policy.get("evaluator")
    )


def _answer(envelope):
    if not isinstance(envelope, dict):
        return None, None
    answers = envelope.get("answers")
    answer = answers.get(QUESTION_ID) if isinstance(answers, dict) else None
    if not isinstance(answer, dict) or answer.get("choice") not in CHOICES:
        return None, None
    confidence = answer.get("confidence")
    if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence) or not 0 <= confidence <= 1):
        confidence = None
    return answer["choice"], confidence


def _state(evidence, workspace, task_id, plan, task, interface_entries, exclusions):
    corrective = task.get("corrects") if isinstance(task, dict) else None
    fused = task.get("fused_from") if isinstance(task, dict) else None
    return {
        "site": SITE,
        "task_id": task_id,
        "workspace": os.path.normcase(os.path.realpath(os.path.abspath(str(workspace)))),
        "task_brief": evidence.get("task_brief"),
        "review_diff": evidence.get("review_diff"),
        "package_bytes": evidence.get("bytes"),
        "task": task,
        "interface_advisory": interface_entries,
        "corrective_context": {
            "corrects": corrective,
            "fused_from": fused,
            "excluded": bool(exclusions),
        },
        "deterministic_exclusions": exclusions,
        "plan_context": plan if isinstance(plan, dict) else None,
    }


def _atomic_write(path, data):
    path = pathlib.Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".review-guidance-", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    except (OSError, UnicodeError) as exc:
        raise RequiredArtifactError(f"cannot write review package: {path}: {exc}") from exc


def _guidance_text(result):
    mode = result.get("actual_action", "standard_review")
    lines = [
        "## Review Guidance",
        "",
        f"Guidance mode: {mode}",
        "",
        "Read the complete task brief and full review diff, including tests and "
        "the available interface-touch and corrective context.",
        "Perform all four mandatory review duties: spec compliance, architecture, "
        "interface discipline, and tests versus acceptance.",
        "Use the existing JSON verdict schema and approval criteria. This section "
        "changes procedural emphasis only; the reviewer remains the sole semantic "
        "approval authority and must make the verdict from the evidence.",
        "",
    ]
    if mode == "focused_review":
        lines.extend([
            "Identify one named risk in the supplied diff and inspect that risk "
            "deeply first, then complete every mandatory duty and retain the full "
            "evidence before returning the verdict.",
            "",
        ])
    else:
        lines.extend([
            "Use the standard review sequence across the complete evidence and "
            "deepen inspection whenever the diff identifies a named risk.",
            "",
        ])
    return "\n".join(lines).encode("utf-8")


def _write_advisory(workspace, identity, policy, result, envelope, started):
    try:
        jev_store.write_record(workspace, SITE, identity, {
            "schema_version": result.get("schema_version"),
            "policy_version": policy.get("version"),
            "schema_identity": result.get("schema_identity"),
            "policy_identity": result.get("policy_identity"),
            "state_identity": result.get("state_identity"),
            "decision": result.get("hypothetical_choice"),
            "confidence": result.get("confidence"),
            "actual_action": result.get("actual_action"),
            "fallback": result.get("fallback_reason"),
            "fallback_reason": result.get("fallback_reason"),
            "inference_status": result.get("inference_status"),
            "classifier_exit_code": result.get("classifier_exit_code"),
            "provider_error": result.get("provider_error"),
            "evidence_bytes": result.get("evidence_bytes"),
            "deterministic_exclusions": result.get("deterministic_exclusions"),
            "timing": {"duration_ms": int((time.monotonic() - started) * 1000)},
            "usage": (envelope or {}).get("usage") if isinstance(envelope, dict) else None,
        })
    except (OSError, TypeError, ValueError, RuntimeError):
        # Advisory persistence cannot turn an optional hook into a pipeline
        # failure and never writes authoritative ledger entries.
        return


def prepare(package_path: str, *, workspace: str, task_id: int, policy_path: str | None = None) -> dict:
    """Prepare shared Site 4 guidance and append it to ``package_path``.

    The package's original bytes are retained as a prefix.  The returned
    object describes the advisory selection and contains no review verdict.
    Required package I/O raises ``RequiredArtifactError``; provider, policy,
    and advisory persistence failures degrade to standard review.
    """
    task_id = _task_id(task_id)
    if not isinstance(workspace, str) or not workspace.strip():
        raise ValueError("workspace is required")
    started = time.monotonic()
    raw, text = _read_package(package_path)
    base = _without_guidance(raw)
    evidence = _evidence(base, text, workspace, task_id)
    plan = _read_json(pathlib.Path(workspace) / "plan.json")
    task = _find_task(plan, task_id)
    entries = _ledger_entries(workspace, task_id)
    interface_entries = [
        entry for entry in entries
        if str(entry.get("task")) == str(task_id)
        and entry.get("type") == "interface_touched"
    ]
    exclusions = _exclusions(workspace, task_id, task, interface_entries)
    state = _state(evidence, workspace, task_id, plan, task, interface_entries, exclusions)

    try:
        policy = jev_policy.read_policy(policy_path, SITE)
    except Exception as exc:
        policy = {"site": SITE, "mode": "shadow", "threshold": 0.9,
                  "policy_error": f"{type(exc).__name__}: {exc}"}
    try:
        schema = _load_schema()
        schema_error = None
    except Exception as exc:
        schema = {"version": None}
        schema_error = f"schema_unavailable:{type(exc).__name__}"

    state_identity = _digest(state)
    schema_identity = _digest(schema)
    policy_identity = _digest(policy)
    identity = _digest({
        "state_identity": state_identity,
        "schema_identity": schema_identity,
        "policy_identity": policy_identity,
    })
    envelope = None
    code = None
    choice = None
    confidence = None
    provider_error = None
    inference_status = "not_run"
    cache_status = "not_invoked"
    fallback_reason = None

    if not evidence["complete"]:
        fallback_reason = evidence["reason"] or "incomplete_evidence"
    elif exclusions:
        fallback_reason = "deterministic_exclusion"
    elif schema_error:
        fallback_reason = schema_error
    elif policy.get("policy_error"):
        fallback_reason = "policy_unavailable"
    elif policy.get("mode") == "off":
        fallback_reason = "policy_off"
    elif policy.get("mode") == "active" and not _policy_calibrated(policy, schema):
        fallback_reason = "uncalibrated_policy"
        inference_status = "uncalibrated"
    else:
        payload = {
            "model": schema.get("model"),
            "state": state,
            "questions": schema.get("questions"),
        }
        if len(_canonical(payload).encode("utf-8")) > MAX_PAYLOAD_BYTES:
            fallback_reason = "evidence_too_large"
            evidence["complete"] = False
            evidence["reason"] = fallback_reason
        else:
            try:
                code, envelope = jev_classify.classify(
                    schema,
                    state,
                    workspace=workspace,
                    site=SITE,
                    threshold=policy.get("threshold", 0.9),
                )
                choice, confidence = _answer(envelope)
                status = envelope.get("status") if isinstance(envelope, dict) else None
                inference_status = status or "unavailable"
                provider_error = envelope.get("error") if isinstance(envelope, dict) else None
                cache_status = "hit" if isinstance(envelope, dict) and envelope.get("cache_hit") else "miss"
                if status == "cache_unavailable" or (isinstance(envelope, dict) and envelope.get("error_kind") == "cache_error"):
                    cache_status = "cache_unavailable"
                    fallback_reason = "cache_unavailable"
                elif code == 2 or (isinstance(envelope, dict) and envelope.get("error_kind") == "setup_error"):
                    fallback_reason = "classifier_setup_error"
                    inference_status = "setup_error"
                elif status == "circuit_open":
                    fallback_reason = "circuit_open"
                elif code == 3 or status == "unavailable":
                    fallback_reason = "provider_unavailable"
                elif code == 1:
                    fallback_reason = "uncertain"
                elif choice is None:
                    fallback_reason = "invalid_choice"
                elif policy.get("mode") == "shadow":
                    fallback_reason = "shadow"
            except Exception as exc:
                message = str(exc) or type(exc).__name__
                provider_error = message
                envelope = {"status": "unavailable", "answers": {}, "error": message}
                inference_status = "unavailable"
                cache_status = "unavailable" if "cache" not in message.lower() else "cache_unavailable"
                fallback_reason = "cache_unavailable" if cache_status == "cache_unavailable" else "provider_unavailable"

    effective_choice = None
    if isinstance(envelope, dict) and choice is not None and policy.get("mode") == "active" and not fallback_reason in {
        "provider_unavailable", "cache_unavailable", "classifier_setup_error", "circuit_open", "invalid_choice"
    }:
        try:
            selected = jev_policy.select_action(policy, QUESTION_ID, envelope, "standard_review")
            if selected in CHOICES:
                effective_choice = selected
            if policy.get("effective_mode") == "shadow" and fallback_reason is None:
                fallback_reason = "policy_uncalibrated"
            elif (selected == "focused_review" and choice == "focused_review"
                  and (confidence is None or confidence < max(
                      MIN_FOCUSED_CONFIDENCE, policy.get("threshold", MIN_FOCUSED_CONFIDENCE)
                  ))):
                effective_choice = "standard_review"
                fallback_reason = fallback_reason or "uncertain"
            elif selected == "standard_review" and choice == "focused_review" and confidence is not None and confidence < policy.get("threshold", .9):
                fallback_reason = fallback_reason or "uncertain"
        except (TypeError, ValueError, KeyError):
            fallback_reason = fallback_reason or "policy_unavailable"

    actual_action = "standard_review"
    if policy.get("mode") == "active" and effective_choice == "focused_review" and fallback_reason is None:
        actual_action = "focused_review"
    elif policy.get("mode") == "active" and effective_choice == "standard_review" and fallback_reason is None:
        fallback_reason = "standard_choice"

    result = {
        "site": SITE,
        "task": task_id,
        "package_path": str(pathlib.Path(package_path).resolve()),
        "state_identity": state_identity,
        "schema_identity": schema_identity,
        "policy_identity": policy_identity,
        "schema_version": schema.get("version"),
        "choice": effective_choice if policy.get("mode") == "active" else choice,
        "hypothetical_choice": choice,
        "confidence": confidence,
        "actual_action": actual_action,
        "fallback_reason": fallback_reason,
        "inference_status": inference_status,
        "cache_status": cache_status,
        "classifier_exit_code": code,
        "provider_error": provider_error,
        "evidence_complete": evidence["complete"],
        "evidence_bytes": evidence["bytes"],
        "deterministic_exclusions": exclusions,
        "usage": (envelope or {}).get("usage") if isinstance(envelope, dict) else None,
    }
    _atomic_write(package_path, base + (b"" if base.endswith(b"\n") else b"\n") + b"\n" + _guidance_text(result))
    _write_advisory(workspace, identity, policy, result, envelope, started)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(prog="review-guidance")
    parser.add_argument("package", nargs="?")
    parser.add_argument("--package", dest="package_option")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--policy")
    try:
        args = parser.parse_args(argv)
        package = args.package_option or args.package
        if not package:
            raise ValueError("package is required")
        result = prepare(package, workspace=args.workspace, task_id=args.task, policy_path=args.policy)
    except SystemExit:
        return 2
    except RequiredArtifactError as exc:
        print(f"review-guidance: {exc}", file=sys.stderr)
        return 1
    except (TypeError, ValueError) as exc:
        print(f"review-guidance: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
