"""Atomic identity-bound worker session records."""
import hashlib
import json
import os
import pathlib


def _path(identity):
    if not isinstance(identity, dict): raise ValueError("identity required")
    root = identity.get("session_dir") or identity.get("worktree")
    if not root: raise ValueError("session directory/worktree required")
    key = hashlib.sha256(json.dumps({k:v for k,v in identity.items() if k != "session_dir"}, sort_keys=True).encode()).hexdigest()
    return pathlib.Path(root) / ".superpowers" / "sessions" / (key + ".json")


def load_session(identity):
    path = _path(identity)
    try: record = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError: return None
    if not isinstance(record, dict) or record.get("identity") != {k:v for k,v in identity.items() if k != "session_dir"}:
        raise ValueError("session identity mismatch")
    return record


def store_session(identity, record):
    if not isinstance(record, dict): raise ValueError("record must be an object")
    path = _path(identity); path.parent.mkdir(parents=True, exist_ok=True)
    value = dict(record); value["identity"] = {k:v for k,v in identity.items() if k != "session_dir"}
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    os.replace(str(temp), str(path))
