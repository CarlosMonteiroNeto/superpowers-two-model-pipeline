"""Shared prompt preparation boundary: one recorded instruction package.

Every worker dispatch starts here. prepare() renders the complete prompt
through prompt_headers.build(), binds each submitted channel to a digest,
and persists the exact bytes plus a tamper-evident envelope before any
worker process starts. Dispatchers verify the envelope; they never
re-assemble channels silently.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import uuid

import prompt_headers


PrepareError = prompt_headers.PromptHeaderError

_HEADINGS = (
    "Role and protocol",
    "Authority",
    "Adapted role core",
    "Backend policy",
    "Domain skills",
    "Task acceptance",
    "Output contract",
)

_CHANNELS = {
    "Role and protocol": "role_protocol",
    "Authority": "authority",
    "Adapted role core": "adapted_role_core",
    "Backend policy": "backend_policy",
    "Domain skills": "domain_skills",
    "Task acceptance": "task_acceptance",
    "Output contract": "output_contract",
}

_CONTEXT_BODY = {
    "role_protocol": "role_protocol",
    "authority": "authority",
    "task_acceptance": "task_acceptance",
    "output_contract": "output_contract",
}


def _hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strip_prefix(value: str, prefix: str, what: str) -> str:
    if not isinstance(value, str) or not value.startswith(prefix):
        raise PrepareError("unexpected %s hash format" % what)
    hexpart = value[len(prefix):]
    if len(hexpart) != 64:
        raise PrepareError("unexpected %s hash length" % what)
    try:
        int(hexpart, 16)
    except ValueError:
        raise PrepareError("unexpected %s hash characters" % what) from None
    return hexpart


def _split_sections(text: str) -> dict:
    sections = {}
    current = None
    buf = []
    for line in text.split("\n"):
        if line.startswith("## ") and line[3:] in _HEADINGS:
            if current is not None:
                if buf and buf[-1] == "":
                    buf.pop()
                if current in sections:
                    raise PrepareError("duplicate prompt section: " + current)
                sections[current] = "\n".join(buf)
            current = line[3:]
            buf = []
        else:
            if current is None:
                raise PrepareError("unexpected prompt layout")
            buf.append(line)
    if current is None:
        raise PrepareError("unexpected prompt layout")
    if buf and buf[-1] == "":
        buf.pop()
    if current in sections:
        raise PrepareError("duplicate prompt section: " + current)
    sections[current] = "\n".join(buf)
    missing = [heading for heading in _HEADINGS if heading not in sections]
    if missing or len(sections) != len(_HEADINGS):
        raise PrepareError(
            "prompt sections do not match the accepted order: "
            + ",".join(sorted(missing)))
    return sections


def _check_skills_section(body: str, skills: dict):
    """Rebuild the Domain skills section from the approved inputs.

    The rendered section must be exactly what the supplied skill bundle
    resolves to — same entries, same revisions, same bytes — so the
    recorded channel provably binds the inputs, not just the output hash.
    """
    if not isinstance(skills, dict) or not isinstance(
            skills.get("skills"), list):
        raise PrepareError("resolved skills manifest is invalid")
    entries = []
    seen = {}
    for entry in skills["skills"]:
        if not isinstance(entry, dict):
            raise PrepareError("resolved skill entry is invalid")
        skill_id = entry.get("id")
        revision = entry.get("revision")
        content = entry.get("content")
        if (not isinstance(skill_id, str) or not skill_id.strip()
                or not isinstance(revision, str) or not revision
                or not isinstance(content, str)):
            raise PrepareError("resolved skill identity or content is invalid")
        previous = seen.get(skill_id)
        if previous is not None:
            if previous != (revision, content):
                raise PrepareError(
                    "conflicting revisions or content for skill " + skill_id)
            continue
        seen[skill_id] = (revision, content)
        entries.append("### %s (revision: %s)\n%s"
                       % (skill_id, revision, content))
    if "\n\n".join(entries) != body:
        raise PrepareError(
            "domain skills section does not match the approved bundle")


def record_envelope(prompt_path, role, channels, policy_sha256=None,
                    output_path=None) -> dict:
    """Record a tamper-evident envelope for an externally assembled prompt.

    Reviewer and director prompts are candidate-bound files, not
    ``prepare()`` packages; this binds their bytes plus declared channels
    (package digest, role core digest) under the same hash contract that
    dispatch verifies. Returns the envelope mapping.
    """
    data = pathlib.Path(prompt_path).read_bytes()
    prompt_hash = _hex(data)
    if not isinstance(channels, list) or not channels:
        raise PrepareError("envelope channels are required")
    for channel in channels:
        if (not isinstance(channel, dict)
                or not isinstance(channel.get("name"), str)
                or not channel["name"]
                or not _is_hex64(channel.get("sha256"))):
            raise PrepareError("envelope channel is invalid")
    if policy_sha256 is not None and not _is_hex64(policy_sha256):
        raise PrepareError("envelope policy digest is invalid")
    body = {"role": role, "prompt_sha256": prompt_hash,
            "policy_sha256": policy_sha256, "channels": channels}
    envelope_hash = _hex(json.dumps(
        body, sort_keys=True, separators=(",", ":")).encode())
    envelope = {"version": 1, "role": role, "prompt_sha256": prompt_hash,
                "prompt_bytes": len(data), "policy_sha256": policy_sha256,
                "channels": channels,
                "instruction_envelope_hash": envelope_hash}
    target = (pathlib.Path(output_path) if output_path is not None
              else pathlib.Path(str(prompt_path) + ".envelope.json"))
    _atomic_json(target, envelope)
    return dict(envelope)


def _is_hex64(value) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(char in "0123456789abcdef" for char in value))


def _atomic_bytes(path, data: bytes):
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
    tmp.write_bytes(data)
    os.replace(str(tmp), str(target))


def _atomic_json(path, value):
    _atomic_bytes(path, (json.dumps(
        value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())


def prepare(role: str, context: dict, skills: dict, policy: str,
            output_dir) -> dict:
    """Render, bind, and persist one instruction package.

    Returns prompt_path, prompt_hash (64 lowercase hex), provenance_path,
    and instruction_envelope_hash. Raises PrepareError before writing
    anything when inputs are incomplete, conflicting, or over budget.
    """
    out = pathlib.Path(output_dir)
    built = prompt_headers.build(role, context, skills, policy)
    text = built["text"]
    prompt_bytes = text.encode("utf-8")
    prompt_hash = _hex(prompt_bytes)
    if _strip_prefix(built["hash"], "sha256:", "builder hash") != prompt_hash:
        raise PrepareError("builder hash does not match rendered prompt")
    sections = _split_sections(text)
    if not isinstance(policy, str) or not policy:
        raise PrepareError("backend policy is required")
    _check_skills_section(sections["Domain skills"], skills)
    expected_bodies = {"Backend policy": policy}
    for field, context_key in _CONTEXT_BODY.items():
        value = context.get(context_key) if isinstance(context, dict) else None
        if not isinstance(value, str) or not value:
            raise PrepareError("prompt context is missing: " + context_key)
        expected_bodies[_channel_heading(field)] = value
    for heading, expected in expected_bodies.items():
        if sections[heading] != expected:
            raise PrepareError(
                "prepared channel does not match its accepted input: "
                + heading)
    channels = [{"name": _CHANNELS[heading],
                 "sha256": _hex(sections[heading].encode("utf-8"))}
                for heading in _HEADINGS]
    provenance = built["provenance"]
    core_hex = _strip_prefix(provenance.get("core_sha256", ""),
                             "sha256:", "core hash")
    envelope_body = {
        "role": role,
        "prompt_sha256": prompt_hash,
        "policy_sha256": _hex(policy.encode("utf-8")),
        "channels": channels,
    }
    envelope_hash = _hex(json.dumps(
        envelope_body, sort_keys=True, separators=(",", ":")).encode())
    envelope = {
        "version": 1,
        "role": role,
        "upstream_revision": provenance.get("upstream_revision"),
        "prompt_sha256": prompt_hash,
        "prompt_bytes": len(prompt_bytes),
        "policy_sha256": _hex(policy.encode("utf-8")),
        "core_sha256_hex": core_hex,
        "channels": channels,
        "provenance": provenance,
        "instruction_envelope_hash": envelope_hash,
    }
    prompt_path = out / "prompt.md"
    provenance_path = out / "provenance.json"
    envelope_path = out / "envelope.json"
    _atomic_bytes(prompt_path, prompt_bytes)
    _atomic_json(provenance_path, {
        "prompt_sha256": prompt_hash,
        "core_sha256_hex": core_hex,
        "builder": provenance,
    })
    _atomic_json(envelope_path, envelope)
    return {
        "prompt_path": str(prompt_path),
        "prompt_hash": prompt_hash,
        "provenance_path": str(provenance_path),
        "instruction_envelope_hash": envelope_hash,
    }


def _channel_heading(field: str) -> str:
    for heading, name in _CHANNELS.items():
        if name == field:
            return heading
    raise PrepareError("unknown channel: " + field)
