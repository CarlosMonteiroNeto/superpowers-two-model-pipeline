#!/usr/bin/env python3
"""Evidence collection boundary for template catalog entries."""

import argparse
import base64
import datetime
import hashlib
import json
import os
import re
import sys

from template_score import GH_API, _fetch_json, compute_score, gather_data


class EvidenceCollectionError(RuntimeError):
    """The upstream evidence set could not be collected completely."""


def _text(response):
    if not isinstance(response, dict):
        return None
    content = (response or {}).get("content")
    if not content:
        return None
    try:
        return base64.b64decode(content).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def _constraint(value):
    return {"status": "known" if value is not None else "unknown", "value": value}


def _sdk_constraint(pubspec_text):
    if pubspec_text is None:
        return _constraint(None)
    match = re.search(r"^\s*sdk:\s*['\"]?([^'\"\n]+)", pubspec_text, re.MULTILINE)
    if not match:
        return _constraint(None)
    version = match.group(1).strip()
    lower = re.search(r">=\s*(\d+(?:\.\d+)*)", version)
    return _constraint(">=" + lower.group(1) if lower else version)


def collect_evidence(owner_repo, github_token=None, fetch_json=None):
    """Return the complete, hashable evidence record for one repository.

    ``fetch_json`` is injected by tests.  Production scoring remains delegated
    to the archived scorer so its public calculation does not change.
    """
    if not isinstance(owner_repo, str) or owner_repo.count("/") != 1:
        raise ValueError("owner_repo must be OWNER/REPO")
    owner, repo = owner_repo.split("/", 1)
    if not owner or not repo:
        raise ValueError("owner_repo must be OWNER/REPO")
    fetch = fetch_json or _fetch_json

    def request(path, *, optional=False):
        try:
            return fetch("{}/repos/{}/{}{}".format(GH_API, owner, repo, path), github_token)
        except (OSError, ValueError, KeyError, TypeError) as error:
            if optional:
                return None
            raise EvidenceCollectionError("failed to collect {}: {}".format(path or "repository", error)) from error

    repo_data = request("")
    if not isinstance(repo_data, dict):
        raise EvidenceCollectionError("repository response is not an object")
    # README and pubspec absence is valid evidence. Transport failures for the
    # required scoring endpoints below remain hard collection failures.
    readme_text = _text(request("/readme", optional=True))
    pubspec_text = _text(request("/contents/pubspec.yaml", optional=True))
    tree = request("/git/trees/HEAD?recursive=1")
    tree_text = None
    if isinstance(tree, dict) and isinstance(tree.get("tree"), list):
        paths = [entry.get("path") for entry in tree["tree"] if isinstance(entry, dict) and isinstance(entry.get("path"), str)]
        tree_text = "\n".join(sorted(paths))
    else:
        raise EvidenceCollectionError("repository tree response is incomplete")

    # ``strict=True`` prevents template_score's legacy best-effort fallback
    # from turning an outage into a synthetic low quality score. README is an
    # optional field and remains explicitly null when absent.
    try:
        raw_score = gather_data(owner, repo, github_token, fetch_json=fetch, strict=True)
    except Exception as error:
        raise EvidenceCollectionError("failed to collect scoring evidence: {}".format(error)) from error
    score_report = compute_score(raw_score)
    score_report["data"] = raw_score

    license_id = None
    if isinstance(repo_data, dict):
        license_id = ((repo_data.get("license") or {}).get("spdx_id") or "").lower() or None
    license_value = None
    if license_id:
        license_value = "mit" if "mit" in license_id else "apache" if "apache" in license_id else "bsd" if "bsd" in license_id else "other"
    record = {
        "owner_repo": owner_repo,
        "score_report": score_report,
        "readme_text": readme_text,
        "pubspec_text": pubspec_text,
        "tree_text": tree_text,
        "constraints": {"license": _constraint(license_value), "sdk": _sdk_constraint(pubspec_text)},
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
    }
    hash_input = {key: value for key, value in record.items() if key != "fetched_at"}
    record["evidence_hash"] = hashlib.sha256(json.dumps(hash_input, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description="Collect deterministic template evidence")
    parser.add_argument("owner_repo")
    parser.add_argument("--output", required=True)
    parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN"))
    args = parser.parse_args(argv)
    try:
        record = collect_evidence(args.owner_repo, args.github_token)
        with open(args.output, "x", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2)
        return 0
    except EvidenceCollectionError as error:
        print("template-evidence: {}".format(error), file=sys.stderr)
        return 1
    except ValueError as error:
        print("template-evidence: {}".format(error), file=sys.stderr)
        return 2
    except (OSError, TypeError) as error:
        print("template-evidence: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
