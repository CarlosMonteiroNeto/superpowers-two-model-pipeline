"""Build deterministic, self-contained worker context packages.

All mandatory material is included verbatim. Missing files, invalid anchors,
and context budgets smaller than the complete package are explicit errors;
the builder never truncates acceptance or evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any


class ContextPackageError(ValueError):
    """A required context reference cannot be resolved or represented."""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _inside(root: Path, relative: str, label: str) -> Path:
    rel = PurePosixPath(relative.replace("\\", "/"))
    if rel.is_absolute() or not rel.parts or any(part in ("", ".", "..") for part in rel.parts):
        raise ContextPackageError("%s must be a canonical relative path: %s" % (label, relative))
    root = root.resolve()
    target = root.joinpath(*rel.parts).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ContextPackageError("%s escapes its approved root: %s" % (label, relative)) from exc
    return target


def _anchor_slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9_ -]", "", value)
    return re.sub(r"[\s-]+", "-", value).strip("-")


def _extract_spec(text: str, anchor: str | None, source: str) -> str:
    if not anchor:
        return text.rstrip()
    requested = _anchor_slug(anchor)
    lines = text.splitlines()
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if match:
            headings.append((index, len(match.group(1)), _anchor_slug(match.group(2))))
    for position, (start, level, slug) in enumerate(headings):
        if slug == requested:
            end = len(lines)
            for next_start, next_level, _ in headings[position + 1:]:
                if next_level <= level:
                    end = next_start
                    break
            return "\n".join(lines[start:end]).rstrip()
    raise ContextPackageError("missing spec anchor #%s in %s" % (anchor, source))


def _read_reference(root: Path, reference: str) -> tuple[str, str, str]:
    path_ref, marker, anchor = reference.partition("#")
    if not (path_ref.lower().endswith((".md", ".markdown", ".txt")) or "/" in path_ref or "\\" in path_ref):
        # Historic section-only citations such as "§2.1" carry no file path;
        # preserve them as citations without pretending they were resolved.
        return reference, reference, ""
    target = _inside(root, path_ref, "spec reference")
    try:
        raw = target.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ContextPackageError("cannot read spec reference %s: %s" % (path_ref, exc)) from exc
    excerpt = _extract_spec(text, anchor if marker else None, path_ref)
    return reference, excerpt, _digest(raw)


def _read_skill(bundle_root: Path, skill_id: str) -> tuple[str, str, str]:
    rel = PurePosixPath(skill_id.replace("\\", "/"))
    if rel.is_absolute() or any(part in ("", ".", "..") for part in rel.parts):
        raise ContextPackageError("invalid pinned skill id: %s" % skill_id)
    candidates = [
        bundle_root.joinpath("skills", *rel.parts, "SKILL.md"),
        bundle_root.joinpath("skills", *rel.parts).with_suffix(".md"),
    ]
    bundle_root = bundle_root.resolve()
    for target in candidates:
        try:
            resolved = target.resolve()
            resolved.relative_to(bundle_root)
        except (OSError, ValueError):
            continue
        if resolved.is_file():
            try:
                raw = resolved.read_bytes()
                return skill_id, raw.decode("utf-8"), _digest(raw)
            except (OSError, UnicodeError) as exc:
                raise ContextPackageError("cannot read pinned skill %s: %s" % (skill_id, exc)) from exc
    raise ContextPackageError("pinned pipeline skill is missing from bundle: %s" % skill_id)


def _find_task(plan: dict[str, Any], task_id: Any) -> dict[str, Any]:
    matches = [task for task in plan.get("tasks", [])
               if isinstance(task, dict) and str(task.get("id")) == str(task_id)]
    if len(matches) != 1:
        raise ContextPackageError("task %s is missing or ambiguous in plan" % task_id)
    return matches[0]


def build_context(role: str, request: dict, plan: dict, bundle_root: str) -> dict:
    """Return ``{"prompt": str, "source_manifest": dict}`` for a worker.

    The core task/spec/verification sections are identical for Codex and
    OpenCode. Backend-specific policy text is an explicit, separate section.
    """
    if not isinstance(request, dict) or not isinstance(plan, dict):
        raise ContextPackageError("request and plan must be JSON objects")
    if role not in ("operator", "reviewer", "director", "closing"):
        raise ContextPackageError("unsupported worker role: %s" % role)
    backend = request.get("backend")
    if backend not in ("codex", "opencode"):
        raise ContextPackageError("request.backend must be codex or opencode")
    task_id = request.get("task_id")
    task = _find_task(plan, task_id)
    repository_root = Path(
        request.get("worktree") or request.get("repository_root") or request.get("project_root") or "."
    ).resolve()
    bundle = Path(bundle_root).resolve()

    spec_refs = task.get("spec_refs") or []
    if not isinstance(spec_refs, list):
        raise ContextPackageError("task.spec_refs must be a list")
    specs = []
    sources = []
    for ref in spec_refs:
        if not isinstance(ref, str) or not ref:
            raise ContextPackageError("spec_refs must contain nonempty strings")
        label, excerpt, digest = _read_reference(repository_root, ref)
        specs.append({"reference": label, "excerpt": excerpt})
        if digest:
            sources.append({"kind": "spec", "reference": label, "sha256": digest})

    skill_ids = task.get("skills") or request.get("skills") or []
    if not isinstance(skill_ids, list) or not all(isinstance(item, str) for item in skill_ids):
        raise ContextPackageError("pinned skills must be a list of skill IDs")
    skills = []
    for skill_id in skill_ids:
        resolved_id, content, digest = _read_skill(bundle, skill_id)
        skills.append({"id": resolved_id, "content": content})
        sources.append({"kind": "pipeline_skill", "id": resolved_id, "sha256": digest})

    project_instructions = []
    agents_file = repository_root / "AGENTS.md"
    if agents_file.is_file():
        raw = agents_file.read_bytes()
        project_instructions.append({"path": "AGENTS.md", "content": raw.decode("utf-8")})
        sources.append({"kind": "project_instructions", "path": "AGENTS.md", "sha256": _digest(raw)})
    for item in request.get("managed_rules", []) or []:
        if not isinstance(item, str):
            raise ContextPackageError("managed_rules entries must be strings")
        project_instructions.append({"path": "managed", "content": item})

    family_id = request.get("task_family_id") or task.get("task_family_id")
    attempt_id = request.get("attempt_id")
    if not family_id or not attempt_id:
        raise ContextPackageError("task_family_id and attempt_id are required context identity")

    identity = {
        "backend": backend,
        "role": role,
        "task_id": task_id,
        "task_family_id": family_id,
        "attempt_id": attempt_id,
        "repository_root": str(repository_root),
        "worktree": str(Path(request.get("worktree") or repository_root).resolve()),
        "allowed_roots": request.get("allowed_roots", [str(repository_root)]),
        "evidence_paths": request.get("evidence_paths", {}),
        "bundle": {
            "root": str(bundle),
            "revision": request.get("bundle_revision"),
            "hash": request.get("bundle_hash"),
        },
    }

    mandatory = {
        "global_constraints": plan.get("global_constraints", []),
        "task": task,
        "interfaces": task.get("interfaces", plan.get("interfaces", {})),
        "verification": task.get("verification", {}),
        "spec_excerpts": specs,
        "identity": identity,
        "toolchain_descriptor": request.get("toolchain_descriptor", {}),
        "role_instructions": request.get("role_instructions", ""),
        "backend_policy": request.get("backend_policy", ""),
        "project_instructions": project_instructions,
        "pinned_pipeline_skills": skills,
    }
    plan_bytes = _json(plan).encode("utf-8")
    sources.insert(0, {"kind": "approved_plan", "sha256": _digest(plan_bytes)})
    manifest = {
        "version": 1,
        "backend": backend,
        "role": role,
        "task_id": task_id,
        "task_family_id": family_id,
        "attempt_id": attempt_id,
        "bundle_root": str(bundle),
        "bundle_revision": request.get("bundle_revision"),
        "bundle_hash": request.get("bundle_hash"),
        "sources": sources,
        "evidence_paths": request.get("evidence_paths", {}),
    }
    prompt_sections = [
        "# Worker Context Package",
        "\n## Invocation identity\n\n" + _json(identity),
        "\n## Global constraints\n\n" + _json(mandatory["global_constraints"]),
        "\n## Complete approved task\n\n" + _json(task),
        "\n## Interfaces\n\n" + _json(mandatory["interfaces"]),
        "\n## Verification contract\n\n" + _json(mandatory["verification"]),
        "\n## Cited specification excerpts\n\n" + _json(specs),
        "\n## Toolchain descriptor\n\n" + _json(mandatory["toolchain_descriptor"]),
        "\n## Project and managed instructions\n\n" + _json(project_instructions),
        "\n## Pinned pipeline skills\n\n" + _json(skills),
        "\n## Role instructions\n\n" + str(mandatory["role_instructions"]),
        "\n## Backend policy wrapper\n\n" + str(mandatory["backend_policy"]),
    ]
    prompt = "\n".join(prompt_sections).rstrip() + "\n"
    budget = request.get("context_budget_chars")
    if budget is not None:
        try:
            budget = int(budget)
        except (TypeError, ValueError) as exc:
            raise ContextPackageError("context_budget_chars must be an integer") from exc
        measured = len(prompt) + len(_json(manifest))
        if budget < 0 or measured > budget:
            raise ContextPackageError(
                "mandatory context is %s characters, exceeding the %s-character budget" %
                (measured, budget)
            )
    return {"prompt": prompt, "source_manifest": manifest}
