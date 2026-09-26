"""Resolve planner-selected, revision-pinned skills from an installed bundle."""

from __future__ import annotations

import hashlib
import pathlib
import re

try:
    import skill_sources
except ImportError:  # pragma: no cover - package-style import fallback
    from . import skill_sources


class SkillManifestError(ValueError):
    """A selected skill cannot be resolved without changing its meaning."""


_ROLES = {"operator", "reviewer", "director"}
_SKILL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _validate_selection(selection: dict) -> tuple[str, list[dict]]:
    if not isinstance(selection, dict):
        raise SkillManifestError("selection must be an object")
    role = selection.get("role")
    if role not in _ROLES:
        raise SkillManifestError("selection role is invalid")
    selected = selection.get("skills")
    if not isinstance(selected, list):
        raise SkillManifestError("selection skills must be an array")

    seen_revisions: dict[str, str] = {}
    for item in selected:
        if not isinstance(item, dict):
            raise SkillManifestError("each selected skill must be an object")
        skill_id = item.get("id")
        revision = item.get("revision")
        roles = item.get("roles")
        sections = item.get("sections")
        if not isinstance(skill_id, str) or not _SKILL_ID.fullmatch(skill_id):
            raise SkillManifestError("selected skill id is invalid")
        if not isinstance(revision, str) or not revision:
            raise SkillManifestError("selected skill revision is required for " + skill_id)
        if not isinstance(item.get("required"), bool):
            raise SkillManifestError("required must be a boolean for " + skill_id)
        if (not isinstance(roles, list) or not roles
                or any(value not in _ROLES for value in roles)):
            raise SkillManifestError("applicable roles are invalid for " + skill_id)
        if (not isinstance(sections, list)
                or any(not isinstance(value, str) or not value.strip()
                       for value in sections)):
            raise SkillManifestError("requested sections are invalid for " + skill_id)
        topics = item.get("topics", [])
        if (not isinstance(topics, list)
                or any(not isinstance(value, str) or not value.strip()
                       for value in topics)):
            raise SkillManifestError("discovery topics are invalid for " + skill_id)
        previous = seen_revisions.get(skill_id)
        if previous is not None and previous != revision:
            raise SkillManifestError("conflicting revisions selected for " + skill_id)
        seen_revisions[skill_id] = revision
    return role, selected


def _section_content(text: str, requested: str, skill_id: str) -> str:
    lines = text.splitlines(keepends=True)
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = _HEADING.match(line.rstrip("\r\n"))
        if match:
            headings.append((index, len(match.group(1)), match.group(2).strip()))

    matches = [position for position, (_, _, title) in enumerate(headings)
               if title == requested]
    if not matches:
        raise SkillManifestError(
            "requested section %r is missing from %s" % (requested, skill_id))
    if len(matches) != 1:
        raise SkillManifestError(
            "requested section %r is ambiguous in %s" % (requested, skill_id))

    position = matches[0]
    line_index, level, _ = headings[position]
    end = len(lines)
    for next_index, next_level, _ in headings[position + 1:]:
        if next_level <= level:
            end = next_index
            break
    return "".join(lines[line_index + 1:end])


def _front_matter(text: str) -> dict:
    """Read the small metadata subset needed by the discovery registry."""
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    try:
        end = next(index for index, line in enumerate(lines[1:], 1)
                   if line.strip() == "---")
    except StopIteration:
        return {}

    values: dict[str, object] = {}
    current_list: str | None = None
    for line in lines[1:end]:
        list_item = re.match(r"^\s+-\s+(.+?)\s*$", line)
        if list_item and current_list:
            values.setdefault(current_list, [])
            if isinstance(values[current_list], list):
                values[current_list].append(_unquote(list_item.group(1)))
            continue
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*?)\s*$", line)
        if not match:
            current_list = None
            continue
        key, raw = match.groups()
        current_list = key if not raw else None
        if not raw:
            values[key] = []
        elif raw.startswith("[") and raw.endswith("]"):
            values[key] = [
                _unquote(value.strip()) for value in raw[1:-1].split(",")
                if value.strip()
            ]
        else:
            values[key] = _unquote(raw)
    return values


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _installed_inventory(skills_root: pathlib.Path, selected: list[dict]) -> list[dict]:
    selected_topics = {item["id"]: item.get("topics", []) for item in selected}
    inventory = []
    if not skills_root.is_dir():
        return inventory
    for path in sorted(skills_root.glob("*/SKILL.md"), key=lambda item: item.as_posix().casefold()):
        try:
            text = path.read_bytes().decode("utf-8-sig")
        except (OSError, UnicodeError):
            continue
        metadata = _front_matter(text)
        skill_id = path.parent.name
        name = metadata.get("name")
        description = metadata.get("description")
        topics = metadata.get("topics", [])
        if not isinstance(topics, list):
            topics = []
        topics = list(dict.fromkeys(
            value for value in topics + selected_topics.get(skill_id, [])
            if isinstance(value, str) and value.strip()))
        inventory.append({
            "id": skill_id,
            "name": name if isinstance(name, str) else skill_id,
            "description": description if isinstance(description, str) else "",
            "topics": topics,
        })
    return inventory


def _discover(selection: dict, skills_root: pathlib.Path,
              selected: list[dict]) -> dict | None:
    request = selection.get("discovery")
    if request is None:
        return None
    if not isinstance(request, dict):
        raise SkillManifestError("discovery request must be an object")
    query = request.get("query")
    registry = request.get("registry")
    if not isinstance(query, dict) or not isinstance(registry, str) or not registry.strip():
        raise SkillManifestError("discovery requires a query and registry path")
    try:
        return skill_sources.discover(
            query, _installed_inventory(skills_root, selected), registry)
    except Exception as exc:
        if isinstance(exc, SkillManifestError):
            raise
        raise SkillManifestError("skill discovery failed: %s" % exc) from exc


def resolve(selection: dict, bundle: str) -> dict:
    """Resolve selected headings from installed SKILL.md files only.

    External registry results are returned as advisory discovery metadata and
    are never materialized as skill content.
    """
    role, selected = _validate_selection(selection)
    root = pathlib.Path(bundle).expanduser().resolve()
    skills_root = (root / "skills").resolve()
    resolved = []
    omissions = []
    for item in selected:
        skill_id = item["id"]
        if role not in item["roles"]:
            omissions.append({"id": skill_id, "reason": "not_applicable_to_role"})
            continue

        path = skills_root / skill_id / "SKILL.md"
        try:
            resolved_path = path.resolve(strict=True)
            resolved_path.relative_to(skills_root)
            raw = resolved_path.read_bytes()
        except (OSError, ValueError):
            if item["required"]:
                raise SkillManifestError("required skill is not installed: " + skill_id)
            omissions.append({"id": skill_id, "reason": "optional_skill_not_installed"})
            continue

        revision = _sha256(raw)
        if revision != item["revision"]:
            raise SkillManifestError(
                "installed skill revision mismatch for %s: expected %s, got %s"
                % (skill_id, item["revision"], revision))
        try:
            source_text = raw.decode("utf-8-sig")
        except UnicodeError as exc:
            raise SkillManifestError("installed skill is not UTF-8: " + skill_id) from exc

        selected_sections = []
        for heading in item["sections"]:
            selected_sections.append({
                "heading": heading,
                "content": _section_content(source_text, heading, skill_id),
            })
        combined = "\n\n".join(
            ("## %s\n%s" % (part["heading"], part["content"])).rstrip()
            for part in selected_sections)
        resolved.append({
            "id": skill_id,
            "revision": revision,
            "source_sha256": revision,
            "roles": list(item["roles"]),
            "sections": selected_sections,
            "content": combined,
        })

    discovery = _discover(selection, skills_root, selected)
    return {
        "schema_version": 1,
        "role": role,
        "skills": resolved,
        "omissions": omissions,
        "discovery": discovery,
    }
