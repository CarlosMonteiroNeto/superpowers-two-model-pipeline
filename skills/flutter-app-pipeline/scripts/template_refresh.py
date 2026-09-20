"""Explicit refresh using the evidence/scoring boundary."""
import argparse
import datetime
import json
import sys
from template_catalog import _connect, upsert_template
from template_evidence import EvidenceCollectionError, collect_evidence


_REQUIRED_EVIDENCE_FIELDS = (
    "owner_repo",
    "score_report",
    "readme_text",
    "pubspec_text",
    "tree_text",
    "constraints",
    "evidence_hash",
    "fetched_at",
)


def _validate_evidence(entry, evidence):
    if not isinstance(evidence, dict) or any(field not in evidence for field in _REQUIRED_EVIDENCE_FIELDS):
        raise ValueError("refresh evidence is incomplete")
    if evidence.get("owner_repo") != entry["owner_repo"]:
        raise ValueError("refresh evidence owner_repo does not match entry")
    if not isinstance(evidence.get("score_report"), dict) or not isinstance(evidence["score_report"].get("verdict"), str):
        raise ValueError("refresh score_report.verdict is required")
    if not isinstance(evidence.get("evidence_hash"), str) or not evidence["evidence_hash"]:
        raise ValueError("refresh evidence_hash is required")
    if not isinstance(evidence.get("constraints"), dict):
        raise ValueError("refresh constraints are required")
    fetched_at = evidence.get("fetched_at")
    if not isinstance(fetched_at, str) or not fetched_at:
        raise ValueError("refresh fetched_at is required")
    try:
        parsed = datetime.datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("refresh fetched_at must be ISO-8601") from error
    if parsed.tzinfo is None:
        raise ValueError("refresh fetched_at must include a timezone")

def refresh_one(conn, entry, github_token=None, collect=None):
    if not isinstance(entry, dict) or not isinstance(entry.get("owner_repo"), str): raise ValueError("entry.owner_repo is required")
    evidence=(collect or collect_evidence)(entry["owner_repo"], github_token)
    _validate_evidence(entry, evidence)
    upsert_template(conn, entry["owner_repo"], entry.get("category", ""), entry.get("project", entry["owner_repo"]), evidence["score_report"], evidence)
    return evidence

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("owner_repo"); p.add_argument("--database"); p.add_argument("--category", required=True); p.add_argument("--project", required=True); a=p.parse_args(argv)
    conn = None
    try:
        conn = _connect(a.database)
        print(json.dumps(refresh_one(conn, vars(a))))
        return 0
    except (OSError, ValueError, KeyError, EvidenceCollectionError): return 1
    finally:
        if conn is not None:
            conn.close()
if __name__ == "__main__": sys.exit(main())
