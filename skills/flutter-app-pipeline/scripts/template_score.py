#!/usr/bin/env python3
"""Deterministic GitHub-based template quality score (pure scorer).

Mirrors pkg_score.py's structure: a pure compute_score(data) function plus
a template-score CLI wrapper. Stars is the heaviest-weight criterion (30 of
100) and the primary search sort key.

Usage:
  template-score OWNER/REPO [--github-token TOKEN]

Reads GITHUB_TOKEN from the environment when --github-token is omitted.
GITHUB_API_BASE env var overrides the API host (tests).
"""

import argparse
import datetime
import json
import os
import sys
import urllib.parse
import urllib.request

GH_API = os.environ.get("GITHUB_API_BASE", "https://api.github.com")


def compute_score(data):
    """Score a candidate template from structured data (pure, no I/O).

    data keys: template (owner/repo string), stars (int), recency_days (int),
    flutter_ready ('current'|'dated'|'none'), open_issues (int),
    closed_issues (int), stars_per_year (float), license ('mit'|'apache'|
    'bsd'|'other'|'none'), readme ('full'|'partial'|'none').

    Returns {"template", "criteria": {stars, recency, flutter_ready,
    issue_ratio, sustained_interest, license, readme}, "total", "verdict"}.
    """
    # Stars: >=1000=30, 300-999=24, 100-299=18, 30-99=12, 10-29=6, <10=0
    stars = data.get("stars") or 0
    if stars >= 1000:
        stars_score = 30
    elif stars >= 300:
        stars_score = 24
    elif stars >= 100:
        stars_score = 18
    elif stars >= 30:
        stars_score = 12
    elif stars >= 10:
        stars_score = 6
    else:
        stars_score = 0

    # Recency (days since last commit): <90=20, 90-179=12, 180-364=5, >=365=0
    days = data.get("recency_days") or 0
    if days < 90:
        recency_score = 20
    elif days < 180:
        recency_score = 12
    elif days < 365:
        recency_score = 5
    else:
        recency_score = 0

    # Flutter readiness: 'current'=20, 'dated'=10, 'none'=0
    flutter_ready = data.get("flutter_ready", "none")
    if flutter_ready == "current":
        flutter_score = 20
    elif flutter_ready == "dated":
        flutter_score = 10
    else:
        flutter_score = 0

    # Issue ratio (open/(open+closed)): <0.20=10, 0.20-0.40=5, >0.40=0
    open_ = data.get("open_issues") or 0
    closed = data.get("closed_issues") or 0
    total_issues = open_ + closed
    if total_issues:
        ratio = open_ / total_issues
    else:
        ratio = 0
    if ratio < 0.20:
        issue_ratio_score = 10
    elif ratio <= 0.40:
        issue_ratio_score = 5
    else:
        issue_ratio_score = 0

    # Sustained interest (stars_per_year): >=10=10, 1-9.9=6, <1=2
    spy = data.get("stars_per_year") or 0
    if spy >= 10:
        sustained_score = 10
    elif spy >= 1:
        sustained_score = 6
    else:
        sustained_score = 2

    # License: 'mit'|'apache'|'bsd'=5, 'other'=3, 'none'=0
    lic = data.get("license", "none")
    if lic in ("mit", "apache", "bsd"):
        license_score = 5
    elif lic == "other":
        license_score = 3
    else:
        license_score = 0

    # Readme: 'full'=5, 'partial'=2, 'none'=0
    readme = data.get("readme", "none")
    if readme == "full":
        readme_score = 5
    elif readme == "partial":
        readme_score = 2
    else:
        readme_score = 0

    total = round(
        stars_score + recency_score + flutter_score + issue_ratio_score
        + sustained_score + license_score + readme_score,
        1,
    )
    total = min(total, 100.0)

    if total >= 70:
        verdict = "AUTO_APPROVE"
    elif total >= 50:
        verdict = "DEVELOPER_DECISION"
    else:
        verdict = "AUTO_REJECT"

    return {
        "template": data.get("template", ""),
        "criteria": {
            "stars": stars_score,
            "recency": recency_score,
            "flutter_ready": flutter_score,
            "issue_ratio": issue_ratio_score,
            "sustained_interest": sustained_score,
            "license": license_score,
            "readme": readme_score,
        },
        "total": total,
        "verdict": verdict,
    }


def _fetch_json(url, token=None):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "template-score/1.0", "Accept": "application/vnd.github+json"},
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


def gather_data(owner, repo, token):
    """Fetch GitHub data for a template repository."""
    data = {"template": "{}/{}".format(owner, repo)}

    try:
        # Get repo info for stars and license
        repo_info = _fetch_json("{}/repos/{}/{}".format(GH_API, owner, repo), token)
        data["stars"] = repo_info.get("stargazers_count", 0)

        # Get license info
        license_info = repo_info.get("license") or {}
        spdx = (license_info.get("spdx_id") or "").lower()
        if "mit" in spdx:
            data["license"] = "mit"
        elif "apache" in spdx:
            data["license"] = "apache"
        elif "bsd" in spdx:
            data["license"] = "bsd"
        elif spdx:
            data["license"] = "other"
        else:
            data["license"] = "none"

        # Get last commit for recency
        commits = _fetch_json(
            "{}/repos/{}/{}/commits?per_page=1".format(GH_API, owner, repo), token
        )
        if commits:
            data["recency_days"] = _days_ago(commits[0]["commit"]["committer"]["date"])
        else:
            data["recency_days"] = 0

        # Get issues for ratio
        open_q = _fetch_json(
            "{}/search/issues?q=repo:{}/{}+type:issue+state:open&per_page=1".format(
                GH_API, owner, repo
            ),
            token,
        )
        closed_q = _fetch_json(
            "{}/search/issues?q=repo:{}/{}+type:issue+state:closed&per_page=1".format(
                GH_API, owner, repo
            ),
            token,
        )
        data["open_issues"] = open_q.get("total_count", 0)
        data["closed_issues"] = closed_q.get("total_count", 0)

        # Stars per year: estimate from stars and repo creation date
        created = repo_info.get("created_at")
        if created:
            age_years = max((_days_ago(created) or 1) / 365.0, 0.1)
            data["stars_per_year"] = round(data["stars"] / age_years, 1)
        else:
            data["stars_per_year"] = 0.0

        # Flutter readiness: best-effort from pubspec analysis
        # For now default to 'none'; Task 3 will refine this
        data["flutter_ready"] = "none"

        # Readme: best-effort from README contents API
        try:
            readme_resp = _fetch_json(
                "{}/repos/{}/{}/readme".format(GH_API, owner, repo), token
            )
            if readme_resp and readme_resp.get("content"):
                import base64
                content = base64.b64decode(readme_resp["content"]).decode("utf-8", errors="ignore")
                lower = content.lower()
                has_setup = any(kw in lower for kw in ["install", "getting started", "setup", "usage", "how to use"])
                has_structure = any(kw in lower for kw in ["structure", "architecture", "project structure", "directory"])
                if has_setup and has_structure:
                    data["readme"] = "full"
                elif has_setup or has_structure:
                    data["readme"] = "partial"
                else:
                    data["readme"] = "none"
            else:
                data["readme"] = "none"
        except Exception:
            data["readme"] = "none"

    except Exception:
        # On any failure, return minimal data with defaults
        data.setdefault("stars", 0)
        data.setdefault("recency_days", 0)
        data.setdefault("flutter_ready", "none")
        data.setdefault("open_issues", 0)
        data.setdefault("closed_issues", 0)
        data.setdefault("stars_per_year", 0.0)
        data.setdefault("license", "none")
        data.setdefault("readme", "none")

    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description="Deterministic GitHub-based template quality score")
    parser.add_argument("template", help="owner/repo template identifier")
    parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN"))
    args = parser.parse_args(argv)

    parts = args.template.split("/")
    if len(parts) != 2:
        print("Error: template must be owner/repo format", file=sys.stderr)
        sys.exit(1)
    owner, repo = parts

    data = gather_data(owner, repo, args.github_token)
    report = compute_score(data)
    report["data"] = data
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
