"""Site 1 catalog triage using conservative Jev advisory decisions."""

import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path


_SHARED = Path(__file__).resolve().parents[2] / "two-model-sdd-pipeline" / "scripts"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))
import jev_classify  # noqa: E402
import jev_policy  # noqa: E402
import jev_store  # noqa: E402


SITE = "site1"
SCHEMA_VERSION = "site1-v1"


class CatalogPersistenceError(RuntimeError):
    """The active Jev decision could not be committed to the catalog."""

    def __init__(self, reason, detail=None):
        self.reason = reason
        self.detail = str(detail) if detail else reason
        super().__init__(self.detail)


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _digest(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _identity(evidence, context):
    """Keep the public triage identity compatible with the original API."""
    return _digest({"evidence": evidence, "context": context})


def _workspace_identity(workspace):
    return os.path.normcase(os.path.realpath(os.path.abspath(str(workspace))))


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
    skeleton = (
        context.get("generic_category"),
        context.get("specific_category"),
        context.get("original_implementations"),
    )
    if any(not value for value in skeleton):
        return "missing_category_skeleton"
    return None


def _catalog_path(workspace, context):
    configured = context.get("catalog_path") if isinstance(context, dict) else None
    return Path(configured) if configured else Path(workspace) / "template-catalog.sqlite3"


def _persist_catalog(context, workspace, owner, result):
    """Atomically persist active triage, proving that exactly one row changed."""
    if result.get("actor") != "jev":
        return
    path = _catalog_path(workspace, context)
    if not path.exists():
        # Do not create an empty database as a side effect of a failed active
        # decision.  A catalog row is required before Jev can be authoritative.
        raise CatalogPersistenceError("catalog_persistence_failed", "catalog database is missing")
    conn = None
    try:
        conn = sqlite3.connect(str(path))
        with conn:
            cursor = conn.execute(
                "UPDATE templates SET triage_decision=?, triage_confidence=?, triage_policy_version=?, triage_actor=? WHERE owner_repo=?",
                (
                    result["decision"],
                    (result.get("judgment") or {}).get("confidence"),
                    result.get("triage_policy_version"),
                    "jev",
                    owner,
                ),
            )
            if cursor.rowcount != 1:
                raise CatalogPersistenceError(
                    "catalog_row_missing",
                    "catalog update changed {} rows".format(cursor.rowcount),
                )
    except CatalogPersistenceError:
        raise
    except Exception as exc:
        # The connection context rolls back any partial update.  Every driver,
        # schema, and write failure is a domain failure at this boundary.
        raise CatalogPersistenceError("catalog_persistence_failed", exc) from exc
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                # The row was committed transactionally.  A close error is not
                # allowed to turn a proven write into an unhandled exception.
                pass


def _clear_catalog_triage(workspace, context, owner):
    path = _catalog_path(workspace, context)
    if not path.exists():
        return
    conn = None
    try:
        conn = sqlite3.connect(str(path))
        with conn:
            cursor = conn.execute(
                "UPDATE templates SET triage_decision=NULL, triage_confidence=NULL, triage_policy_version=NULL, triage_actor=NULL WHERE owner_repo=?",
                (owner,),
            )
            if cursor.rowcount != 1:
                raise CatalogPersistenceError(
                    "catalog_row_missing",
                    "catalog invalidation changed {} rows".format(cursor.rowcount),
                )
    except CatalogPersistenceError:
        raise
    except Exception as exc:
        raise CatalogPersistenceError("catalog_persistence_failed", exc) from exc
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _catalog_evidence_changed(workspace, context, owner, evidence_hash):
    path = _catalog_path(workspace, context)
    if not path.exists():
        return False
    conn = None
    try:
        conn = sqlite3.connect(str(path))
        row = conn.execute("SELECT evidence_hash FROM templates WHERE owner_repo=?", (owner,)).fetchone()
        return row is not None and row[0] not in (None, evidence_hash)
    except Exception:
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _previous_advisory_evidence_changed(workspace, owner, evidence_hash):
    """Read the latest content-addressed Site 1 record for stale evidence."""
    directory = Path(workspace) / ".jev" / SITE / "advisory"
    if not directory.is_dir():
        return False
    latest = None
    for path in directory.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict) or record.get("owner_repo") != owner:
            continue
        if latest is None or record.get("recorded_at", 0) >= latest.get("recorded_at", 0):
            latest = record
    return latest is not None and latest.get("evidence_hash") not in (None, evidence_hash)


def _schema(policy):
    return {
        "version": SCHEMA_VERSION,
        "model": policy.get("model", "jev"),
        "questions": {
            "triage": {
                "type": "choice",
                "instructions": "Choose shortlist triage for this catalog candidate.",
                "criteria": {
                    "adopt": "accept into shortlist",
                    "reject": "exclude from shortlist",
                    "needs_review": "defer to developer",
                },
            }
        },
    }


def _episode(workspace, owner, evidence_hash, state_identity):
    return {
        "site": SITE,
        "workspace": _workspace_identity(workspace),
        "owner_repo": owner,
        "evidence_hash": evidence_hash,
        "state_identity": state_identity,
    }


def _cache_status(envelope, *, invoked):
    if not invoked:
        return "not_invoked"
    if not isinstance(envelope, dict):
        return "unavailable"
    if envelope.get("cache_hit"):
        return "hit"
    if envelope.get("status") in {"cache_unavailable", "circuit_open", "unavailable"} or envelope.get("error_kind") in {"cache_error", "provider_unavailable"}:
        return "unavailable"
    return "miss"


def _write_advisory(
    workspace,
    *,
    state_identity,
    schema,
    policy,
    episode,
    result,
    envelope,
    started,
    invoked,
):
    schema_identity = result.get("schema_identity") or (_digest(schema) if isinstance(schema, dict) else None)
    policy_identity = result.get("policy_identity") or (_digest(policy) if isinstance(policy, dict) else None)
    advisory_identity = _digest(
        {
            "site": SITE,
            "workspace": _workspace_identity(workspace),
            "state_identity": state_identity,
            "schema_identity": schema_identity,
            "policy_identity": policy_identity,
            "episode": episode,
        }
    )
    cache_status = _cache_status(envelope, invoked=invoked)
    answer = result.get("judgment") if isinstance(result.get("judgment"), dict) else {}
    record = {
        "schema_version": schema.get("version") if isinstance(schema, dict) else None,
        "schema_identity": schema_identity,
        "policy_version": policy.get("version") if isinstance(policy, dict) else None,
        "policy_identity": policy_identity,
        "state_identity": state_identity,
        "episode": episode,
        "decision": result.get("hypothetical_decision", result.get("decision")),
        "confidence": answer.get("confidence"),
        "cache_status": cache_status,
        "cache_hit": cache_status == "hit",
        "actual_action": result.get("actual_action", result.get("decision")),
        "fallback": result.get("fallback_reason"),
        "fallback_reason": result.get("fallback_reason"),
        "inference_status": result.get("inference_status", "not_run"),
        "classifier_exit_code": result.get("classifier_exit_code"),
        "provider_error": result.get("provider_error"),
        "owner_repo": episode.get("owner_repo") if isinstance(episode, dict) else None,
        "evidence_hash": result.get("evidence_hash"),
        "timing": {"duration_ms": int(max(0, (time.monotonic() - started) * 1000))},
        "usage": envelope.get("usage") if isinstance(envelope, dict) else None,
    }
    try:
        jev_store.write_record(workspace, SITE, advisory_identity, record)
    except (OSError, TypeError, ValueError, RuntimeError):
        # Advisory persistence is optional.  The catalog transaction above is
        # the authority for active success and is handled separately.
        return


def _finish(
    workspace,
    *,
    state_identity,
    schema,
    policy,
    episode,
    result,
    envelope,
    started,
    invoked,
):
    result.setdefault("schema_identity", _digest(schema) if isinstance(schema, dict) else None)
    result.setdefault("policy_identity", _digest(policy) if isinstance(policy, dict) else None)
    result["cache_status"] = _cache_status(envelope, invoked=invoked)
    result["duration_ms"] = int(max(0, (time.monotonic() - started) * 1000))
    result.setdefault("actual_action", result.get("decision"))
    _write_advisory(
        workspace,
        state_identity=state_identity,
        schema=schema,
        policy=policy,
        episode=episode,
        result=result,
        envelope=envelope,
        started=started,
        invoked=invoked,
    )
    return result


def triage(evidence, context, *, workspace, policy_path=None):
    """Return an advisory catalog decision; never selects or installs a project."""
    if not isinstance(evidence, dict) or not isinstance(context, dict):
        raise ValueError("evidence and context must be JSON objects")
    started = time.monotonic()
    evidence_hash = evidence.get("evidence_hash")
    state_identity = _identity(evidence, context)
    owner = evidence.get("owner_repo") or "unknown"
    try:
        policy = jev_policy.read_policy(policy_path, SITE)
    except Exception as exc:
        policy = {"site": SITE, "mode": "shadow", "threshold": 0.9, "policy_error": str(exc)}
    schema = _schema(policy)
    episode = _episode(workspace, owner, evidence_hash, state_identity)
    schema_identity = _digest(schema)
    policy_identity = _digest(policy)
    base = {
        "decision": "existing_path",
        "actor": "baseline",
        "fallback_reason": None,
        "evidence_hash": evidence_hash,
        "triage_identity": state_identity,
        "project_selected": False,
        "judgment": None,
        "schema_identity": schema_identity,
        "policy_identity": policy_identity,
    }
    score = context.get("score_report") or {}
    verdict = score.get("verdict")
    if verdict != "DEVELOPER_DECISION":
        base["fallback_reason"] = "protected_scoring_verdict"
        return _finish(
            workspace,
            state_identity=state_identity,
            schema=schema,
            policy=policy,
            episode=episode,
            result=base,
            envelope=None,
            started=started,
            invoked=False,
        )

    reason = _valid_evidence(evidence, context)
    try:
        if _catalog_evidence_changed(workspace, context, owner, evidence_hash) or _previous_advisory_evidence_changed(workspace, owner, evidence_hash):
            _clear_catalog_triage(workspace, context, owner)
            base["fallback_reason"] = "evidence_changed"
            return _finish(
                workspace,
                state_identity=state_identity,
                schema=schema,
                policy=policy,
                episode=episode,
                result=base,
                envelope=None,
                started=started,
                invoked=False,
            )
    except CatalogPersistenceError as exc:
        base.update(
            fallback_reason="catalog_persistence_failed",
            domain_error="catalog_persistence_failed",
            persistence_error=exc.reason,
        )
        return _finish(
            workspace,
            state_identity=state_identity,
            schema=schema,
            policy=policy,
            episode=episode,
            result=base,
            envelope=None,
            started=started,
            invoked=False,
        )

    if reason:
        base["fallback_reason"] = reason
        return _finish(
            workspace,
            state_identity=state_identity,
            schema=schema,
            policy=policy,
            episode=episode,
            result=base,
            envelope=None,
            started=started,
            invoked=False,
        )
    if policy.get("mode") == "off":
        base["fallback_reason"] = "policy_off"
        return _finish(
            workspace,
            state_identity=state_identity,
            schema=schema,
            policy=policy,
            episode=episode,
            result=base,
            envelope=None,
            started=started,
            invoked=False,
        )

    state = {
        "evidence": evidence,
        "category_skeleton": {
            "generic_category": context["generic_category"],
            "specific_category": context["specific_category"],
            "original_implementations": context["original_implementations"],
        },
        "score_report": score,
        "intended_use": context.get("intended_use"),
        "declared_dependencies": context.get("declared_dependencies"),
    }
    invoked = True
    try:
        code, envelope = jev_classify.classify(
            schema,
            state,
            workspace=workspace,
            site=SITE,
            threshold=policy.get("threshold", 0.9),
        )
    except Exception as exc:
        code = 3
        envelope = {
            "status": "unavailable",
            "answers": {},
            "usage": None,
            "cache_hit": False,
            "error": str(exc) or type(exc).__name__,
        }
    if not isinstance(envelope, dict):
        envelope = {}
    base["classifier_exit_code"] = code
    base.setdefault("inference_status", envelope.get("status", "unavailable" if code == 3 else "answered"))
    base.setdefault("provider_error", envelope.get("error") if code == 3 else None)
    fallback = "existing_path"
    action = jev_policy.select_action(policy, "triage", envelope, fallback)
    answer = (envelope.get("answers") or {}).get("triage")
    base["judgment"] = answer
    proposed = (answer or {}).get("choice")
    if policy.get("mode") == "shadow" or code != 0 or action not in {"adopt", "reject"}:
        base["fallback_reason"] = (
            "provider_unavailable"
            if code == 3
            else (
                "shadow"
                if policy.get("mode") == "shadow"
                else ("uncertain" if code else "needs_review")
            )
        )
        base["inference_status"] = envelope.get("status", "unavailable" if code == 3 else "answered")
        base["provider_error"] = envelope.get("error") if code == 3 else None
        base["hypothetical_decision"] = proposed
        base["jev_proposed_decision"] = proposed
        base["observed_decision"] = context.get("observed_decision", "developer_review")
        base["actual_action"] = "existing_path"
    else:
        base.update(decision=action, actor="jev", fallback_reason=None)
        base["triage_policy_version"] = policy.get("version")
        base["actual_action"] = action
        try:
            _persist_catalog(context, workspace, owner, base)
        except CatalogPersistenceError as exc:
            # A Jev answer is only authoritative after its catalog update is
            # proven.  Preserve the proposal for audit while returning the
            # existing developer path and a domain/write failure.
            base.update(
                decision="existing_path",
                actor="baseline",
                fallback_reason="catalog_persistence_failed",
                domain_error="catalog_persistence_failed",
                persistence_error=exc.reason,
                hypothetical_decision=action,
                jev_proposed_decision=action,
                observed_decision=context.get("observed_decision", "developer_review"),
                actual_action="existing_path",
            )

    return _finish(
        workspace,
        state_identity=state_identity,
        schema=schema,
        policy=policy,
        episode=episode,
        result=base,
        envelope=envelope,
        started=started,
        invoked=invoked,
    )


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(prog="template-triage")
    parser.add_argument("evidence_file")
    parser.add_argument("context_file")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--policy")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        evidence = json.loads(Path(args.evidence_file).read_text(encoding="utf-8"))
        context = json.loads(Path(args.context_file).read_text(encoding="utf-8"))
        result = triage(evidence, context, workspace=args.workspace, policy_path=args.policy)
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        return 1 if result.get("domain_error") else 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print("template-triage: {}".format(exc), file=sys.stderr)
        return 2 if isinstance(exc, (ValueError, TypeError, json.JSONDecodeError)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
