#!/usr/bin/env python3
"""Deterministic, offline recall and atomic refresh for normalized assets."""

import argparse
import datetime as dt
import json
import math
import os
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import asset_catalog


def embedding_identity(model, source_hash):
    import hashlib

    if not isinstance(model, str) or not model or not isinstance(source_hash, str) or not source_hash:
        raise ValueError("model and source_hash are required")
    return hashlib.sha256((model + "\0" + source_hash).encode("utf-8")).hexdigest()


def is_valid_vector(vector):
    return (
        isinstance(vector, list)
        and bool(vector)
        and all(not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) for value in vector)
        and any(value != 0 for value in vector)
    )


def embed_text(text, encoder=None):
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    if encoder is None:
        raise RuntimeError("embedding encoder is unavailable")
    vector = encoder(text)
    if not isinstance(vector, (list, tuple)) or not vector or any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in vector
    ) or not any(value != 0 for value in vector):
        raise ValueError("encoder returned an invalid vector")
    return [float(value) for value in vector]


def vector_is_compatible(record, identity=None, *, model=None, source_hash=None, dimension=None):
    if not isinstance(record, dict):
        return False
    vector = record.get("vector")
    if not is_valid_vector(vector) or (dimension is not None and len(vector) != dimension):
        return False
    record_model = record.get("model")
    record_hash = record.get("source_hash")
    if not isinstance(record_model, str) or not record_model or not isinstance(record_hash, str) or not record_hash:
        return False
    if model is not None and record_model != model:
        return False
    if source_hash is not None and record_hash != source_hash:
        return False
    expected = embedding_identity(record_model, record_hash)
    return record.get("identity") == expected and (identity is None or identity == expected)


def _age_days(value, now=None):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        age = ((now or dt.datetime.now(dt.timezone.utc)) - parsed).total_seconds() / 86400
        return age if age >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _path_value(value, path):
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _dependencies(evidence):
    value = evidence.get("dependencies", evidence.get("package_names", []))
    if not isinstance(value, list):
        return None
    if any(not isinstance(item, str) or not item for item in value):
        return None
    return set(value)


def _matches_compatibility(actual, required):
    if not isinstance(actual, dict) or not isinstance(required, dict):
        return False
    for path, expected in required.items():
        if not isinstance(path, str) or not path or _path_value(actual, path) != expected:
            return False
    return True


def _normalise_query_vector(record, model, source_hash=None, identity=None):
    structured = record if isinstance(record, dict) else None
    vector = structured.get("vector") if structured is not None else record
    if not is_valid_vector(vector):
        return None
    requested_model = structured.get("model") if structured is not None else model
    if not isinstance(requested_model, str) or not requested_model or (model is not None and model != requested_model):
        return None
    requested_hash = structured.get("source_hash") if structured is not None else source_hash
    requested_identity = structured.get("identity") if structured is not None else identity
    if requested_hash is not None or requested_identity is not None:
        if not isinstance(requested_hash, str) or not requested_hash or not isinstance(requested_identity, str) or not requested_identity:
            return None
        if requested_identity != embedding_identity(requested_model, requested_hash):
            return None
    return vector, requested_model


def _stored_similarity(asset, query_vector, model):
    derived = asset.get("derived") or {}
    vector_entry = derived.get("vector") if isinstance(derived, dict) else None
    stored = vector_entry.get("value") if isinstance(vector_entry, dict) else None
    evidence_hash = asset.get("evidence_hash")
    identity = vector_entry.get("identity") if isinstance(vector_entry, dict) else None
    if not isinstance(evidence_hash, str) or not evidence_hash or not vector_is_compatible(
        stored,
        identity,
        model=model,
        source_hash=evidence_hash,
        dimension=len(query_vector),
    ):
        return None
    vector = stored["vector"]
    denominator = math.sqrt(sum(value * value for value in query_vector)) * math.sqrt(sum(value * value for value in vector))
    if not denominator:
        return None
    similarity = sum(left * right for left, right in zip(query_vector, vector)) / denominator
    return similarity if math.isfinite(similarity) else None


def _validate_query(query):
    if not isinstance(query, dict):
        raise ValueError("query must be an object")
    ecosystem = query.get("ecosystem")
    if not isinstance(ecosystem, str) or not ecosystem:
        raise ValueError("query.ecosystem is required")
    category = query.get("category")
    if category is not None and (not isinstance(category, str) or not category):
        raise ValueError("query.category must be a non-empty string")
    top_n = query.get("top_n", 3)
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 1:
        raise ValueError("query.top_n must be a positive integer")
    max_age = query.get("max_age_days", 180)
    if isinstance(max_age, bool) or not isinstance(max_age, (int, float)) or not math.isfinite(float(max_age)) or max_age < 0:
        raise ValueError("query.max_age_days must be a finite non-negative number")
    compatibility = query.get("required_compatibility", {})
    filters = query.get("evidence_filters", {})
    dependencies = query.get("dependencies", [])
    hashes = query.get("evidence_hashes")
    asset_ids = query.get("asset_ids")
    if not isinstance(compatibility, dict) or not isinstance(filters, dict):
        raise ValueError("compatibility and evidence_filters must be objects")
    if not isinstance(dependencies, list) or any(not isinstance(item, str) or not item for item in dependencies):
        raise ValueError("query.dependencies must be a list of non-empty strings")
    if hashes is not None and not (
        isinstance(hashes, str)
        or (isinstance(hashes, list) and all(isinstance(item, str) and item for item in hashes))
    ):
        raise ValueError("query.evidence_hashes must be a string or list of strings")
    if asset_ids is not None and (not isinstance(asset_ids, list) or any(not isinstance(item, str) or not item for item in asset_ids)):
        raise ValueError("query.asset_ids must be a list of non-empty strings")
    query_vector = query.get("query_vector")
    model = query.get("model")
    normalised_vector = None
    if query_vector is not None:
        normalised_vector = _normalise_query_vector(
            query_vector,
            model,
            query.get("query_source_hash"),
            query.get("query_vector_identity"),
        )
        if normalised_vector is None:
            raise ValueError("query vector, model, or vector identity is invalid")
    return {
        "ecosystem": ecosystem,
        "category": category,
        "top_n": top_n,
        "max_age_days": float(max_age),
        "compatibility": compatibility,
        "filters": filters,
        "dependencies": set(dependencies),
        "hashes": {hashes} if isinstance(hashes, str) else set(hashes) if hashes is not None else None,
        "asset_ids": set(asset_ids) if asset_ids is not None else None,
        "vector": normalised_vector[0] if normalised_vector else None,
        "model": normalised_vector[1] if normalised_vector else None,
    }


def query_connection(conn, query):
    """Query an initialized catalog connection without network or mutation."""
    try:
        request = _validate_query(query)
        cursor = conn.execute("SELECT * FROM assets WHERE ecosystem=? ORDER BY asset_id", (request["ecosystem"],))
        columns = [column[0] for column in cursor.description]
        candidates = []
        now = dt.datetime.now(dt.timezone.utc)
        for values in cursor.fetchall():
            stored = dict(zip(columns, values))
            if request["asset_ids"] is not None and stored["asset_id"] not in request["asset_ids"]:
                continue
            try:
                evidence = json.loads(stored["evidence_json"])
                derived = json.loads(stored["derived_json"])
                source = json.loads(stored["source_json"])
                license_info = json.loads(stored["license_json"])
                compatibility = json.loads(stored["compatibility_json"])
            except (TypeError, ValueError, json.JSONDecodeError):
                return {"status": "SETUP_ERROR", "results": [], "error": "malformed stored asset JSON"}
            if not all(isinstance(item, dict) for item in (evidence, derived, license_info, compatibility)):
                return {"status": "SETUP_ERROR", "results": [], "error": "malformed stored asset record"}
            if request["category"] is not None and evidence.get("category") != request["category"]:
                continue
            if any(_path_value(evidence, path) != expected for path, expected in request["filters"].items()):
                continue
            if not _matches_compatibility(compatibility, request["compatibility"]):
                continue
            age = _age_days(evidence.get("fetched_at"), now)
            if age is None or age > request["max_age_days"]:
                continue
            evidence_hash = stored.get("evidence_hash")
            if not isinstance(evidence_hash, str) or not evidence_hash:
                continue
            if request["hashes"] is not None and evidence_hash not in request["hashes"]:
                continue
            dependencies = _dependencies(evidence)
            if dependencies is None:
                return {"status": "SETUP_ERROR", "results": [], "error": "malformed dependency evidence"}
            overlap = len(request["dependencies"] & dependencies)
            similarity = 0.0
            if request["vector"] is not None:
                similarity = _stored_similarity(
                    {"derived": derived, "evidence_hash": evidence_hash}, request["vector"], request["model"]
                )
                if similarity is None:
                    return {"status": "SETUP_ERROR", "results": [], "error": "invalid or stale stored vector"}
            candidates.append(
                {
                    "asset_id": stored["asset_id"],
                    "ecosystem": stored["ecosystem"],
                    "name": stored["name"],
                    "version": stored["version"],
                    "source": source,
                    "license": license_info,
                    "compatibility": compatibility,
                    "evidence_hash": evidence_hash,
                    "evidence": evidence,
                    "derived": derived,
                    "dependency_overlap": overlap,
                    "similarity": similarity,
                }
            )
        candidates.sort(key=lambda item: (-item["dependency_overlap"], -item["similarity"], item["name"], item["asset_id"]))
        return {"status": "HIT" if candidates else "MISS", "results": candidates[: request["top_n"]]}
    except (AttributeError, KeyError, TypeError, ValueError, sqlite3.DatabaseError) as error:
        return {"status": "SETUP_ERROR", "results": [], "error": str(error)}


def query(database, query):
    """Read-only database query; a missing DB is a setup error, never created."""
    if not isinstance(database, (str, os.PathLike)) or not os.path.isfile(database):
        return {"status": "SETUP_ERROR", "results": [], "error": "catalog database does not exist"}
    path = Path(database).resolve().as_posix()
    uri = "file:{}?mode=ro".format(quote(path, safe="/:"))
    conn = None
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=10)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        has_assets = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='assets'").fetchone()
        if version != asset_catalog.SCHEMA_VERSION or has_assets is None:
            return {"status": "SETUP_ERROR", "results": [], "error": "catalog schema is not initialized"}
        return query_connection(conn, query)
    except (OSError, TypeError, sqlite3.DatabaseError) as error:
        return {"status": "SETUP_ERROR", "results": [], "error": str(error)}
    finally:
        if conn is not None:
            conn.close()


def _validate_refresh(evidence):
    asset_catalog._validate_evidence(evidence)
    record = evidence["evidence"].get("fetched_at")
    if not isinstance(record, str) or not record:
        raise ValueError("refresh evidence.evidence fetched_at is required")
    try:
        parsed = dt.datetime.fromisoformat(record.replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("refresh evidence.evidence fetched_at must be ISO-8601") from error
    if parsed.tzinfo is None:
        raise ValueError("refresh evidence.evidence fetched_at must include a timezone")
    if parsed > dt.datetime.now(dt.timezone.utc):
        raise ValueError("refresh evidence.evidence fetched_at cannot be in the future")


def refresh_connection(conn, evidence):
    """Validate a complete snapshot before atomically upserting on a caller connection."""
    _validate_refresh(evidence)
    return asset_catalog.upsert_connection(conn, evidence)


def refresh(database, evidence):
    """Store a complete evidence snapshot after validating it before mutation."""
    _validate_refresh(evidence)
    return asset_catalog.upsert(database, evidence)


def _load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main_recall(argv=None):
    parser = argparse.ArgumentParser(description="Offline deterministic reusable-asset recall")
    parser.add_argument("--database", required=True)
    parser.add_argument("--query", required=True, help="JSON query file")
    args = parser.parse_args(argv)
    try:
        result = query(args.database, _load_json(args.query))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        result = {"status": "SETUP_ERROR", "results": [], "error": str(error)}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True))
    return {"HIT": 0, "MISS": 2, "SETUP_ERROR": 1}[result["status"]]


def main_refresh(argv=None):
    parser = argparse.ArgumentParser(description="Refresh one generic asset from complete local evidence")
    parser.add_argument("--database", required=True)
    parser.add_argument("evidence_json")
    args = parser.parse_args(argv)
    try:
        result = refresh(args.database, _load_json(args.evidence_json))
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True))
        return 0
    except (OSError, ValueError, sqlite3.DatabaseError, json.JSONDecodeError) as error:
        print("asset-refresh: {}".format(error), file=sys.stderr)
        return 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "refresh":
        return main_refresh(argv[1:])
    if argv and argv[0] == "recall":
        argv = argv[1:]
    return main_recall(argv)


if __name__ == "__main__":
    raise SystemExit(main())
