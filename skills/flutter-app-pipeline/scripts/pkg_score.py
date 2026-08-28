#!/usr/bin/env python3
"""Corrected Quality Score for a pub.dev package (no LLM involved).

Fetches pub.dev + GitHub REST and prints a JSON report with each weighted
criterion, the 0-100 total, and the gate verdict.

Usage:
  pkg-score PACKAGE [--project-sdk CONSTRAINT] [--github-token TOKEN]

Reads GITHUB_TOKEN from the environment when --github-token is omitted.
PUB_API_BASE / GITHUB_API_BASE env vars override the API hosts (tests).
"""

import argparse
import datetime
import json
import os
import re
import sys
import urllib.parse
import urllib.request

PUB_API = os.environ.get("PUB_API_BASE", "https://pub.dev")
GH_API = os.environ.get("GITHUB_API_BASE", "https://api.github.com")

SDK_SCORE = {"compatible": 15, "needs_override": 5, "incompatible": 0}


def compute_score(data):
    """Score a candidate package from structured data (pure, no I/O).

    data keys: package, granted_points, max_points, popularity (0..1),
    recency_days, sdk ('compatible'|'needs_override'|'incompatible'),
    dependents, open_issues, closed_issues.
    Returns {"package", "criteria", "total", "verdict"}.
    """
    max_points = data.get("max_points") or 0
    granted = data.get("granted_points") or 0
    pub_points = (granted / max_points) * 30 if max_points else 0

    popularity = (data.get("popularity") or 0) * 15

    days = data.get("recency_days") or 0
    recency = 20 if days < 90 else 12 if days < 180 else 5 if days < 365 else 0

    sdk = SDK_SCORE.get(data.get("sdk"), 0)

    dependents = data.get("dependents") or 0
    dep = 10 if dependents >= 50 else 6 if dependents >= 10 else 3 if dependents >= 1 else 0

    open_ = data.get("open_issues") or 0
    closed = data.get("closed_issues") or 0
    ratio = open_ / (open_ + closed) if (open_ + closed) else 0
    issue_ratio = 10 if ratio < 0.20 else 5 if ratio <= 0.40 else 0

    total = round(pub_points + popularity + recency + sdk + dep + issue_ratio, 1)
    total = min(total, 100.0)
    verdict = "AUTO_APPROVE" if total >= 70 else "DEVELOPER_DECISION" if total >= 50 else "AUTO_REJECT"

    return {
        "package": data.get("package", ""),
        "criteria": {
            "pub_points": round(pub_points, 2),
            "popularity": round(popularity, 2),
            "recency": recency,
            "sdk": sdk,
            "dependents": dep,
            "issue_ratio": issue_ratio,
        },
        "total": total,
        "verdict": verdict,
    }


def _fetch_json(url, token=None):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "pkg-score/1.0", "Accept": "application/vnd.github+json"},
    )
    if token:
        req.add_header("Authorization", "Bearer {}".format(token))
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _days_ago(iso):
    if not iso:
        return None
    dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (datetime.datetime.now(datetime.timezone.utc) - dt).days


def _github_repo(repo_url):
    if not repo_url or "github.com" not in repo_url:
        return None
    parts = repo_url.rstrip("/").split("/")
    return (parts[3], parts[4]) if len(parts) >= 5 else None


def _sdk_status(constraint, project_sdk):
    """Best-effort SDK compatibility. 'compatible' unless the project SDK
    constraint makes the package's constraint clearly unsatisfiable."""
    if not constraint:
        return "incompatible"
    if not project_sdk:
        return "compatible"
    return "needs_override"


def _dependents_count(package, token):
    """pub.dev has no official dependents endpoint; best-effort page scrape."""
    try:
        html = urllib.request.urlopen(
            urllib.request.Request(
                "{}/packages/{}".format(PUB_API, package),
                headers={"User-Agent": "pkg-score/1.0"},
            ),
            timeout=30,
        ).read().decode("utf-8", errors="ignore")
        match = re.search(r"(\d[\d,]*)</span>\s*</a>\s*</li>\s*<li>\s*<span[^>]*>\s*<a[^>]*>importer", html)
        if match:
            return int(match.group(1).replace(",", ""))
        match = re.search(r"(\d[\d,]*)\s+packages? that depend on", html, re.I)
        if match:
            return int(match.group(1).replace(",", ""))
    except Exception:
        pass
    return 0


def gather_data(package, project_sdk, token):
    score = _fetch_json("{}/api/packages/{}/score".format(PUB_API, package), token)
    pkg = _fetch_json("{}/api/packages/{}/".format(PUB_API, package), token)
    latest = pkg.get("latest", {})
    pubspec = latest.get("pubspec", {}) or {}
    environment = pubspec.get("environment", {}) or {}

    data = {
        "package": package,
        "granted_points": score.get("grantedPoints", 0),
        "max_points": score.get("maxPoints", 160),
        "popularity": score.get("popularityScore", 0),
        "sdk": _sdk_status(environment.get("sdk"), project_sdk),
        "dependents": _dependents_count(package, token),
    }

    repo = _github_repo(pubspec.get("repository") or pubspec.get("homepage"))
    recency_days = None
    open_issues = closed_issues = 0
    if repo:
        owner, name = repo
        try:
            commits = _fetch_json(
                "{}/repos/{}/{}/commits?per_page=1".format(GH_API, owner, name), token
            )
            if commits:
                recency_days = _days_ago(commits[0]["commit"]["committer"]["date"])
            repo_info = _fetch_json("{}/repos/{}/{}".format(GH_API, owner, name), token)
            open_q = _fetch_json(
                "{}/search/issues?q=repo:{}/{}+type:issue+state:open&per_page=1".format(GH_API, owner, name),
                token,
            )
            closed_q = _fetch_json(
                "{}/search/issues?q=repo:{}/{}+type:issue+state:closed&per_page=1".format(GH_API, owner, name),
                token,
            )
            open_issues = open_q.get("total_count", 0)
            closed_issues = closed_q.get("total_count", 0)
        except Exception:
            pass

    if recency_days is None:
        recency_days = _days_ago(latest.get("published")) or 0
        data["recency_source"] = "published"
    else:
        data["recency_source"] = "github"

    data["recency_days"] = recency_days
    data["open_issues"] = open_issues
    data["closed_issues"] = closed_issues
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description="Corrected Quality Score for a pub.dev package")
    parser.add_argument("package")
    parser.add_argument("--project-sdk", default=os.environ.get("PROJECT_SDK"))
    parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN"))
    args = parser.parse_args(argv)

    data = gather_data(args.package, args.project_sdk, args.github_token)
    report = compute_score(data)
    report["data"] = data
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()