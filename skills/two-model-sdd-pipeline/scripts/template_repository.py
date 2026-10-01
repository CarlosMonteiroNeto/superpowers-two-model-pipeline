"""Path-safe, local template update previews for immutable version bindings."""

import argparse
import json
import sys
from pathlib import PurePosixPath
from pathlib import Path


def _safe_path(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and all(part not in ("", ".", "..") for part in path.parts)


def _files(value):
    if not isinstance(value, dict) or any(not _safe_path(path) or not isinstance(content, str) for path, content in value.items()):
        raise ValueError("files must map safe relative paths to text")
    return dict(value)


def preview_update(binding, candidate):
    """Compare a new immutable candidate with a binding without modifying it."""
    if not isinstance(binding, dict) or not isinstance(candidate, dict):
        return {"status": "SETUP_ERROR", "error": "binding and candidate must be objects"}
    for obj, label, fields in ((binding, "binding", ("asset_id", "version", "source_identity")),
                               (candidate, "candidate", ("version", "source_identity"))):
        if any(not isinstance(obj.get(key), str) or not obj[key] for key in fields):
            return {"status": "SETUP_ERROR", "error": "{} identity is incomplete".format(label)}
    try:
        base = _files(binding.get("files", {}))
        proposed = _files(candidate.get("files", {}))
        local = _files(binding.get("local_changes", {}))
    except ValueError as error:
        return {"status": "SETUP_ERROR", "error": str(error)}
    if binding["version"] == candidate["version"] and binding["source_identity"] == candidate["source_identity"]:
        return {"status": "current", "binding": dict(binding), "added": [], "changed": [], "removed": [], "conflicts": []}
    changed = sorted(path for path in base.keys() & proposed.keys() if base[path] != proposed[path])
    added = sorted(proposed.keys() - base.keys())
    removed = sorted(base.keys() - proposed.keys())
    conflicts = sorted(path for path, content in local.items()
                       if path not in base or base.get(path) != content and proposed.get(path) != base.get(path))
    return {
        "status": "conflict" if conflicts else "update_available",
        "binding": dict(binding),
        "candidate": {"version": candidate["version"], "source_identity": candidate["source_identity"]},
        "added": added,
        "changed": changed,
        "removed": removed,
        "conflicts": conflicts,
        "preserved_local": dict(local),
        "preview_files": {**proposed, **local},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Preview an immutable template binding update")
    parser.add_argument("binding_json")
    parser.add_argument("candidate_json")
    args = parser.parse_args(argv)
    try:
        binding = json.loads(Path(args.binding_json).read_text(encoding="utf-8"))
        candidate = json.loads(Path(args.candidate_json).read_text(encoding="utf-8"))
        result = preview_update(binding, candidate)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["status"] != "SETUP_ERROR" else 1
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("template-repository: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
