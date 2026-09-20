"""Prepare the Agente diretor prompt for a Site 3 episode.

Site 3 is advisory.  The existing task-generator dispatch remains the
authoritative corrective/arbitration action; this module only chooses whether
to append a narrowly scoped focus hint to the already constructed baseline
prompt.  A provider, policy, cache, or advisory persistence failure therefore
falls back to the baseline prompt and does not write pipeline ledger state.
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


SITE = "site3"
QUESTION_ID = "director_classification"
CHOICES = (
    "local_mechanical_correction",
    "architectural_disagreement",
    "test_noise_or_unclear",
)
SCHEMA_PATH = pathlib.Path(__file__).resolve().parent.parent / "schemas" / "jev-site-3.json"
VALID_VERDICTS = {"APPROVED", "SEND_BACK", "ESCALATE"}
VALID_SEVERITIES = {"Critical", "Important", "Minor"}


class RequiredArtifactError(Exception):
    """The pre-existing baseline could not be read or the selected prompt saved."""


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _digest(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _read_text(path, label):
    try:
        return pathlib.Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RequiredArtifactError(f"cannot read {label}: {path}: {exc}") from exc


def _read_json(path):
    try:
        with pathlib.Path(path).open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return None


def _validate_review(value):
    """Validate the structured review artifact before it enters Jev state.

    A parsed verdict is an authority boundary: a truthy JSON object is not
    enough to establish the findings and evidence required for a focused
    corrective prompt.  Return the original object only when all required
    fields have the expected shape.
    """
    if not isinstance(value, dict):
        return None, "review artifact is missing or not an object"
    verdict = value.get("verdict")
    if verdict not in VALID_VERDICTS:
        return None, "review verdict is invalid"
    findings = value.get("findings")
    if not isinstance(findings, list):
        return None, "review findings must be a list"
    minors = value.get("minors")
    if not isinstance(minors, list):
        return None, "review minors must be a list"
    summary = value.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None, "review summary is required"
    if verdict == "SEND_BACK" and not findings:
        return None, "SEND_BACK review requires findings"
    for finding in findings:
        if not isinstance(finding, dict):
            return None, "review finding must be an object"
        if finding.get("severity") not in VALID_SEVERITIES:
            return None, "review finding severity is invalid"
        line = finding.get("line")
        if isinstance(line, bool) or not isinstance(line, int) or line <= 0:
            return None, "review finding line must be a positive integer"
        for field in ("file", "issue", "fix"):
            if not isinstance(finding.get(field), str) or not finding[field].strip():
                return None, "review finding requires a nonempty " + field
    return value, None


def _load_schema():
    value = _read_json(SCHEMA_PATH)
    if not isinstance(value, dict) or not isinstance(value.get("questions"), dict):
        raise ValueError("Site 3 schema is invalid")
    return value


def _task_id(value):
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("task must be a positive integer") from exc
    if number <= 0 or str(number) != str(value).strip():
        raise ValueError("task must be a positive integer")
    return number


def _workspace_identity(workspace):
    return os.path.normcase(os.path.realpath(os.path.abspath(str(workspace))))


def _find_task(plan, task_id):
    if not isinstance(plan, dict) or not isinstance(plan.get("tasks"), list):
        return None
    for task in plan["tasks"]:
        if isinstance(task, dict) and str(task.get("id")) == str(task_id):
            return task
    return None


def _ledger_entries(workspace):
    entries = []
    for name in ("ledger.jsonl",):
        path = pathlib.Path(workspace) / name
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


def _spec_material(task, plan_path):
    """Return cited constraints without making spec reads a required hook."""
    refs = task.get("spec_refs", []) if isinstance(task, dict) else []
    if not isinstance(refs, list):
        refs = []
    material = []
    plan_parent = pathlib.Path(plan_path).resolve().parent
    roots = [pathlib.Path.cwd(), plan_parent]
    # A normal tracked plan lives below <checkout>/docs/...; keep the lookup
    # useful for disposable test plans and shallow paths too.
    roots.extend(plan_parent.parents)
    search_roots = []
    for root in roots:
        if root not in search_roots:
            search_roots.append(root)
    for ref in refs:
        ref = str(ref)
        path_part = ref.split("#", 1)[0]
        found = None
        for root in search_roots:
            candidate = root / path_part
            if candidate.is_file():
                found = candidate
                break
        item = {"ref": ref, "available": bool(found)}
        if found:
            try:
                item["text"] = found.read_text(encoding="utf-8", errors="replace")
            except OSError:
                item["available"] = False
        material.append(item)
    return material


def _episode_state(mode, workspace, task_id, plan_path, plan, target_task):
    worktree = _workspace_identity(workspace)
    plan_identity = None
    try:
        plan_identity = hashlib.sha256(pathlib.Path(plan_path).read_bytes()).hexdigest()
    except OSError:
        pass
    findings_path = pathlib.Path(workspace) / f"task-{task_id}-review.json"
    findings, findings_error = _validate_review(_read_json(findings_path))
    entries = _ledger_entries(workspace)
    escalations = [entry for entry in entries
                   if str(entry.get("task")) == str(task_id)
                   and (entry.get("type") in {"escalated", "scope_violation"}
                        or (entry.get("type") == "review_outcome"
                            and entry.get("summary") == "ESCALATE"))]
    latest_escalation = escalations[-1] if escalations else None
    review = findings if isinstance(findings, dict) else None
    actual = review if mode == "CORRECTIVE" else {
        "review": review,
        "escalation": latest_escalation,
    }
    refs = target_task.get("spec_refs", []) if isinstance(target_task, dict) else []
    constraints = {
        "spec_refs": refs if isinstance(refs, list) else [],
        "acceptance": target_task.get("acceptance", []) if isinstance(target_task, dict) else [],
        "touches": target_task.get("touches", []) if isinstance(target_task, dict) else [],
        "depends_on": target_task.get("depends_on", []) if isinstance(target_task, dict) else [],
    }
    episode = {
        "site": SITE,
        "mode": mode,
        "task": task_id,
        "workspace": worktree,
        "plan_identity": plan_identity,
        "findings_artifact": str(findings_path),
    }
    state = {
        "episode": episode,
        "target_task": target_task,
        "actual_findings_or_escalation": actual,
        "findings": review,
        "escalation": latest_escalation,
        "cited_constraints": constraints,
        "spec_material": _spec_material(target_task or {}, plan_path),
        "plan": plan,
        "plan_path": str(pathlib.Path(plan_path).resolve()),
    }
    # Keep the compatibility names explicit so downstream evaluation can
    # identify the exact evidence without scraping prose.
    state["actual_findings"] = review if mode == "CORRECTIVE" else None
    state["actual_escalation"] = latest_escalation if mode == "ARBITRATE" else None
    state["findings_valid"] = review is not None
    state["findings_error"] = findings_error
    return state


def _answer(envelope):
    if not isinstance(envelope, dict):
        return None, None
    answers = envelope.get("answers")
    answer = answers.get(QUESTION_ID) if isinstance(answers, dict) else None
    if not isinstance(answer, dict) or answer.get("choice") not in CHOICES:
        return None, None
    confidence = answer.get("confidence")
    if (not isinstance(confidence, (int, float)) or isinstance(confidence, bool)
            or not math.isfinite(confidence) or not 0 <= confidence <= 1):
        confidence = None
    return answer["choice"], confidence


def _focus_prompt(baseline, mode, choice):
    if mode == "CORRECTIVE":
        return baseline.rstrip() + ("\n\n"
            "Jev advisory focus (not a verdict; you remain authoritative): "
            "inspect this as a possible local mechanical correction first. "
            "Verify the complete plan, target task, original findings, and cited "
            "constraints before appending one corrective task; reject this focus "
            "if the evidence shows an architectural or unsafe change.\n")
    return baseline.rstrip() + ("\n\n"
        f"Jev advisory focus (classification: {choice.replace('_', ' ')}; not a ruling): "
        "use this only to focus inspection. Retain the full viability context, "
        "including the complete plan, target task, original escalation/findings, "
        "and cited constraints, and make the director ruling yourself.\n")


def _atomic_write(path, text):
    path = pathlib.Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".director-prompt-", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    except (OSError, UnicodeError) as exc:
        raise RequiredArtifactError(f"cannot write director prompt: {path}: {exc}") from exc


def _write_advisory(workspace, identity, policy, result, envelope, started):
    try:
        jev_store.write_record(workspace, SITE, identity, {
            "schema_version": result.get("schema_version"),
            "policy_version": policy.get("version"),
            "schema_identity": result.get("schema_identity"),
            "policy_identity": result.get("policy_identity"),
            "episode_state_identity": result.get("episode_state_identity"),
            "state_identity": identity,
            # ``choice`` is the effective active action; retain the raw
            # provider recommendation for shadow and active fallback cases.
            "decision": result.get("hypothetical_choice"),
            "confidence": result.get("confidence"),
            "cache_status": "hit" if isinstance(envelope, dict) and envelope.get("cache_hit") else result.get("cache_status"),
            "actual_action": result.get("actual_action"),
            "fallback": result.get("fallback_reason"),
            "fallback_reason": result.get("fallback_reason"),
            "inference_status": result.get("inference_status"),
            "classifier_exit_code": result.get("classifier_exit_code"),
            "provider_error": result.get("provider_error"),
            "timing": {"duration_ms": int((time.monotonic() - started) * 1000)},
            "usage": (envelope or {}).get("usage") if isinstance(envelope, dict) else None,
            "episode": result.get("episode"),
        })
    except (OSError, TypeError, ValueError, RuntimeError):
        # Advisory persistence cannot turn an optional hook into a pipeline
        # failure, and never writes authoritative ledger entries.
        return


def prepare(*, mode, workspace, task_id, plan_path, baseline_path, output_path, policy_path=None):
    """Prepare and save a director prompt, returning advisory metadata.

    Baseline reading and output writing are required artifacts and raise
    ``RequiredArtifactError``.  Everything used to select a Jev hint is
    optional and degrades to the unchanged baseline.
    """
    if mode not in ("CORRECTIVE", "ARBITRATE"):
        raise ValueError("mode must be CORRECTIVE or ARBITRATE")
    task_id = _task_id(task_id)
    if not isinstance(workspace, str) or not workspace.strip():
        raise ValueError("workspace is required")
    baseline = _read_text(baseline_path, "baseline prompt")
    started = time.monotonic()
    fallback_reason = None
    plan = _read_json(plan_path)
    target = _find_task(plan, task_id)
    state = _episode_state(mode, workspace, task_id, plan_path, plan, target)
    state["episode"]["baseline_identity"] = _digest(baseline)
    try:
        policy = jev_policy.read_policy(policy_path, SITE)
    except Exception as exc:  # optional policy/config boundary
        policy = {"site": SITE, "mode": "shadow", "threshold": .9,
                  "policy_error": f"{type(exc).__name__}: {exc}"}
    try:
        schema = _load_schema()
    except Exception as exc:  # optional schema/config boundary
        schema = {"version": None}
        schema_error = f"schema_unavailable:{type(exc).__name__}"
    else:
        schema_error = None
    schema_identity = _digest(schema)
    policy_identity = _digest(policy)
    state["episode"]["schema_identity"] = schema_identity
    state["episode"]["policy_identity"] = policy_identity
    episode_state_identity = _digest(state)
    # The advisory record identity is content-addressed across all three
    # dimensions.  A policy or schema change must never collide with a prior
    # episode that happens to have the same state payload.
    identity = _digest({
        "episode_state_identity": episode_state_identity,
        "schema_identity": schema_identity,
        "policy_identity": policy_identity,
    })
    envelope = None
    code = None
    choice = None
    confidence = None
    cache_status = "not_invoked"
    inference_status = "not_run"
    provider_error = None
    if not isinstance(plan, dict) or target is None:
        fallback_reason = "required_context_unavailable"
    elif schema_error:
        fallback_reason = schema_error
    elif mode == "CORRECTIVE" and state.get("findings_error"):
        fallback_reason = "invalid_findings"
    elif policy.get("policy_error"):
        fallback_reason = "policy_unavailable"
    elif policy.get("mode") == "off":
        fallback_reason = "policy_off"
    else:
        try:
            code, envelope = jev_classify.classify(
                schema,
                state,
                workspace=workspace,
                site=SITE,
                threshold=policy.get("threshold", .9),
            )
            choice, confidence = _answer(envelope)
            status = envelope.get("status") if isinstance(envelope, dict) else None
            inference_status = status or "unavailable"
            provider_error = envelope.get("error") if isinstance(envelope, dict) else None
            if status == "cache_unavailable":
                cache_status = "cache_unavailable"
            else:
                cache_status = "hit" if isinstance(envelope, dict) and envelope.get("cache_hit") else "miss"
            # Exit 1 is overloaded by the classifier contract: an answered
            # low-confidence response is uncertainty, while circuit-open is
            # provider degradation.  The envelope status is authoritative.
            if code == 2 or (isinstance(envelope, dict) and envelope.get("error_kind") == "setup_error"):
                fallback_reason = "classifier_setup_error"
                inference_status = "setup_error"
            elif status == "circuit_open":
                fallback_reason = "circuit_open"
            elif status == "cache_unavailable" or (isinstance(envelope, dict) and envelope.get("error_kind") == "cache_error"):
                fallback_reason = "cache_unavailable"
            elif code == 3 or status == "unavailable":
                fallback_reason = "provider_unavailable"
            elif code == 1:
                fallback_reason = "uncertain"
            elif choice is None:
                fallback_reason = "invalid_choice"
            elif policy.get("mode") == "shadow":
                fallback_reason = "shadow"
        except Exception as exc:  # optional provider/config/cache boundary
            message = str(exc) or type(exc).__name__
            if "cache" in message.lower():
                fallback_reason = "cache_unavailable"
                inference_status = "cache_unavailable"
                cache_status = "cache_unavailable"
            else:
                fallback_reason = "provider_unavailable"
                inference_status = "unavailable"
                cache_status = "unavailable"
            provider_error = message
            envelope = {"status": inference_status, "error": message, "answers": {}}

    # Keep the provider's raw recommendation for shadow telemetry.  Policy
    # selection is only authoritative for a calibrated active policy.
    effective_choice = None
    if envelope is not None and policy.get("mode") == "active" and choice is not None:
        try:
            selected = jev_policy.select_action(policy, QUESTION_ID, envelope, None)
            if selected in CHOICES:
                effective_choice = selected
            elif policy.get("effective_mode") == "shadow":
                fallback_reason = fallback_reason or "policy_uncalibrated"
            elif (confidence is None or confidence < policy.get("threshold", .9)):
                fallback_reason = fallback_reason or "uncertain"
        except (TypeError, ValueError, KeyError):
            fallback_reason = fallback_reason or "policy_unavailable"

    actual_action = "baseline"
    selected_choice = effective_choice if policy.get("mode") == "active" else choice
    prompt = baseline
    if policy.get("mode") == "active" and effective_choice in CHOICES and fallback_reason is None:
        if mode == "CORRECTIVE" and effective_choice == "local_mechanical_correction":
            actual_action = "focused"
            prompt = _focus_prompt(baseline, mode, effective_choice)
            fallback_reason = None
        elif mode == "ARBITRATE":
            actual_action = "focused_hint"
            prompt = _focus_prompt(baseline, mode, effective_choice)
            fallback_reason = None
    result = {
        "site": SITE,
        "mode": mode,
        "task": task_id,
        "episode": state["episode"],
        "state_identity": identity,
        "episode_state_identity": episode_state_identity,
        "schema_identity": schema_identity,
        "policy_identity": policy_identity,
        "schema_version": schema.get("version"),
        "choice": selected_choice,
        "hypothetical_choice": choice,
        "confidence": confidence,
        "actual_action": actual_action,
        "fallback_reason": fallback_reason,
        "cache_status": cache_status,
        "inference_status": inference_status if envelope is not None else "not_run",
        "classifier_exit_code": code,
        "provider_error": provider_error,
        "findings_valid": state.get("findings_valid"),
        "findings_error": state.get("findings_error"),
        "usage": (envelope or {}).get("usage") if isinstance(envelope, dict) else None,
    }
    _atomic_write(output_path, prompt)
    _write_advisory(workspace, identity, policy, result, envelope, started)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(prog="director-prompt")
    parser.add_argument("--mode", required=True, choices=("CORRECTIVE", "ARBITRATE"))
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--policy")
    try:
        args = parser.parse_args(argv)
        result = prepare(
            mode=args.mode,
            workspace=args.workspace,
            task_id=args.task,
            plan_path=args.plan,
            baseline_path=args.baseline,
            output_path=args.output,
            policy_path=args.policy,
        )
    except SystemExit:
        return 2
    except (RequiredArtifactError, OSError, UnicodeError) as exc:
        print(f"director-prompt: {exc}", file=sys.stderr)
        return 1
    except (TypeError, ValueError) as exc:
        print(f"director-prompt: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
