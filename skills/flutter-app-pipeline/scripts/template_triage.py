"""Site 1 catalog triage using conservative Jev advisory decisions."""
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

_SHARED = Path(__file__).resolve().parents[2] / "two-model-sdd-pipeline" / "scripts"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))
import jev_classify  # noqa: E402
import jev_policy  # noqa: E402


def _identity(evidence, context):
    payload = {"evidence": evidence, "context": context}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _valid_evidence(evidence, context):
    required = ("owner_repo", "evidence_hash", "readme_text", "pubspec_text", "tree_text")
    if any(not evidence.get(key) for key in required):
        return "missing_required_evidence"
    constraints = evidence.get("constraints", {})
    def failed(value):
        if isinstance(value, dict):
            return any(failed(item) for item in value.values())
        if isinstance(value, list):
            return any(failed(item) for item in value)
        return value in ("fail", "failed", False)
    if isinstance(constraints, dict) and any(failed(value) for value in constraints.values()):
        return "failed_explicit_constraint"
    skeleton = (context.get("generic_category"), context.get("specific_category"), context.get("original_implementations"))
    if any(not value for value in skeleton):
        return "missing_category_skeleton"
    return None


def _audit_path(workspace):
    path = Path(workspace) / ".jev" / "site1-triage.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_audit(workspace):
    path = _audit_path(workspace)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _save_audit(workspace, audit):
    path = _audit_path(workspace)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(audit, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def _persist_catalog(context, owner, result):
    path = context.get("catalog_path")
    if not path or result.get("actor") != "jev":
        return
    conn = sqlite3.connect(path)
    try:
        conn.execute("UPDATE templates SET triage_decision=?, triage_confidence=?, triage_policy_version=?, triage_actor=? WHERE owner_repo=?",
                     (result["decision"], (result.get("judgment") or {}).get("confidence"), result.get("triage_policy_version"), "jev", owner))
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()


def _clear_catalog_triage(workspace, owner):
    path = Path(workspace) / "template-catalog.sqlite3"
    if not path.exists():
        return
    conn = sqlite3.connect(path)
    try:
        conn.execute("UPDATE templates SET triage_decision=NULL, triage_confidence=NULL, triage_policy_version=NULL, triage_actor=NULL WHERE owner_repo=?", (owner,))
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()


def _catalog_evidence_changed(workspace, owner, evidence_hash):
    path = Path(workspace) / "template-catalog.sqlite3"
    if not path.exists():
        return False
    conn = sqlite3.connect(path)
    try:
        row = conn.execute("SELECT evidence_hash FROM templates WHERE owner_repo=?", (owner,)).fetchone()
        return row is not None and row[0] not in (None, evidence_hash)
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


def triage(evidence, context, *, workspace, policy_path=None):
    """Return an advisory catalog decision; never selects or installs a project."""
    if not isinstance(evidence, dict) or not isinstance(context, dict):
        raise ValueError("evidence and context must be JSON objects")
    evidence_hash = evidence.get("evidence_hash")
    identity = _identity(evidence, context)
    base = {"decision": "existing_path", "actor": "baseline", "fallback_reason": None,
            "evidence_hash": evidence_hash, "triage_identity": identity, "project_selected": False,
            "judgment": None}
    score = context.get("score_report") or {}
    verdict = score.get("verdict")
    if verdict != "DEVELOPER_DECISION":
        base["fallback_reason"] = "protected_scoring_verdict"
        return base
    reason = _valid_evidence(evidence, context)
    audit = _load_audit(workspace)
    owner = evidence.get("owner_repo") or "unknown"
    previous = audit.get(owner)
    if (previous and previous.get("evidence_hash") != evidence_hash) or _catalog_evidence_changed(workspace, owner, evidence_hash):
        _clear_catalog_triage(workspace, owner)
        base["fallback_reason"] = "evidence_changed"
        audit[owner] = {"evidence_hash": evidence_hash, "invalidated": True, "identity": identity}
        _save_audit(workspace, audit)
        return base
    policy = jev_policy.read_policy(policy_path, "site1")
    if reason:
        base["fallback_reason"] = reason
        return base
    if policy.get("mode") == "off":
        base["fallback_reason"] = "policy_off"
        return base
    schema = {"model": policy.get("model", "jev"), "questions": {"triage": {
        "type": "choice", "instructions": "Choose shortlist triage for this catalog candidate.",
        "criteria": {"adopt": "accept into shortlist", "reject": "exclude from shortlist", "needs_review": "defer to developer"}
    }}}
    state = {"evidence": evidence, "category_skeleton": {
        "generic_category": context["generic_category"], "specific_category": context["specific_category"],
        "original_implementations": context["original_implementations"]}, "score_report": score,
        "intended_use": context.get("intended_use"), "declared_dependencies": context.get("declared_dependencies")}
    code, envelope = jev_classify.classify(schema, state, workspace=workspace, site="site1", threshold=policy.get("threshold", .9))
    fallback = "existing_path"
    action = jev_policy.select_action(policy, "triage", envelope, fallback)
    answer = (envelope.get("answers") or {}).get("triage")
    base["judgment"] = answer
    proposed = (answer or {}).get("choice")
    if policy.get("mode") == "shadow" or code != 0 or action not in {"adopt", "reject"}:
        base["fallback_reason"] = "provider_unavailable" if code == 3 else ("shadow" if policy.get("mode") == "shadow" else ("uncertain" if code else "needs_review"))
        base["inference_status"] = envelope.get("status", "unavailable" if code == 3 else "answered")
        base["provider_error"] = envelope.get("error") if code == 3 else None
        base["hypothetical_decision"] = proposed
        base["jev_proposed_decision"] = proposed
        base["observed_decision"] = context.get("observed_decision", "developer_review")
    else:
        base.update(decision=action, actor="jev", fallback_reason=None)
        base["triage_policy_version"] = policy.get("version")
    preserved = previous if previous and previous.get("evidence_hash") == evidence_hash and code == 3 else {}
    audit[owner] = {"evidence_hash": evidence_hash, "identity": identity, "decision": preserved.get("decision", base["decision"]),
                    "actor": preserved.get("actor", base["actor"]), "judgment": preserved.get("judgment", answer),
                    "inference_status": base.get("inference_status"), "provider_error": base.get("provider_error"),
                    "usage": envelope.get("usage"), "duration_ms": envelope.get("duration_ms")}
    _save_audit(workspace, audit)
    persisted_context = dict(context)
    persisted_context.setdefault("catalog_path", str(Path(workspace) / "template-catalog.sqlite3"))
    _persist_catalog(persisted_context, owner, base)
    return base


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="template-triage")
    parser.add_argument("evidence_file"); parser.add_argument("context_file"); parser.add_argument("--workspace", required=True)
    parser.add_argument("--policy"); parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        evidence = json.loads(Path(args.evidence_file).read_text(encoding="utf-8"))
        context = json.loads(Path(args.context_file).read_text(encoding="utf-8"))
        result = triage(evidence, context, workspace=args.workspace, policy_path=args.policy)
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print("template-triage: {}".format(exc), file=sys.stderr)
        return 2 if isinstance(exc, (ValueError, TypeError, json.JSONDecodeError)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
