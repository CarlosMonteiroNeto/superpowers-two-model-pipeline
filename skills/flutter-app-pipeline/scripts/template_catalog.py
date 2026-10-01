#!/usr/bin/env python3
"""Transactional local catalog for scored Flutter templates."""

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "two-model-sdd-pipeline" / "scripts"
sys.path.insert(0, str(SHARED_SCRIPTS))
import asset_catalog
import asset_recall


_COLUMNS = {
    "score_verdict": "TEXT", "evidence_hash": "TEXT", "readme_text": "TEXT", "pubspec_text": "TEXT", "tree_text": "TEXT",
    "generic_category": "TEXT", "specific_category": "TEXT", "original_implementations": "TEXT",
    "constraints": "TEXT", "triage_decision": "TEXT", "triage_confidence": "REAL", "triage_policy_version": "TEXT",
    "triage_actor": "TEXT", "vector_identity": "TEXT", "adoption_history": "TEXT NOT NULL DEFAULT '[]'", "asset_id": "TEXT",
    "package_names": "TEXT", "fetched_at": "TEXT", "vector": "TEXT",
}


def _connect(path=None):
    database = path or os.path.join(os.getcwd(), "template-catalog.sqlite3")
    conn = asset_catalog.connect(database)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute("CREATE TABLE IF NOT EXISTS templates (owner_repo TEXT PRIMARY KEY, category TEXT NOT NULL, project TEXT NOT NULL, score_report TEXT NOT NULL)")
        existing = {row[1] for row in conn.execute("PRAGMA table_info(templates)")}
        for name, definition in _COLUMNS.items():
            if name not in existing:
                conn.execute("ALTER TABLE templates ADD COLUMN {} {}".format(name, definition))
        conn.execute("UPDATE templates SET score_verdict=json_extract(score_report, '$.verdict') WHERE score_verdict IS NULL")
        missing = conn.execute("SELECT * FROM templates WHERE asset_id IS NULL ORDER BY owner_repo").fetchall()
        for row in missing:
            generic = asset_catalog.upsert_connection(conn, _asset_evidence(dict(row)))
            conn.execute("UPDATE templates SET asset_id=? WHERE owner_repo=?", (generic["asset_id"], row["owner_repo"]))
    return conn


def _validate(owner_repo, category, project, score_report):
    if not isinstance(owner_repo, str) or owner_repo.count("/") != 1 or not all(owner_repo.split("/")):
        raise ValueError("owner_repo must be OWNER/REPO")
    if not isinstance(category, str) or not category or not isinstance(project, str) or not project:
        raise ValueError("category and project are required")
    if not isinstance(score_report, dict) or not isinstance(score_report.get("verdict"), str):
        raise ValueError("score_report.verdict is required")


def _asset_evidence(row, *, evidence=None):
    evidence = evidence or {}
    try:
        constraints = json.loads(evidence.get("constraints", row.get("constraints") or "{}")) if isinstance(evidence.get("constraints", row.get("constraints") or {}), str) else evidence.get("constraints", row.get("constraints") or {})
        score_report = row.get("score_report")
        if isinstance(score_report, str):
            score_report = json.loads(score_report or "{}")
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("template evidence contains malformed JSON") from error
    if not isinstance(constraints, dict) or not isinstance(score_report, dict):
        raise ValueError("template constraints and score report must be objects")
    license_info = constraints.get("license")
    if not isinstance(license_info, dict) or license_info.get("status") not in ("known", "unknown"):
        license_info = dict(asset_catalog.UNKNOWN_LICENSE)
    compatibility = {key: value for key, value in constraints.items() if key != "license"}
    owner_repo = row["owner_repo"]
    payload_evidence = {
        "score_report": score_report,
        "category": row.get("category"),
        "project": row.get("project"),
        "readme_text": evidence.get("readme_text", row.get("readme_text")),
        "pubspec_text": evidence.get("pubspec_text", row.get("pubspec_text")),
        "tree_text": evidence.get("tree_text", row.get("tree_text")),
        "generic_category": evidence.get("generic_category", row.get("generic_category")),
        "specific_category": evidence.get("specific_category", row.get("specific_category")),
        "original_implementations": evidence.get("original_implementations", row.get("original_implementations")),
        "fetched_at": evidence.get("fetched_at", row.get("fetched_at")),
    }
    evidence_hash = evidence.get("evidence_hash") or row.get("evidence_hash")
    if not isinstance(evidence_hash, str) or not evidence_hash:
        evidence_hash = hashlib.sha256(json.dumps(payload_evidence, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    record = {
        "ecosystem": "flutter",
        "name": owner_repo,
        "version": "catalog-entry",
        "source": {"type": "github", "uri": "https://github.com/" + owner_repo},
        "license": license_info,
        "evidence_hash": evidence_hash,
        "compatibility": compatibility,
        "evidence": payload_evidence,
    }
    if "derived" in evidence:
        record["derived"] = evidence["derived"]
    return record


def upsert_template(conn, owner_repo, category, project, score_report, evidence=None, *, generic_category=None, specific_category=None, original_implementations=None, refresh=False):
    """Insert/update a template without conflating scoring, triage, or adoption."""
    _validate(owner_repo, category, project, score_report)
    evidence = evidence or {}
    generic_category = generic_category or evidence.get("generic_category") or category
    specific_category = specific_category or evidence.get("specific_category") or category
    original_implementations = original_implementations if original_implementations is not None else evidence.get("original_implementations")
    if original_implementations is None:
        original_implementations = project
    if not isinstance(original_implementations, str) or not original_implementations:
        raise ValueError("original_implementations is required")
    legacy_evidence_hash = evidence.get("evidence_hash")
    previous = conn.execute("SELECT * FROM templates WHERE owner_repo=?", (owner_repo,)).fetchone()
    mapped_row = {
        "owner_repo": owner_repo,
        "category": category,
        "project": project,
        "score_report": json.dumps(score_report, ensure_ascii=False, sort_keys=True),
        "evidence_hash": legacy_evidence_hash,
        "readme_text": evidence.get("readme_text"),
        "pubspec_text": evidence.get("pubspec_text"),
        "tree_text": evidence.get("tree_text"),
        "generic_category": generic_category,
        "specific_category": specific_category,
        "original_implementations": original_implementations,
        "constraints": json.dumps(evidence.get("constraints"), ensure_ascii=False, sort_keys=True) if evidence.get("constraints") is not None else None,
        "fetched_at": evidence.get("fetched_at"),
    }
    generic = _asset_evidence(mapped_row, evidence=evidence)
    values = (owner_repo, category, project, json.dumps(score_report, ensure_ascii=False, sort_keys=True), score_report["verdict"], legacy_evidence_hash,
              evidence.get("readme_text"), evidence.get("pubspec_text"), evidence.get("tree_text"), generic_category, specific_category, original_implementations,
              json.dumps(evidence.get("constraints"), ensure_ascii=False, sort_keys=True) if evidence.get("constraints") is not None else None)
    with conn:
        old = previous
        changed = old is not None and old["evidence_hash"] != legacy_evidence_hash
        conn.execute("INSERT INTO templates (owner_repo, category, project, score_report, score_verdict, evidence_hash, readme_text, pubspec_text, tree_text, generic_category, specific_category, original_implementations, constraints, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(owner_repo) DO UPDATE SET category=excluded.category, project=excluded.project, score_report=excluded.score_report, score_verdict=excluded.score_verdict, evidence_hash=excluded.evidence_hash, readme_text=excluded.readme_text, pubspec_text=excluded.pubspec_text, tree_text=excluded.tree_text, generic_category=excluded.generic_category, specific_category=excluded.specific_category, original_implementations=excluded.original_implementations, constraints=excluded.constraints, fetched_at=excluded.fetched_at", values + (evidence.get("fetched_at"),))
        if evidence.get("vector") is not None:
            vector = evidence["vector"]
            conn.execute("UPDATE templates SET vector=?, vector_identity=? WHERE owner_repo=?", (json.dumps(vector, sort_keys=True), vector.get("identity") if isinstance(vector, dict) else None, owner_repo))
        if changed:
            conn.execute("UPDATE templates SET triage_decision=NULL, triage_confidence=NULL, triage_policy_version=NULL, triage_actor=NULL, vector_identity=NULL WHERE owner_repo=?", (owner_repo,))
        if not changed and previous is not None:
            derived = {}
            triage = {key: previous[key] for key in ("triage_decision", "triage_confidence", "triage_policy_version", "triage_actor") if previous[key] is not None}
            if triage:
                derived["triage"] = triage
            if previous["vector"] is not None or previous["vector_identity"] is not None:
                try:
                    vector_value = json.loads(previous["vector"]) if previous["vector"] else None
                except json.JSONDecodeError:
                    vector_value = None
                derived["vector"] = {"value": vector_value, "identity": previous["vector_identity"]}
            if derived:
                generic["derived"] = derived
        generic_result = asset_recall.refresh_connection(conn, generic) if refresh else asset_catalog.upsert_connection(conn, generic)
        conn.execute("UPDATE templates SET asset_id=? WHERE owner_repo=?", (generic_result["asset_id"], owner_repo))


def list_templates(conn, category=None, *, include_rejected=False):
    query, args = "SELECT * FROM templates", ()
    if category is not None:
        query, args = query + " WHERE category=?", (category,)
    if not include_rejected:
        query += " AND " if " WHERE " in query else " WHERE "
        query += "(triage_decision IS NULL OR triage_decision != 'reject')"
    return [dict(row) for row in conn.execute(query + " ORDER BY owner_repo", args)]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Manage template catalog")
    parser.add_argument("--database")
    commands = parser.add_subparsers(dest="command")
    add = commands.add_parser("add")
    add.add_argument("owner_repo"); add.add_argument("category"); add.add_argument("project"); add.add_argument("score_report"); add.add_argument("--evidence")
    listing = commands.add_parser("list"); listing.add_argument("--category")
    outcome = commands.add_parser("outcome"); outcome.add_argument("owner_repo"); outcome.add_argument("value")
    args = parser.parse_args(argv)
    if not args.command:
        return 2
    try:
        conn = _connect(args.database)
        if args.command == "add":
            with open(args.score_report, encoding="utf-8") as handle: score = json.load(handle)
            evidence = None
            if args.evidence:
                with open(args.evidence, encoding="utf-8") as handle: evidence = json.load(handle)
            upsert_template(conn, args.owner_repo, args.category, args.project, score, evidence)
        elif args.command == "list": print(json.dumps(list_templates(conn, args.category), ensure_ascii=False))
        else:
            with conn:
                row = conn.execute("SELECT * FROM templates WHERE owner_repo=?", (args.owner_repo,)).fetchone()
                if row is None: raise ValueError("unknown owner_repo")
                if not row["asset_id"]:
                    generic = asset_catalog.upsert_connection(conn, _asset_evidence(dict(row)))
                    asset_id = generic["asset_id"]
                else:
                    asset_id = row["asset_id"]
                conn.execute("UPDATE templates SET adoption_history=? WHERE owner_repo=?", (args.value, args.owner_repo))
                asset_catalog.record_outcome_connection(conn, {"asset_id": asset_id, "outcome": args.value, "actor": "flutter-template-catalog-cli", "provenance": {"owner_repo": args.owner_repo}})
        return 0
    except (OSError, ValueError, json.JSONDecodeError, sqlite3.DatabaseError) as error:
        print("template-catalog: {}".format(error), file=sys.stderr)
        return 1
    finally:
        if "conn" in locals() and conn is not None:
            conn.close()


if __name__ == "__main__": sys.exit(main())
