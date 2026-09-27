"""Deterministic, backend-neutral prompt assembly for worker roles."""

from __future__ import annotations

import hashlib
import json
import pathlib


class PromptHeaderError(ValueError):
    """Prompt inputs cannot be composed into a safe, complete worker prompt."""


_ROLES = {"operator", "reviewer", "director"}
_REQUIRED_CONTEXT = (
    "role_protocol", "authority", "task_acceptance", "output_contract",
)
_PROMPT_DIR = pathlib.Path(__file__).resolve().parents[1] / "prompts"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PromptHeaderError("required prompt context is missing or invalid: " + name)
    return value


def _load_sources(role: str) -> tuple[str, str, dict, dict, list[dict]]:
    core_path = _PROMPT_DIR / ("core-%s.md" % role)
    lock_path = _PROMPT_DIR / "upstream-lock.json"
    map_path = _PROMPT_DIR / "adaptation-map.json"
    try:
        core_bytes = core_path.read_bytes()
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        adaptation = json.loads(map_path.read_text(encoding="utf-8"))
        core = core_bytes.decode("utf-8")
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PromptHeaderError("prompt core provenance is unavailable") from exc

    revision = lock.get("revision")
    if (not isinstance(revision, str) or not revision
            or adaptation.get("upstream_revision") != revision):
        raise PromptHeaderError("prompt source revision conflict")
    source_hashes = {
        item.get("path"): item.get("sha256")
        for item in lock.get("sources", []) if isinstance(item, dict)
    }
    core_sources = []
    seen_paths = set()
    for entry in adaptation.get("sections", []):
        if not isinstance(entry, dict) or entry.get("role") not in (role, "shared"):
            continue
        source_path = entry.get("source_path")
        if source_path in seen_paths:
            continue
        digest = source_hashes.get(source_path)
        if not isinstance(source_path, str) or not isinstance(digest, str):
            raise PromptHeaderError("prompt source hash is missing for %s" % source_path)
        seen_paths.add(source_path)
        core_sources.append({"path": source_path, "sha256": digest})
    return core, _sha256(core_bytes), lock, adaptation, core_sources


def _skill_content(skills: dict, role: str) -> tuple[str, list[dict]]:
    if not isinstance(skills, dict) or not isinstance(skills.get("skills", []), list):
        raise PromptHeaderError("resolved skills manifest is invalid")
    manifest_role = skills.get("role")
    if manifest_role is not None and manifest_role != role:
        raise PromptHeaderError("resolved skills manifest role conflicts with prompt role")
    if skills.get("conflicts") or skills.get("ambiguities"):
        raise PromptHeaderError("selected skill instructions contain a conflict")

    by_id: dict[str, dict] = {}
    ordered: list[dict] = []
    for entry in skills.get("skills", []):
        if not isinstance(entry, dict):
            raise PromptHeaderError("resolved skill entry is invalid")
        skill_id = entry.get("id")
        revision = entry.get("revision")
        source_sha = entry.get("source_sha256", revision)
        content = entry.get("content")
        if (not isinstance(skill_id, str) or not skill_id.strip()
                or not isinstance(revision, str) or not revision
                or not isinstance(source_sha, str) or not source_sha
                or not isinstance(content, str)):
            raise PromptHeaderError("resolved skill identity or content is invalid")
        if source_sha != revision:
            raise PromptHeaderError("skill revision and source hash conflict for " + skill_id)
        previous = by_id.get(skill_id)
        if previous is not None:
            if (previous["revision"] != revision
                    or previous["source_sha256"] != source_sha
                    or previous["content"] != content):
                raise PromptHeaderError("conflicting revisions or content for skill " + skill_id)
            continue
        normalized = {
            "id": skill_id,
            "revision": revision,
            "source_sha256": source_sha,
            "content": content,
        }
        by_id[skill_id] = normalized
        ordered.append(normalized)
    rendered = "\n\n".join(
        "### %s (revision: %s)\n%s"
        % (entry["id"], entry["revision"], entry["content"])
        for entry in ordered)
    provenance = [
        {"id": entry["id"], "revision": entry["revision"],
         "source_sha256": entry["source_sha256"]}
        for entry in ordered
    ]
    return rendered, provenance


def build(role: str, context: dict, skills: dict, policy: str) -> dict:
    """Build a complete prompt in the shared accepted order and hash its bytes."""
    if role not in _ROLES:
        raise PromptHeaderError("worker role is invalid")
    if not isinstance(context, dict):
        raise PromptHeaderError("prompt context must be an object")
    values = {name: _required_text(context.get(name), name) for name in _REQUIRED_CONTEXT}
    policy_text = _required_text(policy, "backend policy")

    budget = context.get("budget_chars")
    if budget is not None and (isinstance(budget, bool) or not isinstance(budget, int) or budget < 1):
        raise PromptHeaderError("prompt character budget is invalid")

    core, core_sha, lock, _adaptation, core_sources = _load_sources(role)
    skill_text, skill_provenance = _skill_content(skills, role)
    core_text = "Source: %s@%s (%s)\n\n%s" % (
        lock["repository"], lock["tag"], lock["revision"], core)
    sections = [
        ("Role and protocol", values["role_protocol"]),
        ("Authority", values["authority"]),
        ("Adapted role core", core_text),
        ("Backend policy", policy_text),
        ("Domain skills", skill_text),
        ("Task acceptance", values["task_acceptance"]),
        ("Output contract", values["output_contract"]),
    ]
    text = "\n\n".join("## %s\n%s" % (heading, body) for heading, body in sections)
    if budget is not None and len(text) > budget:
        raise PromptHeaderError(
            "complete required prompt exceeds character budget (%d > %d)"
            % (len(text), budget))

    return {
        "text": text,
        "hash": _sha256(text.encode("utf-8")),
        "provenance": {
            "upstream_revision": lock["revision"],
            "upstream_tag": lock.get("tag"),
            "core_sha256": core_sha,
            "core_sources": core_sources,
            "skills": skill_provenance,
        },
    }
