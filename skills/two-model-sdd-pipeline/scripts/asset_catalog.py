#!/usr/bin/env python3
"""Ecosystem-neutral SQLite catalog for versioned reusable assets."""

import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import uuid


SCHEMA_VERSION = 1
DEFAULT_DATABASE = "asset-catalog.sqlite3"
UNKNOWN_LICENSE = {"status": "unknown", "value": None}
_IDENTITY_FIELDS = ("ecosystem", "name", "version", "source", "license", "compatibility")


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _validate_evidence(evidence):
    if not isinstance(evidence, dict):
        raise ValueError("asset evidence must be an object")
    for field in ("ecosystem", "name", "version", "evidence_hash"):
        value = evidence.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("{}.{} is required".format("evidence", field))
    source = evidence.get("source")
    if not ((isinstance(source, str) and source.strip()) or (isinstance(source, dict) and source)):
        raise ValueError("evidence.source must be a non-empty string or object")
    license_info = evidence.get("license")
    if not isinstance(license_info, dict) or license_info.get("status") not in ("known", "unknown"):
        raise ValueError("evidence.license.status must be known or unknown")
    if license_info["status"] == "known":
        if not isinstance(license_info.get("value"), str) or not license_info["value"].strip():
            raise ValueError("known license evidence requires a value")
    elif license_info.get("value") is not None:
        raise ValueError("unknown license evidence must have a null value")
    for field in ("compatibility", "evidence"):
        if not isinstance(evidence.get(field), dict):
            raise ValueError("evidence.{} must be an object".format(field))
    if "derived" in evidence and not isinstance(evidence["derived"], dict):
        raise ValueError("evidence.derived must be an object")
    try:
        _canonical(evidence)
    except (TypeError, ValueError) as error:
        raise ValueError("asset evidence must be JSON-safe: {}".format(error)) from error


def _identity(evidence):
    return {field: evidence[field] for field in _IDENTITY_FIELDS} | {"evidence_hash": evidence["evidence_hash"]}


def _identity_key(evidence):
    return _canonical({field: evidence[field] for field in _IDENTITY_FIELDS})


def _asset_id(identity_key):
    return hashlib.sha256(identity_key.encode("utf-8")).hexdigest()


def _tables(conn):
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _backup_target(database):
    candidate = database + ".bak"
    index = 1
    while os.path.exists(candidate):
        candidate = database + ".bak.{}".format(index)
        index += 1
    return candidate


def backup_path(database):
    """Return the first backup path created for a migrated database."""
    candidate = database + ".bak"
    if os.path.isfile(candidate):
        return candidate
    index = 1
    while os.path.isfile(database + ".bak.{}".format(index)):
        return database + ".bak.{}".format(index)
    return candidate


def _backup(conn, database):
    target = _backup_target(database)
    directory = os.path.dirname(os.path.abspath(target))
    fd, temporary = tempfile.mkstemp(prefix=".asset-catalog-backup-", suffix=".sqlite3", dir=directory)
    os.close(fd)
    try:
        backup_conn = sqlite3.connect(temporary)
        try:
            conn.backup(backup_conn)
            backup_conn.commit()
        finally:
            backup_conn.close()
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return target


def _create_schema(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS assets (
            asset_id TEXT PRIMARY KEY,
            identity_key TEXT NOT NULL UNIQUE,
            ecosystem TEXT NOT NULL,
            name TEXT NOT NULL,
            version TEXT NOT NULL,
            source_json TEXT NOT NULL,
            license_json TEXT NOT NULL,
            compatibility_json TEXT NOT NULL,
            evidence_hash TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            derived_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS adoption_outcomes (
            outcome_id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
            outcome TEXT NOT NULL,
            actor TEXT NOT NULL,
            provenance_json TEXT NOT NULL,
            occurred_at TEXT NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS adoption_outcomes_asset_idx ON adoption_outcomes(asset_id, occurred_at)")


def _legacy_asset(row):
    legacy = dict(row)
    owner_repo = legacy.get("owner_repo")
    if not isinstance(owner_repo, str) or owner_repo.count("/") != 1 or not all(owner_repo.split("/")):
        raise ValueError("legacy template owner_repo must be OWNER/REPO")
    try:
        score_report = json.loads(legacy.get("score_report") or "{}")
        constraints = json.loads(legacy.get("constraints") or "{}")
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("legacy template JSON is malformed") from error
    if not isinstance(score_report, dict) or not isinstance(constraints, dict):
        raise ValueError("legacy template score_report and constraints must be objects")
    license_info = constraints.pop("license", None)
    if not isinstance(license_info, dict) or license_info.get("status") not in ("known", "unknown"):
        license_info = dict(UNKNOWN_LICENSE)
    evidence_hash = legacy.get("evidence_hash")
    if not isinstance(evidence_hash, str) or not evidence_hash:
        evidence_hash = hashlib.sha256(_canonical(legacy).encode("utf-8")).hexdigest()
    derived = {}
    triage = {
        key: legacy.get(key)
        for key in ("triage_decision", "triage_confidence", "triage_policy_version", "triage_actor")
        if legacy.get(key) is not None
    }
    if triage:
        derived["triage"] = triage
    if legacy.get("vector") is not None or legacy.get("vector_identity") is not None:
        derived["vector"] = {"value": legacy.get("vector"), "identity": legacy.get("vector_identity")}
    return {
        "ecosystem": "flutter",
        "name": owner_repo,
        "version": "catalog-entry",
        "source": {"type": "github", "uri": "https://github.com/" + owner_repo},
        "license": license_info,
        "evidence_hash": evidence_hash,
        "compatibility": constraints,
        "evidence": {"legacy_template": legacy, "score_report": score_report},
        "derived": derived,
    }


def initialize_connection(conn, database=None, *, backup_existing=True):
    """Initialize or transactionally migrate a connection; return its version."""
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise ValueError("asset catalog schema is newer than this runtime")
    tables = _tables(conn)
    if version == SCHEMA_VERSION and "assets" in tables:
        return version

    existing = bool(database and database != ":memory:" and os.path.isfile(database) and os.path.getsize(database) > 0)
    if backup_existing and existing:
        _backup(conn, database)

    conn.execute("BEGIN IMMEDIATE")
    try:
        _create_schema(conn)
        if "templates" in tables:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(templates)")}
            rows = conn.execute("SELECT * FROM templates ORDER BY owner_repo").fetchall() if "owner_repo" in columns else []
            for row in rows:
                _upsert_connection(conn, _legacy_asset(row))
        conn.execute("PRAGMA user_version={}".format(SCHEMA_VERSION))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return SCHEMA_VERSION


def connect(database=None):
    database = database or DEFAULT_DATABASE
    existed = database != ":memory:" and os.path.isfile(database) and os.path.getsize(database) > 0
    conn = sqlite3.connect(database, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        initialize_connection(conn, database, backup_existing=existed)
    except Exception:
        conn.close()
        raise
    return conn


def _row_asset(row, evidence_changed=False):
    identity = {
        "ecosystem": row["ecosystem"],
        "name": row["name"],
        "version": row["version"],
        "source": json.loads(row["source_json"]),
        "license": json.loads(row["license_json"]),
        "evidence_hash": row["evidence_hash"],
        "compatibility": json.loads(row["compatibility_json"]),
    }
    return {
        "asset_id": row["asset_id"],
        "identity": identity,
        "evidence_hash": row["evidence_hash"],
        "evidence": json.loads(row["evidence_json"]),
        "derived": json.loads(row["derived_json"]),
        "evidence_changed": evidence_changed,
    }


def _upsert_connection(conn, evidence):
    _validate_evidence(evidence)
    identity_key = _identity_key(evidence)
    asset_id = _asset_id(identity_key)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    old = conn.execute("SELECT evidence_hash, derived_json, created_at FROM assets WHERE asset_id=?", (asset_id,)).fetchone()
    changed = old is not None and old["evidence_hash"] != evidence["evidence_hash"]
    if "derived" in evidence:
        derived = evidence["derived"]
    elif changed:
        derived = {}
    elif old is not None:
        derived = json.loads(old["derived_json"])
    else:
        derived = {}
    conn.execute(
        """INSERT INTO assets (asset_id, identity_key, ecosystem, name, version, source_json,
            license_json, compatibility_json, evidence_hash, evidence_json, derived_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset_id) DO UPDATE SET evidence_hash=excluded.evidence_hash,
            evidence_json=excluded.evidence_json, derived_json=excluded.derived_json, updated_at=excluded.updated_at""",
        (
            asset_id,
            identity_key,
            evidence["ecosystem"],
            evidence["name"],
            evidence["version"],
            _canonical(evidence["source"]),
            _canonical(evidence["license"]),
            _canonical(evidence["compatibility"]),
            evidence["evidence_hash"],
            _canonical(evidence["evidence"]),
            _canonical(derived),
            old["created_at"] if old else now,
            now,
        ),
    )
    row = conn.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,)).fetchone()
    return _row_asset(row, evidence_changed=changed)


def upsert_connection(conn, evidence):
    """Upsert using an existing SQLite connection for compatibility adapters."""
    initialize_connection(conn)
    if conn.in_transaction:
        return _upsert_connection(conn, evidence)
    try:
        with conn:
            return _upsert_connection(conn, evidence)
    except sqlite3.IntegrityError as error:
        raise ValueError("asset identity conflicts with existing catalog data") from error


def upsert(database, evidence):
    _validate_evidence(evidence)
    conn = connect(database)
    try:
        return upsert_connection(conn, evidence)
    finally:
        conn.close()


def record_outcome_connection(conn, outcome):
    initialize_connection(conn)
    if not isinstance(outcome, dict):
        raise ValueError("outcome must be an object")
    asset_id = outcome.get("asset_id")
    value = outcome.get("outcome")
    actor = outcome.get("actor")
    provenance = outcome.get("provenance", {})
    if not isinstance(asset_id, str) or not asset_id:
        raise ValueError("outcome.asset_id is required")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("outcome.outcome is required")
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("outcome.actor is required")
    if not isinstance(provenance, dict):
        raise ValueError("outcome.provenance must be an object")
    try:
        provenance_json = _canonical(provenance)
    except (TypeError, ValueError) as error:
        raise ValueError("outcome.provenance must be JSON-safe") from error
    occurred_at = outcome.get("occurred_at") or dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    if not isinstance(occurred_at, str) or not occurred_at.strip():
        raise ValueError("outcome.occurred_at must be a non-empty string")
    if conn.execute("SELECT 1 FROM assets WHERE asset_id=?", (asset_id,)).fetchone() is None:
        raise ValueError("unknown asset_id")
    outcome_id = outcome.get("outcome_id") or str(uuid.uuid4())
    if conn.in_transaction:
        conn.execute(
            "INSERT INTO adoption_outcomes(outcome_id, asset_id, outcome, actor, provenance_json, occurred_at) VALUES (?, ?, ?, ?, ?, ?)",
            (outcome_id, asset_id, value, actor, provenance_json, occurred_at),
        )
    else:
        with conn:
            conn.execute(
                "INSERT INTO adoption_outcomes(outcome_id, asset_id, outcome, actor, provenance_json, occurred_at) VALUES (?, ?, ?, ?, ?, ?)",
                (outcome_id, asset_id, value, actor, provenance_json, occurred_at),
            )
    return {"outcome_id": outcome_id, "asset_id": asset_id, "outcome": value, "actor": actor, "provenance": provenance, "occurred_at": occurred_at}


def record_outcome(database, outcome):
    conn = connect(database)
    try:
        return record_outcome_connection(conn, outcome)
    finally:
        conn.close()


def list_outcomes(database, asset_id):
    conn = connect(database)
    try:
        rows = conn.execute("SELECT * FROM adoption_outcomes WHERE asset_id=? ORDER BY rowid", (asset_id,)).fetchall()
        return [
            {
                "outcome_id": row["outcome_id"],
                "asset_id": row["asset_id"],
                "outcome": row["outcome"],
                "actor": row["actor"],
                "provenance": json.loads(row["provenance_json"]),
                "occurred_at": row["occurred_at"],
            }
            for row in rows
        ]
    finally:
        conn.close()


def schema_version(database):
    conn = connect(database)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def _read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Manage the generic reusable-asset catalog")
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    commands = parser.add_subparsers(dest="command")
    add = commands.add_parser("upsert")
    add.add_argument("evidence_json")
    outcome = commands.add_parser("outcome")
    outcome.add_argument("outcome_json")
    listing = commands.add_parser("outcomes")
    listing.add_argument("asset_id")
    args = parser.parse_args(argv)
    if not args.command:
        return 2
    try:
        if args.command == "upsert":
            result = upsert(args.database, _read_json(args.evidence_json))
        elif args.command == "outcome":
            result = record_outcome(args.database, _read_json(args.outcome_json))
        else:
            result = list_outcomes(args.database, args.asset_id)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, sqlite3.DatabaseError, json.JSONDecodeError) as error:
        print("asset-catalog: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
