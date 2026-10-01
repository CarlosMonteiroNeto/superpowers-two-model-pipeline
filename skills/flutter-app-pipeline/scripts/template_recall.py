"""Deterministic fresh catalog recall with optional injected vectors.

The catalog is an input boundary, not a source of truth for malformed data.
Rows that are not fresh, scored ``AUTO_APPROVE``, and backed by evidence are
ineligible. Once vector recall is requested, invalid vector setup is a hard
``SETUP_ERROR`` so callers cannot mistake a broken embedding store for a
normal no-result response.
"""

import argparse
import ast
import datetime
import json
import math
import os
import subprocess
import sqlite3
import sys
from pathlib import Path

SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "two-model-sdd-pipeline" / "scripts"
if str(SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS))
import asset_recall

try:  # Direct script execution is the supported CLI path.
    from template_catalog import _connect
    from template_embed import embedding_identity, is_valid_vector, vector_is_compatible
except ImportError:  # Package-safe imports for test/discovery runners.
    from .template_catalog import _connect
    from .template_embed import embedding_identity, is_valid_vector, vector_is_compatible


def _age(value):
    """Return age in days, or ``None`` for malformed/future timestamps."""
    try:
        dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        age = (datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds() / 86400
        return age if age >= 0 else None
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


def _pkgs(row):
    value = row.get("package_names")
    if not value:
        return set()
    try:
        value = json.loads(value)
    except (TypeError, ValueError):
        try:
            value = ast.literal_eval(value)
        except (TypeError, ValueError, SyntaxError):
            return set()
    return {str(x) for x in value} if isinstance(value, (list, tuple, set)) else set()


def _normalise_query(query_vector, model, query_source_hash=None, query_vector_identity=None):
    """Validate an injected query vector and optional content identity.

    A plain list remains supported for the public API: stored candidate
    vectors are still required to have a recomputed identity for the requested
    model and their own evidence hash. A structured query record can carry its
    own source hash and identity, which are validated when present.
    """
    record = query_vector if isinstance(query_vector, dict) else None
    vector = record.get("vector") if record is not None else query_vector
    if not is_valid_vector(vector):
        return None

    requested_model = record.get("model") if record is not None else model
    if not isinstance(requested_model, str) or not requested_model:
        return None
    if model is not None and requested_model != model:
        return None

    source_hash = record.get("source_hash") if record is not None else query_source_hash
    identity = record.get("identity") if record is not None else query_vector_identity
    if source_hash is not None or identity is not None:
        if not isinstance(source_hash, str) or not source_hash or not isinstance(identity, str) or not identity:
            return None
        if identity != embedding_identity(requested_model, source_hash):
            return None

    return vector, requested_model


def _stored_similarity(row, query, model):
    """Validate one stored vector and return its cosine similarity.

    ``None`` means a malformed or incompatible catalog vector. The caller
    turns that into ``SETUP_ERROR`` rather than silently dropping the
    candidate.
    """
    try:
        stored = json.loads(row.get("vector") or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(stored, dict):
        return None

    source_hash = row.get("evidence_hash")
    if not isinstance(source_hash, str) or not source_hash:
        return None
    expected_identity = embedding_identity(model, source_hash)
    if row.get("vector_identity") != expected_identity:
        return None
    if not vector_is_compatible(
        stored,
        expected_identity,
        model=model,
        source_hash=source_hash,
        dimension=len(query),
    ):
        return None

    vector = stored["vector"]
    denominator = math.sqrt(sum(value * value for value in query)) * math.sqrt(sum(value * value for value in vector))
    if not denominator:
        return None
    similarity = sum(left * right for left, right in zip(query, vector)) / denominator
    return similarity if math.isfinite(similarity) else None


def recall(
    conn,
    category,
    packages=None,
    query_vector=None,
    top_n=3,
    max_age_days=180,
    model=None,
    evidence_hashes=None,
    query_source_hash=None,
    query_vector_identity=None,
):
    """Return ``(HIT|MISS|SETUP_ERROR, rows)`` for a catalog category."""
    if (
        not isinstance(category, str)
        or not category
        or isinstance(top_n, bool)
        or not isinstance(top_n, int)
        or top_n < 1
        or isinstance(max_age_days, bool)
        or not isinstance(max_age_days, (int, float))
        or not math.isfinite(float(max_age_days))
        or max_age_days < 0
    ):
        return "SETUP_ERROR", []

    vector_requested = query_vector is not None
    query = None
    requested_model = model
    if vector_requested:
        if not isinstance(model, str) or not model:
            return "SETUP_ERROR", []
        normalised = _normalise_query(query_vector, model, query_source_hash, query_vector_identity)
        if normalised is None:
            return "SETUP_ERROR", []
        query, requested_model = normalised

    if evidence_hashes is None:
        allowed_hashes = None
    elif isinstance(evidence_hashes, str):
        allowed_hashes = {evidence_hashes}
    else:
        try:
            allowed_hashes = {value for value in evidence_hashes if isinstance(value, str) and value}
        except TypeError:
            return "SETUP_ERROR", []

    try:
        candidate_limit = max(top_n, conn.execute("SELECT COUNT(*) FROM assets WHERE ecosystem='flutter'").fetchone()[0])
    except (AttributeError, sqlite3.DatabaseError, TypeError):
        return "SETUP_ERROR", []
    wanted = {str(value) for value in (packages or [])}
    try:
        bindings = conn.execute("SELECT owner_repo, asset_id FROM templates ORDER BY owner_repo").fetchall()
        current_ids = [row["asset_id"] for row in bindings]
        if any(not isinstance(asset_id, str) or not asset_id for asset_id in current_ids):
            return "SETUP_ERROR", []
        if current_ids:
            placeholders = ",".join("?" for _ in current_ids)
            existing = {row[0] for row in conn.execute(
                "SELECT asset_id FROM assets WHERE ecosystem='flutter' AND asset_id IN ({})".format(placeholders),
                current_ids,
            )}
            if existing != set(current_ids):
                return "SETUP_ERROR", []
    except (AttributeError, sqlite3.DatabaseError, TypeError):
        return "SETUP_ERROR", []
    request = {
        "ecosystem": "flutter",
        "category": category,
        "top_n": candidate_limit,
        "max_age_days": max_age_days,
        "dependencies": list(packages or []),
        "evidence_filters": {"score_report.verdict": "AUTO_APPROVE"},
        "asset_ids": current_ids,
    }
    if allowed_hashes is not None:
        request["evidence_hashes"] = sorted(allowed_hashes)
    result = asset_recall.query_connection(conn, request)
    if result["status"] != "HIT":
        return result["status"], []
    try:
        rows = {row["asset_id"]: dict(row) for row in conn.execute("SELECT * FROM templates")}
    except (AttributeError, sqlite3.DatabaseError):
        return "SETUP_ERROR", []
    eligible = []
    for asset in result["results"]:
        row = rows.get(asset["asset_id"])
        if row is None:
            return "SETUP_ERROR", []
        # The compatibility table remains the source of Flutter-only package
        # names and older injected vectors while callers migrate to assets.
        # A synthesized generic hash never makes an incomplete legacy record
        # eligible for the Flutter public contract.
        if not isinstance(row.get("evidence_hash"), str) or not row["evidence_hash"] or _age(row.get("fetched_at")) is None:
            continue
        row["package_overlap"] = len(wanted & _pkgs(row))
        similarity = _stored_similarity(row, query, requested_model) if vector_requested else 0.0
        if vector_requested and similarity is None:
            return "SETUP_ERROR", []
        row["similarity"] = similarity
        eligible.append(row)
    eligible.sort(key=lambda row: (-row["package_overlap"], -row["similarity"], row["owner_repo"]))
    eligible = eligible[:top_n]
    return ("HIT", eligible) if eligible else ("MISS", [])


def _run_live_search(specific, generic, workspace):
    """Invoke the existing Phase 2a search only after an explicit MISS.

    The recall boundary remains offline when no search queries are supplied.
    The caller receives the search output as telemetry; this function never
    changes the deterministic recall verdict or catalog.
    """
    script = os.path.join(os.path.dirname(__file__), "template-search")
    shell = os.environ.get("BASH")
    if not shell:
        candidate = r"C:\Program Files\Git\bin\bash.exe"
        shell = candidate if os.name == "nt" and os.path.exists(candidate) else "bash"
    result = subprocess.run(
        [shell, script, "--specific", specific, "--generic", generic],
        cwd=workspace,
        capture_output=True,
        text=True,
        env=dict(os.environ),
    )
    return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("category")
    parser.add_argument("--database")
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--max-age-days", type=float, default=180)
    parser.add_argument("--model")
    parser.add_argument("--query-vector", help="JSON list or vector record")
    parser.add_argument("--query-source-hash")
    parser.add_argument("--vector-identity")
    parser.add_argument("--workspace")
    parser.add_argument("--policy")
    parser.add_argument("--suitability-context")
    parser.add_argument("--suitability-output")
    parser.add_argument("--live-search", action="store_true")
    parser.add_argument("--specific")
    parser.add_argument("--generic")
    args = parser.parse_args(argv)

    # Recall is read-only and must never create an empty catalog as a side
    # effect. A missing path is therefore a setup error.
    if not args.database or not os.path.exists(args.database) or args.top < 1 or args.max_age_days < 0:
        return 1

    query_vector = None
    if args.query_vector is not None:
        try:
            query_vector = json.loads(args.query_vector)
        except (TypeError, ValueError, json.JSONDecodeError):
            return 1

    conn = None
    try:
        conn = _connect(args.database)
        status, rows = recall(
            conn,
            args.category,
            query_vector=query_vector,
            top_n=args.top,
            max_age_days=args.max_age_days,
            model=args.model,
            query_source_hash=args.query_source_hash,
            query_vector_identity=args.vector_identity,
        )
        report = {"status": status, "results": rows}
        if args.suitability_context:
            if not args.workspace:
                return 1
            with open(args.suitability_context, encoding="utf-8") as handle:
                context = json.load(handle)
            if status == "SETUP_ERROR":
                # Preserve the deterministic setup error and avoid invoking
                # an optional Jev hook on malformed catalog/embedding state.
                report["verdict"] = "SETUP_ERROR"
            else:
                try:
                    from recall_suitability import assess
                except ImportError:
                    from .recall_suitability import assess
                report = assess(report, context, workspace=args.workspace, policy_path=args.policy)
                if report.get("verdict") == "MISS":
                    specific = args.specific or context.get("specific_query")
                    generic = args.generic or context.get("generic_query")
                    if specific and generic:
                        report["live_search"] = _run_live_search(specific, generic, args.workspace)
                    elif args.live_search:
                        report["live_search"] = {"exit_code": 2, "stdout": "", "stderr": "missing specific/generic query"}
            if args.suitability_output:
                with open(args.suitability_output, "w", encoding="utf-8") as handle:
                    json.dump(report, handle, ensure_ascii=False, allow_nan=False, sort_keys=True)
            print(json.dumps(report, ensure_ascii=False, allow_nan=False))
            return {"HIT": 0, "MISS": 2, "SETUP_ERROR": 1}[report.get("verdict", "SETUP_ERROR")]
        print(json.dumps(report, ensure_ascii=False, allow_nan=False))
        return {"HIT": 0, "MISS": 2, "SETUP_ERROR": 1}[status]
    except (OSError, ValueError, TypeError, sqlite3.DatabaseError, json.JSONDecodeError):
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
