"""Installed-first discovery and durable refresh for reusable skill sources.

GitHub results are query-scoped candidates. Star count ranks discovery results;
it never approves a source or a skill for installation.
"""

import argparse
import base64
import copy
import datetime as dt
import json
import os
import pathlib
import re
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen


SCHEMA_VERSION = 1
CACHE_TTL = dt.timedelta(days=30)
MAX_RESULTS = 100
GITHUB_API = "https://api.github.com"
SEED_PATH = pathlib.Path(__file__).resolve().parent.parent / "skills" / "sources.seed.json"
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
GITHUB_LINK_RE = re.compile(r"https?://github\.com/[^\s)\]>\"']+", re.IGNORECASE)


class SkillSourceError(ValueError):
    """Invalid registry or discovery request."""


class SourceFetchError(RuntimeError):
    """A GitHub request failed; the message deliberately excludes its URL."""

    def __init__(self, message, status_code=None, retry_after=None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


def _now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_time(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _fresh(timestamp, now):
    stamp = _parse_time(timestamp)
    current = _parse_time(now)
    if stamp is None or current is None:
        return False
    age = current - stamp
    return dt.timedelta(0) <= age < CACHE_TTL


def _empty_registry():
    return {
        "schema_version": SCHEMA_VERSION,
        "last_refreshed_at": None,
        "last_attempted_at": None,
        "status": "stale",
        "sources": [],
        "queries": [],
    }


def _validate_registry(registry):
    if not isinstance(registry, dict) or registry.get("schema_version") != SCHEMA_VERSION:
        raise SkillSourceError("skill source registry must use schema_version 1")
    if not isinstance(registry.get("sources"), list):
        raise SkillSourceError("skill source registry sources must be an array")
    if not isinstance(registry.get("queries"), list):
        raise SkillSourceError("skill source registry queries must be an array")
    if registry.get("status") not in ("fresh", "stale", "incomplete"):
        raise SkillSourceError("skill source registry status is invalid")
    return registry


def _load_registry(path):
    path = pathlib.Path(path)
    if not path.exists():
        return _empty_registry()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillSourceError("cannot read skill source registry: %s" % exc)
    return _validate_registry(value)


def _atomic_json(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".skill-sources-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _github_get_json(url):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "superpowers-skill-source-registry",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        reset = exc.headers.get("X-RateLimit-Reset") if exc.headers else None
        if retry_after:
            detail = "GitHub rate limit reached; retry after %s seconds" % retry_after
        elif reset and exc.code in (403, 429):
            detail = "GitHub rate limit reached; reset at %s" % reset
        elif exc.code in (403, 429):
            detail = "GitHub rate limit reached (HTTP %d)" % exc.code
        else:
            detail = "GitHub request failed (HTTP %d)" % exc.code
        raise SourceFetchError(detail, exc.code, retry_after or reset)
    except (URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceFetchError("GitHub is unavailable: %s" % type(exc).__name__)


def _canonical_repository(value):
    if not isinstance(value, str) or not REPOSITORY_RE.fullmatch(value.strip()):
        return None
    return value.strip()


def _source_key(source):
    repository = _canonical_repository(source.get("repository"))
    if repository:
        return "repo:" + repository.casefold()
    url = source.get("source_url")
    return "url:" + url.casefold() if isinstance(url, str) else None


def _seed_sources():
    try:
        data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillSourceError("cannot read source seed: %s" % exc)
    sources = data.get("sources") if isinstance(data, dict) else None
    if not isinstance(sources, list):
        raise SkillSourceError("source seed must contain a sources array")
    return copy.deepcopy(sources)


def _base_source(candidate):
    if not isinstance(candidate, dict):
        raise SkillSourceError("each skill source must be an object")
    repository = _canonical_repository(candidate.get("repository"))
    source_url = candidate.get("source_url") or candidate.get("url")
    category = candidate.get("category")
    if not isinstance(source_url, str) or not source_url.startswith("https://"):
        raise SkillSourceError("skill source requires an HTTPS source_url")
    if repository is None and category != "documentation":
        raise SkillSourceError("GitHub skill source requires an owner/repository identity")
    if not isinstance(category, str) or not category.strip():
        raise SkillSourceError("skill source category is required")
    review_status = candidate.get("review_status", "candidate")
    if review_status not in ("candidate", "unreviewed", "reviewed", "rejected"):
        raise SkillSourceError("skill source review_status is invalid")
    result = copy.deepcopy(candidate)
    result.update({
        "repository": repository,
        "source_url": source_url,
        "category": category,
        "revision": candidate.get("revision"),
        "last_checked_at": candidate.get("last_checked_at"),
        "review_status": review_status,
        "description": candidate.get("description"),
        "stars": candidate.get("stars"),
        "topics": list(candidate.get("topics") or []),
        "license": copy.deepcopy(candidate.get("license")),
        "skills": copy.deepcopy(candidate.get("skills") or []),
        "refresh_status": candidate.get("refresh_status", "candidate"),
    })
    return result


def _dedupe_sources(sources):
    ordered = []
    indexes = {}
    for raw in sources:
        candidate = _base_source(raw)
        key = _source_key(candidate)
        if key is None:
            ordered.append(candidate)
            continue
        if key not in indexes:
            indexes[key] = len(ordered)
            ordered.append(candidate)
        else:
            current = ordered[indexes[key]]
            # Preserve skill paths discovered from multiple catalog links.
            known = {str(item.get("path", "")) for item in current["skills"]}
            for skill in candidate["skills"]:
                path = str(skill.get("path", ""))
                if path and path not in known:
                    current["skills"].append(skill)
                    known.add(path)
            if current["review_status"] == "candidate" and candidate["review_status"] == "unreviewed":
                current["review_status"] = "unreviewed"
    return ordered


def _merge_sources(existing, incoming):
    values = _dedupe_sources(existing)
    index = {_source_key(item): i for i, item in enumerate(values) if _source_key(item)}
    for candidate in _dedupe_sources(incoming):
        key = _source_key(candidate)
        if key not in index:
            index[key] = len(values)
            values.append(candidate)
            continue
        old = values[index[key]]
        discovered_candidate = candidate.get("category") == "linked-candidate"
        if discovered_candidate:
            # A catalog link is partial evidence. It must not downgrade a
            # source already registered with richer metadata or decisions.
            candidate["category"] = old.get("category", candidate["category"])
            candidate["skills"] = _merge_skill_entries(
                candidate.get("skills", []),
                old.get("skills", []),
                preserve_missing=True,
                previous_source_license=old.get("license"),
            )
            for field, value in old.items():
                if field not in candidate:
                    candidate[field] = copy.deepcopy(value)
            if old.get("refresh_status"):
                candidate["refresh_status"] = old["refresh_status"]
        candidate["revision"] = candidate.get("revision") or old.get("revision")
        candidate["last_checked_at"] = candidate.get("last_checked_at") or old.get("last_checked_at")
        for field in ("description", "stars", "topics", "license", "skills", "refresh_status"):
            if candidate.get(field) in (None, [], "") and old.get(field) not in (None, [], ""):
                candidate[field] = copy.deepcopy(old[field])
        # A refresh may add evidence, but it never upgrades review/trust state.
        candidate["review_status"] = old.get("review_status", candidate["review_status"])
        values[index[key]] = candidate
    return values


def _remote_error(exc):
    if isinstance(exc, SourceFetchError):
        return str(exc)
    if isinstance(exc, HTTPError):
        if exc.code in (403, 429):
            retry = exc.headers.get("Retry-After") if exc.headers else None
            return ("GitHub rate limit reached; retry after %s seconds" % retry
                    if retry else "GitHub rate limit reached (HTTP %d)" % exc.code)
        return "GitHub request failed (HTTP %d)" % exc.code
    return "GitHub is unavailable: %s" % type(exc).__name__


def _normal_license(value):
    if not isinstance(value, dict):
        return None
    spdx = value.get("spdx_id")
    name = value.get("name")
    if not isinstance(spdx, str) or not spdx.strip() or spdx.upper() == "NOASSERTION":
        return None
    return {"spdx_id": spdx, "name": name if isinstance(name, str) else None}


def _skill_entries(tree, license_info):
    entries = []
    for item in tree.get("tree", []) if isinstance(tree, dict) else []:
        path = item.get("path") if isinstance(item, dict) else None
        if not isinstance(path, str) or pathlib.PurePosixPath(path).name.casefold() != "skill.md":
            continue
        parent = pathlib.PurePosixPath(path).parent.name
        entries.append({
            "name": parent or path,
            "path": path,
            "topics": [],
            "compatibility": [],
            "license": copy.deepcopy(license_info),
            "review_status": "unreviewed",
        })
    return sorted(entries, key=lambda item: item["path"].casefold())


def _merge_skill_entries(refreshed, previous, preserve_missing=False,
                         previous_source_license=None):
    previous_by_path = {
        item["path"]: item
        for item in previous
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    merged = []
    seen = set()
    refresh_owned_fields = {"name", "path", "license"}
    for item in refreshed:
        entry = copy.deepcopy(item)
        path = entry.get("path")
        key = path if isinstance(path, str) else None
        old = previous_by_path.get(key) if key is not None else None
        if old is not None:
            for field, value in old.items():
                if field not in refresh_owned_fields:
                    entry[field] = copy.deepcopy(value)
            if "license" in old:
                old_license = _normal_license(old.get("license"))
                inherited_license = _normal_license(previous_source_license)
                if old.get("license") is None or old_license != inherited_license:
                    entry["license"] = copy.deepcopy(old["license"])
            seen.add(key)
        merged.append(entry)
    if preserve_missing:
        for key, item in previous_by_path.items():
            if key not in seen:
                merged.append(copy.deepcopy(item))
    return sorted(merged, key=lambda item: str(item.get("path", "")).casefold())


def _catalog_targets(readme, catalog_repository):
    targets = []
    catalog_key = catalog_repository.casefold()
    seen = set()
    for raw_url in GITHUB_LINK_RE.findall(readme or ""):
        clean_url = raw_url.rstrip(".,;:")
        parsed = urlparse(clean_url)
        if parsed.netloc.casefold() not in ("github.com", "www.github.com"):
            continue
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2:
            continue
        repository = _canonical_repository(parts[0] + "/" + parts[1])
        if not repository or repository.casefold() == catalog_key:
            continue
        key = repository.casefold()
        if key not in seen:
            seen.add(key)
            targets.append({
                "repository": repository,
                "source_url": "https://github.com/" + repository,
                "category": "linked-candidate",
                "revision": None,
                "last_checked_at": None,
                "review_status": "unreviewed",
                "description": None,
                "stars": None,
                "topics": [],
                "license": None,
                "skills": [],
                "refresh_status": "unreviewed",
                "discovered_from": catalog_repository,
            })
        target = targets[-1] if targets and targets[-1]["repository"].casefold() == key else next(
            item for item in targets if item["repository"].casefold() == key
        )
        if len(parts) >= 4 and parts[2].casefold() in ("tree", "blob"):
            skill_path = "/".join(parts[4:])
            if skill_path:
                if skill_path.casefold().endswith("/skill.md"):
                    skill_name = pathlib.PurePosixPath(skill_path).parent.name
                else:
                    skill_name = pathlib.PurePosixPath(skill_path).name
                if not any(item.get("path", "") == skill_path
                           for item in target["skills"]):
                    target["skills"].append({
                        "name": skill_name or skill_path,
                        "path": skill_path,
                        "topics": [],
                        "compatibility": [],
                        "license": None,
                        "review_status": "unreviewed",
                    })
    return targets


def _refresh_source(source, now):
    repository = source.get("repository")
    if not repository:
        return source, []
    safe_repository = _canonical_repository(repository)
    if safe_repository is None:
        raise SkillSourceError("invalid GitHub repository identity")
    encoded_repo = "/".join(quote(part, safe="") for part in safe_repository.split("/"))
    details = _github_get_json(GITHUB_API + "/repos/" + encoded_repo)
    if not isinstance(details, dict):
        raise SourceFetchError("GitHub returned invalid repository metadata")
    full_name = details.get("full_name")
    if isinstance(full_name, str):
        safe_repository = _canonical_repository(full_name) or safe_repository
    branch = details.get("default_branch")
    if not isinstance(branch, str) or not branch:
        raise SourceFetchError("GitHub repository has no default branch")
    commit = _github_get_json(GITHUB_API + "/repos/" + encoded_repo + "/commits/" + quote(branch, safe=""))
    revision = commit.get("sha") if isinstance(commit, dict) else None
    if not isinstance(revision, str) or not revision:
        raise SourceFetchError("GitHub did not return a repository revision")
    license_info = _normal_license(details.get("license"))
    topics = details.get("topics") if isinstance(details.get("topics"), list) else []
    updated = dict(source)
    updated.update({
        "repository": safe_repository,
        "source_url": details.get("html_url") or ("https://github.com/" + safe_repository),
        "revision": revision,
        "last_checked_at": now,
        "description": details.get("description") if isinstance(details.get("description"), str) else None,
        "stars": details.get("stargazers_count") if isinstance(details.get("stargazers_count"), int) else None,
        "topics": sorted({topic.casefold() for topic in topics if isinstance(topic, str)}),
        "license": license_info,
        "refresh_status": "fresh",
    })
    linked = []
    category = source.get("category")
    if category in ("publisher", "catalog"):
        tree_url = GITHUB_API + "/repos/" + encoded_repo + "/git/trees/" + quote(revision, safe="") + "?recursive=1"
        tree = _github_get_json(tree_url)
        tree_incomplete = (
            not isinstance(tree, dict)
            or not isinstance(tree.get("tree"), list)
            or bool(tree.get("truncated"))
        )
        updated["skills"] = _merge_skill_entries(
            _skill_entries(tree, license_info),
            source.get("skills", []),
            preserve_missing=tree_incomplete,
            previous_source_license=source.get("license"),
        )
        updated["skills_incomplete"] = tree_incomplete
        if tree_incomplete:
            updated["refresh_status"] = "incomplete"
    if category == "catalog":
        readme = _github_get_json(GITHUB_API + "/repos/" + encoded_repo + "/readme")
        if not isinstance(readme, dict) or readme.get("encoding") != "base64":
            raise SourceFetchError("GitHub catalog README was unavailable or not base64 encoded")
        try:
            content = base64.b64decode(readme.get("content", ""), validate=False).decode("utf-8", errors="replace")
        except (ValueError, TypeError) as exc:
            raise SourceFetchError("GitHub catalog README could not be decoded") from exc
        linked = _catalog_targets(content, safe_repository)
    return updated, linked


def refresh(registry: str, now: str, sources: list) -> dict:
    """Refresh selected GitHub sources and atomically preserve the registry.

    Network failures are recorded as incomplete and never erase last usable
    metadata or cached query results. This function only reads metadata; it
    does not clone a repository or execute skill code.
    """
    if _parse_time(now) is None:
        raise SkillSourceError("now must be an ISO-8601 timestamp")
    if not isinstance(sources, list):
        raise SkillSourceError("sources must be a list")
    path = pathlib.Path(registry)
    current = _load_registry(path)
    source_inputs = _dedupe_sources(sources)
    merged = _merge_sources(current["sources"], source_inputs)
    preexisting_refreshable = {
        _source_key(item)
        for item in current["sources"]
        if isinstance(item, dict)
        and item.get("repository")
        and item.get("category") != "documentation"
        and _source_key(item)
    }
    selected_refreshable = {
        _source_key(item)
        for item in source_inputs
        if item.get("repository") and item.get("category") != "documentation"
        and _source_key(item)
    }
    unselected_sources = preexisting_refreshable - selected_refreshable
    source_index = {_source_key(item): i for i, item in enumerate(merged) if _source_key(item)}
    linked_sources = []
    failed = []
    incomplete_sources = []
    for source in source_inputs:
        if source.get("category") == "documentation" or not source.get("repository"):
            continue
        key = _source_key(source)
        try:
            refresh_source = merged[source_index[key]] if key in source_index else source
            refreshed, linked = _refresh_source(refresh_source, now)
        except (SourceFetchError, HTTPError, URLError, TimeoutError, OSError,
                ValueError, UnicodeError) as exc:
            failed.append({"repository": source.get("repository"), "error": _remote_error(exc)})
            if key in source_index:
                existing = merged[source_index[key]]
                existing["refresh_status"] = "incomplete"
                existing["last_error"] = _remote_error(exc)
            continue
        if key in source_index:
            existing = merged[source_index[key]]
            # Refresh metadata without changing the review decision.
            refreshed["review_status"] = existing.get("review_status", refreshed["review_status"])
            merged[source_index[key]] = refreshed
        else:
            source_index[key] = len(merged)
            merged.append(refreshed)
        if refreshed.get("refresh_status") == "incomplete":
            incomplete_sources.append({
                "repository": refreshed.get("repository"),
                "error": "GitHub repository tree was truncated; cached skill inventory was preserved",
            })
        linked_sources.extend(linked)
    merged = _merge_sources(merged, linked_sources)
    result = copy.deepcopy(current)
    result["last_attempted_at"] = now
    result["sources"] = merged
    if failed or incomplete_sources:
        result["status"] = "incomplete"
        result["last_refresh_errors"] = failed + incomplete_sources
        result.pop("unrefreshed_sources", None)
    elif unselected_sources:
        result["status"] = "stale"
        result["unrefreshed_sources"] = sorted(unselected_sources)
        result.pop("last_refresh_errors", None)
    else:
        result["status"] = "fresh"
        result["last_refreshed_at"] = now
        result.pop("unrefreshed_sources", None)
        result.pop("last_refresh_errors", None)
    _validate_registry(result)
    _atomic_json(path, result)
    return result


def _normal_topics(value):
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = []
    output = []
    seen = set()
    for item in values:
        if not isinstance(item, str):
            continue
        topic = " ".join(item.casefold().split())
        if topic and topic not in seen:
            output.append(topic)
            seen.add(topic)
    return output


def _required_topics(query):
    topics = _normal_topics(query.get("topics"))
    if not topics:
        topics = _normal_topics(query.get("keywords"))
    return topics or ["agent"]


def _normalize_query(query):
    if not isinstance(query, dict):
        raise SkillSourceError("query must be an object")
    result = copy.deepcopy(query)
    for field in ("topics", "keywords", "compatibility"):
        if field in result:
            result[field] = _normal_topics(result[field])
    return result


def _query_terms(query, topics=None):
    terms = []
    selected_topics = _normal_topics(topics) if topics is not None else _required_topics(query)
    for values in (selected_topics, _normal_topics(query.get("keywords"))):
        for value in values:
            tokens = re.findall(r"[\w.+#-]+", value, flags=re.UNICODE)
            for token in tokens:
                if token not in terms:
                    terms.append(token)
    return terms or ["agent"]


def _search_query(query, topics=None):
    terms = _query_terms(query, topics)
    return " ".join(terms + ["skill", "in:name,description,readme"])


def _topic_tokens(value):
    return re.findall(r"[\w.+#-]+", str(value or "").casefold(), flags=re.UNICODE)


def _contains_topic(text, topic):
    wanted = _topic_tokens(topic)
    available = _topic_tokens(text)
    if not wanted:
        return False
    return any(available[index:index + len(wanted)] == wanted
               for index in range(len(available) - len(wanted) + 1))


def _topic_match(record, topics):
    record_topics = set(_normal_topics(record.get("topics")))
    text_fields = ("repository", "description", "name", "path")
    matched = [topic for topic in topics
               if topic in record_topics or any(
                   _contains_topic(record.get(field), topic) for field in text_fields)]
    return matched


def _skill_checks(skill, source, query, candidate_topics):
    topics = _required_topics(query)
    skill_topics = _normal_topics(skill.get("topics"))
    relevant = bool(set(topics).intersection(skill_topics or candidate_topics))
    wanted = set(_normal_topics(query.get("compatibility")))
    available = set(_normal_topics(skill.get("compatibility")))
    compatible = not wanted or wanted.issubset(available)
    url = source.get("source_url") or source.get("url")
    parsed = urlparse(url if isinstance(url, str) else "")
    source_valid = parsed.scheme == "https" and parsed.netloc.casefold() == "github.com"
    license_value = skill.get("license") if "license" in skill else source.get("license")
    license_info = _normal_license(license_value)
    return {
        "relevance": relevant,
        "compatibility": compatible,
        "source": source_valid,
        "license": license_info is not None,
    }


def _decorate_candidate(candidate, query, matched_topics):
    item = copy.deepcopy(candidate)
    item.setdefault("source_url", item.get("url"))
    item["matched_topics"] = matched_topics
    item.setdefault("review_status", "unreviewed")
    item["install_requires_approval"] = True
    for skill in item.get("skills", []):
        skill["checks"] = _skill_checks(skill, item, query, matched_topics)
        approved_checks = all(skill["checks"].values())
        if approved_checks and skill.get("review_status") == "reviewed":
            skill["recommendation_status"] = "requires_user_approval"
        else:
            skill["recommendation_status"] = "review_required"
    return item


def _candidate_from_github(item, now):
    if not isinstance(item, dict):
        return None
    repository = _canonical_repository(item.get("full_name"))
    html_url = item.get("html_url")
    if repository is None or not isinstance(html_url, str) or not html_url.startswith("https://github.com/"):
        return None
    topics = item.get("topics") if isinstance(item.get("topics"), list) else []
    return {
        "repository": repository,
        "source_url": "https://github.com/" + repository,
        "category": "github-search",
        "revision": None,
        "last_checked_at": now,
        "review_status": "unreviewed",
        "description": item.get("description") if isinstance(item.get("description"), str) else None,
        "stars": item.get("stargazers_count") if isinstance(item.get("stargazers_count"), int) else 0,
        "topics": sorted({topic.casefold() for topic in topics if isinstance(topic, str)}),
        "license": _normal_license(item.get("license")),
        "skills": [],
    }


def _query_limits(query):
    per_page = query.get("per_page", 100) if isinstance(query, dict) else 100
    if isinstance(per_page, bool) or not isinstance(per_page, int):
        per_page = 100
    per_page = min(100, max(1, per_page))
    limit = query.get("limit", MAX_RESULTS) if isinstance(query, dict) else MAX_RESULTS
    if isinstance(limit, bool) or not isinstance(limit, int):
        limit = MAX_RESULTS
    limit = min(MAX_RESULTS, max(1, limit))
    return limit, per_page


def _query_record_limits(record):
    query = record.get("query") if isinstance(record.get("query"), dict) else {}
    query = dict(query)
    if "limit" in record:
        query["limit"] = record["limit"]
    if "per_page" in record:
        query["per_page"] = record["per_page"]
    return _query_limits(query)


def _search_github(query, search_text, now):
    limit, per_page = _query_limits(query)
    topics = _required_topics(query)
    repositories = {}
    page = 1
    incomplete = False
    total_count = None
    while len(repositories) < limit and page <= 10:
        url = GITHUB_API + "/search/repositories?" + urlencode({
            "q": search_text,
            "sort": "stars",
            "order": "desc",
            "per_page": per_page,
            "page": page,
        })
        response = _github_get_json(url)
        if not isinstance(response, dict) or not isinstance(response.get("items"), list):
            raise SourceFetchError("GitHub returned invalid repository search results")
        total_count = response.get("total_count") if isinstance(response.get("total_count"), int) else None
        incomplete = incomplete or bool(response.get("incomplete_results"))
        for raw in response["items"]:
            candidate = _candidate_from_github(raw, now)
            if candidate is None:
                continue
            matched = _topic_match(candidate, topics)
            if topics and not matched:
                continue
            key = candidate["repository"].casefold()
            candidate["matched_topics"] = matched
            old = repositories.get(key)
            if old is None or candidate["stars"] > old["stars"]:
                repositories[key] = candidate
        if not response["items"] or len(response["items"]) < per_page:
            break
        if total_count is not None and page * per_page >= min(total_count, 1000):
            break
        page += 1
    ordered = sorted(repositories.values(), key=lambda item: (-item["stars"], item["repository"].casefold()))[:limit]
    scope = (
        "Query-scoped GitHub repository search for %r; sorted by stars descending; "
        "top 100 relevant results at most (requested limit %d); not a global or exhaustive ranking."
        % (search_text, limit)
    )
    return ordered, scope, incomplete


def _matching_query_record(registry, search_text, query):
    expected_limits = _query_limits(query)
    for item in registry.get("queries", []):
        if (isinstance(item, dict) and item.get("search_query") == search_text
                and _query_record_limits(item) == expected_limits):
            return item
    return None


def _record_query(registry, record):
    for index, item in enumerate(registry["queries"]):
        if (isinstance(item, dict)
                and item.get("search_query") == record["search_query"]
                and _query_record_limits(item) == _query_record_limits(record)):
            registry["queries"][index] = record
            return
    registry["queries"].append(record)


def _relevant_cached_candidates(record, query):
    topics = _required_topics(query)
    candidates = []
    for source in record.get("repositories", []):
        if not isinstance(source, dict):
            continue
        matched = _topic_match(source, topics)
        if topics and not matched:
            continue
        candidates.append(_decorate_candidate(source, query, matched))
    candidates.sort(key=lambda item: (-int(item.get("stars") or 0), item.get("repository", "").casefold()))
    return candidates[:_query_limits(query)[0]]


def _registry_candidates(registry, query, topics):
    candidates = []
    covered = set()
    for source in registry.get("sources", []):
        if not isinstance(source, dict) or source.get("category") == "documentation":
            continue
        if source.get("review_status") == "rejected":
            continue
        source_matches = _topic_match(source, topics)
        source_topics = _normal_topics(source.get("topics"))
        matching_skills = []
        for raw_skill in source.get("skills", []):
            if not isinstance(raw_skill, dict):
                continue
            skill_matches = _topic_match(raw_skill, topics)
            if skill_matches:
                relevant_topics = skill_matches
            elif not _normal_topics(raw_skill.get("topics")) and source_matches:
                relevant_topics = source_matches
            else:
                continue
            skill = copy.deepcopy(raw_skill)
            skill["checks"] = _skill_checks(skill, source, query, relevant_topics)
            checks_pass = all(skill["checks"].values())
            if skill.get("review_status") == "rejected":
                continue
            if checks_pass and skill.get("review_status") == "reviewed":
                skill["recommendation_status"] = "requires_user_approval"
            else:
                skill["recommendation_status"] = "review_required"
            matching_skills.append(skill)
            if checks_pass:
                covered.update(relevant_topics)
        if not source_matches and not matching_skills:
            continue
        candidate = copy.deepcopy(source)
        candidate["matched_topics"] = sorted(set(source_matches).union(
            topic for skill in matching_skills for topic in _topic_match(skill, topics)
        ))
        candidate["install_requires_approval"] = True
        if source.get("skills"):
            candidate["skills"] = matching_skills
        else:
            candidate["skills"] = []
        candidates.append(candidate)
    candidates.sort(key=lambda item: (-int(item.get("stars") or 0),
                                     item.get("repository") or ""))
    return candidates[:MAX_RESULTS], covered


def _combine_candidates(*groups):
    combined = {}
    for group in groups:
        for item in group:
            repository = item.get("repository")
            if not isinstance(repository, str):
                continue
            key = repository.casefold()
            if key not in combined:
                combined[key] = item
                continue
            old = combined[key]
            if len(item.get("skills", [])) > len(old.get("skills", [])):
                old["skills"] = item["skills"]
            if old.get("category") == "github-search" and item.get("category") != "github-search":
                item["matched_topics"] = sorted(set(item.get("matched_topics", []))
                                                 .union(old.get("matched_topics", [])))
                combined[key] = item
    values = list(combined.values())
    values.sort(key=lambda item: (-int(item.get("stars") or 0),
                                 item.get("repository", "").casefold()))
    return values[:MAX_RESULTS]


def _refresh_if_due(path, registry_value, now):
    registered_sources = registry_value.get("sources") or []
    sources_current = all(
        not isinstance(source, dict)
        or not source.get("repository")
        or source.get("category") == "documentation"
        or (_fresh(source.get("last_checked_at"), now)
            and source.get("refresh_status", "fresh") == "fresh")
        for source in registered_sources
    )
    if (registry_value.get("status") == "fresh"
            and _fresh(registry_value.get("last_refreshed_at"), now)
            and sources_current):
        return registry_value
    sources = registered_sources or _seed_sources()
    return refresh(str(path), now, sources)


def discover(query: dict, installed: list, registry: str) -> dict:
    """Search installed skills first, then cached and external sources for gaps."""
    query = _normalize_query(query)
    if not isinstance(installed, list):
        raise SkillSourceError("installed skills must be a list")
    topics = _required_topics(query)
    installed_coverage = set()
    installed_matches = []
    for skill in installed:
        if not isinstance(skill, dict):
            continue
        skill_topics = set(_normal_topics(skill.get("topics")))
        matched = {topic for topic in topics if topic in skill_topics or any(
            _contains_topic(skill.get(field), topic) for field in ("name", "description"))}
        installed_coverage.update(matched)
        if matched:
            installed_matches.append(copy.deepcopy(skill))
    missing_topics = [topic for topic in topics if topic not in installed_coverage]
    if not missing_topics:
        return {
            "query": query,
            "installed_matches": installed_matches,
            "missing_topics": [],
            "candidates": [],
            "cache_status": "installed",
            "scope": "Installed skills cover the requested topics; no external search was needed.",
            "external_installation_requires_approval": True,
            "installation_performed": False,
        }

    path = pathlib.Path(registry)
    now = _now_iso()
    current = _load_registry(path)
    current = _refresh_if_due(path, current, now)
    registered_candidates, registry_coverage = _registry_candidates(current, query, topics)
    uncovered_topics = [topic for topic in missing_topics if topic not in registry_coverage]
    if not uncovered_topics:
        return {
            "query": query,
            "installed_matches": installed_matches,
            "missing_topics": missing_topics,
            "candidates": registered_candidates,
            "cache_status": current.get("status", "fresh"),
            "scope": "Registry query found relevant cached skill metadata; no external search was needed.",
            "external_installation_requires_approval": True,
            "installation_performed": False,
        }

    search_text = _search_query(query, uncovered_topics)
    cached = _matching_query_record(current, search_text, query)
    if cached and cached.get("status") == "fresh" and _fresh(cached.get("collected_at"), now):
        return {
            "query": query,
            "installed_matches": installed_matches,
            "missing_topics": missing_topics,
            "candidates": _combine_candidates(
                registered_candidates, _relevant_cached_candidates(cached, query)),
            "cache_status": current.get("status", "fresh"),
            "scope": cached.get("scope", "Query-scoped GitHub skill discovery."),
            "external_installation_requires_approval": True,
            "installation_performed": False,
        }

    try:
        candidates, scope, incomplete = _search_github(query, search_text, now)
        record = {
            "query": query,
            "search_query": search_text,
            "limit": _query_limits(query)[0],
            "per_page": _query_limits(query)[1],
            "collected_at": now,
            "scope": scope,
            "status": "incomplete" if incomplete else "fresh",
            "repositories": candidates,
        }
        if incomplete:
            current["status"] = "incomplete"
    except (SourceFetchError, HTTPError, URLError, TimeoutError, OSError,
            ValueError, UnicodeError) as exc:
        reason = _remote_error(exc)
        if cached:
            record = copy.deepcopy(cached)
            record["status"] = "incomplete"
            record["last_error"] = reason
            scope = record.get("scope", "Query-scoped GitHub skill discovery; cached results may be stale.")
        else:
            scope = "Query-scoped GitHub skill discovery was incomplete; no global or exhaustive ranking is available."
            record = {
                "query": query,
                "search_query": search_text,
                "collected_at": None,
                "scope": scope,
                "status": "incomplete",
                "last_error": reason,
                "repositories": [],
            }
        current["status"] = "incomplete"
    _record_query(current, record)
    current["last_attempted_at"] = now
    _validate_registry(current)
    _atomic_json(path, current)
    return {
        "query": query,
        "installed_matches": installed_matches,
        "missing_topics": missing_topics,
        "candidates": _combine_candidates(
            registered_candidates, _relevant_cached_candidates(record, query)),
        "cache_status": record["status"] if current.get("status") == "fresh" else "incomplete",
        "scope": scope,
        "external_installation_requires_approval": True,
        "installation_performed": False,
    }


def _json_argument(value, default):
    if value is None:
        return default
    path = pathlib.Path(value)
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        pass
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise SkillSourceError("expected JSON text or a JSON file path") from exc


def refresh_cli(argv=None):
    parser = argparse.ArgumentParser(description="Refresh cached skill source metadata")
    parser.add_argument("registry", help="path to the persisted skill source registry")
    parser.add_argument("--sources", help="JSON file containing a sources array; defaults to sources.seed.json")
    parser.add_argument("--now", help="explicit ISO-8601 clock for deterministic runs")
    args = parser.parse_args(argv)
    try:
        if args.sources:
            source_data = json.loads(pathlib.Path(args.sources).read_text(encoding="utf-8"))
            sources = source_data.get("sources") if isinstance(source_data, dict) else source_data
        else:
            sources = _seed_sources()
        result = refresh(args.registry, args.now or _now_iso(), sources)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if result["status"] == "fresh" else 1
    except (OSError, json.JSONDecodeError, SkillSourceError) as exc:
        print("SKILL-SOURCE-REFRESH: %s" % exc, file=sys.stderr)
        return 2


def search_cli(argv=None):
    parser = argparse.ArgumentParser(description="Discover installed and cached skill sources")
    parser.add_argument("registry", help="path to the persisted skill source registry")
    parser.add_argument("--query", required=True, help="query JSON text or a JSON file path")
    parser.add_argument("--installed", help="installed-skill JSON text or a JSON file path")
    args = parser.parse_args(argv)
    try:
        query = _json_argument(args.query, None)
        installed = _json_argument(args.installed, [])
        result = discover(query, installed, args.registry)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if result["cache_status"] in ("fresh", "installed") else 1
    except (OSError, json.JSONDecodeError, SkillSourceError) as exc:
        print("SKILL-SOURCE-SEARCH: %s" % exc, file=sys.stderr)
        return 2
