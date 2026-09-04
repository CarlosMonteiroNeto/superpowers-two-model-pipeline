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


def _detect_flutter_ready(owner, repo, token):
    """Detect Flutter readiness from pubspec.yaml SDK constraint.

    Returns 'current' if the SDK lower bound is >= 2.12 (null-safe),
    'dated' if the SDK is present but < 2.12, 'none' otherwise.
    """
    import base64
    import re
    try:
        pubspec_resp = _fetch_json(
            "{}/repos/{}/{}/contents/pubspec.yaml".format(GH_API, owner, repo), token
        )
        if not pubspec_resp or not pubspec_resp.get("content"):
            return "none"
        content = base64.b64decode(pubspec_resp["content"]).decode("utf-8", errors="ignore")
        match = re.search(r'sdk:\s*["\']?([>=<.0-9]+)', content)
        if not match:
            return "none"
        version_str = match.group(1)
        parts = re.findall(r"(\d+)", version_str)
        if len(parts) >= 2:
            major, minor = int(parts[0]), int(parts[1])
            if major > 2 or (major == 2 and minor >= 12):
                return "current"
            return "dated"
        return "none"
    except Exception:
        return "none"


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

        # Flutter readiness: detect from pubspec.yaml SDK constraint
        data["flutter_ready"] = _detect_flutter_ready(owner, repo, token)

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


def collect_candidates(specific_query, generic_query, token=None):
    """Search GitHub for templates and score them.

    Search order: specific category first (stars descending), then generic
    as fallback. Returns a dict with 'specific' and 'generic' lists of
    scored candidates, plus 'presentation' (the combined presentation list).

    The stop rule halts scoring as soon as the 3rd AUTO_APPROVE is found —
    no further candidates from the specific search are scored. The generic
    search is only issued when the specific category yields zero AUTO_APPROVE.
    """
    result = {"specific": [], "generic": [], "presentation": []}

    def _fetch_search_items(query):
        """Fetch search results without scoring. Returns list of items."""
        if not query:
            return []
        encoded = urllib.parse.quote(query)
        try:
            search_resp = _fetch_json(
                "{}/search/repositories?q={}&sort=stars&order=desc".format(GH_API, encoded),
                token,
            )
        except Exception:
            return []
        return search_resp.get("items", [])

    def _score_item(item):
        """Score a single search result item. Returns scored dict or None."""
        full_name = item.get("full_name", "")
        parts = full_name.split("/")
        if len(parts) != 2:
            return None
        owner, repo = parts
        try:
            data = gather_data(owner, repo, token)
            score = compute_score(data)
            score["data"] = data
            return score
        except Exception:
            return None

    # Fetch specific search results (one API call)
    specific_items = _fetch_search_items(specific_query)

    # Score candidates in search order, collecting until 3rd AUTO_APPROVE
    specific_candidates = []
    auto_count = 0
    for item in specific_items:
        scored = _score_item(item)
        if scored is None:
            continue
        specific_candidates.append(scored)
        if scored["verdict"] == "AUTO_APPROVE":
            auto_count += 1
            if auto_count >= 3:
                break
    result["specific"] = specific_candidates

    if auto_count >= 1:
        # Specific yielded at least one AUTO_APPROVE — present what was collected
        result["presentation"] = specific_candidates
    else:
        # No AUTO_APPROVE in specific: collect DEVELOPER_DECISION (50-69)
        dev_decision = [c for c in specific_candidates if c["verdict"] == "DEVELOPER_DECISION"]

        # Search generic category for AUTO_APPROVE (only when specific has none)
        generic_items = _fetch_search_items(generic_query)
        generic_candidates = []
        for item in generic_items:
            scored = _score_item(item)
            if scored is None:
                continue
            generic_candidates.append(scored)
        result["generic"] = generic_candidates
        generic_auto = [c for c in generic_candidates if c["verdict"] == "AUTO_APPROVE"]

        # Presentation: both groups
        result["presentation"] = dev_decision + generic_auto

    return result


def main(argv=None):
    args_list = argv if argv is not None else sys.argv[1:]

    # Detect mode from first argument
    if args_list and args_list[0] == "collect":
        parser = argparse.ArgumentParser(description="Search and collect template candidates")
        parser.add_argument("command")
        parser.add_argument("--specific", required=True, help="Specific-category search query")
        parser.add_argument("--generic", required=True, help="Generic-category fallback search query")
        parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN"))
        args = parser.parse_args(args_list)
        result = collect_candidates(
            args.specific, args.generic, args.github_token
        )
        print(json.dumps(result, indent=2))
    elif args_list:
        # Legacy single-score mode: OWNER/REPO
        parser = argparse.ArgumentParser(description="Deterministic GitHub-based template quality score")
        parser.add_argument("template", help="owner/repo template identifier")
        parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN"))
        args = parser.parse_args(args_list)
        parts = args.template.split("/")
        if len(parts) != 2:
            print("Error: template must be owner/repo format", file=sys.stderr)
            sys.exit(1)
        owner, repo = parts
        data = gather_data(owner, repo, args.github_token)
        report = compute_score(data)
        report["data"] = data
        print(json.dumps(report, indent=2))
    else:
        parser = argparse.ArgumentParser(description="Deterministic GitHub-based template quality score")
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
