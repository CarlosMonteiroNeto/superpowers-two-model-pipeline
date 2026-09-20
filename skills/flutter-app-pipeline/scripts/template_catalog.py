#!/usr/bin/env python3
"""Transactional local catalog for scored Flutter templates."""

import argparse
import json
import os
import sqlite3
import sys


_COLUMNS = {
    "score_verdict": "TEXT", "evidence_hash": "TEXT", "readme_text": "TEXT", "pubspec_text": "TEXT", "tree_text": "TEXT",
    "generic_category": "TEXT", "specific_category": "TEXT", "original_implementations": "TEXT",
    "constraints": "TEXT", "triage_decision": "TEXT", "triage_confidence": "REAL", "triage_policy_version": "TEXT",
    "triage_actor": "TEXT", "vector_identity": "TEXT", "adoption_history": "TEXT NOT NULL DEFAULT '[]'",
    "package_names": "TEXT", "fetched_at": "TEXT", "vector": "TEXT",
}


def _connect(path=None):
    conn = sqlite3.connect(path or os.path.join(os.getcwd(), "template-catalog.sqlite3"))
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute("CREATE TABLE IF NOT EXISTS templates (owner_repo TEXT PRIMARY KEY, category TEXT NOT NULL, project TEXT NOT NULL, score_report TEXT NOT NULL)")
        existing = {row[1] for row in conn.execute("PRAGMA table_info(templates)")}
        for name, definition in _COLUMNS.items():
            if name not in existing:
                conn.execute("ALTER TABLE templates ADD COLUMN {} {}".format(name, definition))
        conn.execute("UPDATE templates SET score_verdict=json_extract(score_report, '$.verdict') WHERE score_verdict IS NULL")
    return conn


def _validate(owner_repo, category, project, score_report):
    if not isinstance(owner_repo, str) or owner_repo.count("/") != 1 or not all(owner_repo.split("/")):
        raise ValueError("owner_repo must be OWNER/REPO")
    if not isinstance(category, str) or not category or not isinstance(project, str) or not project:
        raise ValueError("category and project are required")
    if not isinstance(score_report, dict) or not isinstance(score_report.get("verdict"), str):
        raise ValueError("score_report.verdict is required")


def upsert_template(conn, owner_repo, category, project, score_report, evidence=None, *, generic_category=None, specific_category=None, original_implementations=None):
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
    evidence_hash = evidence.get("evidence_hash")
    values = (owner_repo, category, project, json.dumps(score_report, ensure_ascii=False, sort_keys=True), score_report["verdict"], evidence_hash,
              evidence.get("readme_text"), evidence.get("pubspec_text"), evidence.get("tree_text"), generic_category, specific_category, original_implementations,
              json.dumps(evidence.get("constraints"), ensure_ascii=False, sort_keys=True) if evidence.get("constraints") is not None else None)
    with conn:
        old = conn.execute("SELECT evidence_hash FROM templates WHERE owner_repo=?", (owner_repo,)).fetchone()
        changed = old is not None and old["evidence_hash"] != evidence_hash
        conn.execute("INSERT INTO templates (owner_repo, category, project, score_report, score_verdict, evidence_hash, readme_text, pubspec_text, tree_text, generic_category, specific_category, original_implementations, constraints, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(owner_repo) DO UPDATE SET category=excluded.category, project=excluded.project, score_report=excluded.score_report, score_verdict=excluded.score_verdict, evidence_hash=excluded.evidence_hash, readme_text=excluded.readme_text, pubspec_text=excluded.pubspec_text, tree_text=excluded.tree_text, generic_category=excluded.generic_category, specific_category=excluded.specific_category, original_implementations=excluded.original_implementations, constraints=excluded.constraints, fetched_at=excluded.fetched_at", values + (evidence.get("fetched_at"),))
        if evidence.get("vector") is not None:
            vector = evidence["vector"]
            conn.execute("UPDATE templates SET vector=?, vector_identity=? WHERE owner_repo=?", (json.dumps(vector, sort_keys=True), vector.get("identity") if isinstance(vector, dict) else None, owner_repo))
        if changed:
            conn.execute("UPDATE templates SET triage_decision=NULL, triage_confidence=NULL, triage_policy_version=NULL, triage_actor=NULL, vector_identity=NULL WHERE owner_repo=?", (owner_repo,))


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
                if conn.execute("UPDATE templates SET adoption_history=? WHERE owner_repo=?", (args.value, args.owner_repo)).rowcount != 1: raise ValueError("unknown owner_repo")
        return 0
    except (OSError, ValueError, json.JSONDecodeError, sqlite3.DatabaseError) as error:
        print("template-catalog: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__": sys.exit(main())
