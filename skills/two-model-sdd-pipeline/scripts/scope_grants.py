"""Atomically reserve task write paths for supervisor-issued scope grants."""
import json
import os
import tempfile


def _normal(path):
    if not isinstance(path, str) or not path.strip() or "\\" in path:
        raise ValueError("invalid canonical relative path")
    path = path.strip()
    if path.startswith("/") or any(p in ("", ".", "..") for p in path.split("/")) or (len(path) > 1 and path[1] == ":"):
        raise ValueError("path escapes ownership root")
    return path


def reserve(request: dict, ownership: dict) -> dict:
    if not isinstance(request, dict) or not isinstance(ownership, dict):
        raise ValueError("request and ownership must be objects")
    if not ownership.get("run_id") or ownership.get("family_id") is None:
        raise ValueError("ownership requires run_id and family_id")
    path = _normal(request.get("path"))
    kind = request.get("kind")
    repo_root = ownership.get("repo_root")
    if repo_root:
        root = os.path.realpath(repo_root)
        path = _resolve_path(root, path)
    allowed_roots = [_resolve_path(root, _normal(x)).rstrip("/") if repo_root else _normal(x).rstrip("/")
                     for x in ownership.get("allowed_roots", [])]
    path_key = os.path.normcase(path)
    protected = {os.path.normcase(_resolve_path(root, _normal(x)) if repo_root else _normal(x))
                 for x in ownership.get("protected_paths", [])}
    if any(path_key == p or path_key.startswith(p + os.sep) for p in protected):
        return {"decision": "block", "reason": "protected path", "path": path}
    in_root = any(path == root or path.startswith(root + "/") for root in allowed_roots)
    if not in_root:
        return {"decision": "block", "reason": "outside approved task roots", "path": path}
    conflicts = {os.path.normcase(_resolve_path(root, _normal(x)) if repo_root else _normal(x))
                 for x in ownership.get("conflicting_paths", [])}
    conflicts.update(os.path.normcase(_resolve_path(root, _normal(x)) if repo_root else _normal(x))
                     for x in ownership.get("active_task_paths", []))
    conflicts.update(os.path.normcase(_resolve_path(root, _normal(x)) if repo_root else _normal(x))
                     for x in ownership.get("future_task_paths", []))
    if path_key in conflicts:
        return {"decision": "block", "reason": "path conflicts with active or future task scope", "path": path}
    approved = {os.path.normcase(_resolve_path(root, _normal(x)) if repo_root else _normal(x))
                for x in ownership.get("director_approved_existing", [])}
    if kind == "existing_file" and path_key not in approved:
        return {"decision": "block", "reason": "existing file requires director approval", "path": path}
    if kind not in ("new_file", "existing_file"):
        return {"decision": "block", "reason": "unsupported path kind", "path": path}
    if repo_root:
        absolute = os.path.join(root, *path.split("/"))
        exists = os.path.exists(absolute)
        if kind == "new_file" and exists:
            return {"decision": "block", "reason": "new-file request already exists", "path": path}
        if kind == "existing_file" and not exists:
            return {"decision": "block", "reason": "existing-file request is missing", "path": path}
    registry = ownership.get("registry_path")
    if registry:
        _reserve_registry(registry, path, ownership)
    return {"decision": "grant", "path": path, "run_id": ownership.get("run_id"), "family_id": ownership.get("family_id")}


def _resolve_path(root, relative):
    """Resolve aliases before comparing scope declarations or protected paths."""
    absolute = os.path.realpath(os.path.join(root, *relative.split("/")))
    try:
        if os.path.commonpath((root, absolute)) != root:
            raise ValueError("path escapes ownership root")
    except ValueError as exc:
        raise ValueError("path escapes ownership root") from exc
    return os.path.relpath(absolute, root).replace(os.sep, "/")


def _reserve_registry(path, relative, owner):
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lock = path + ".lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError("scope registry is locked") from exc
    os.close(fd)
    try:
        try:
            with open(path, encoding="utf-8") as f:
                records = json.load(f)
        except FileNotFoundError:
            records = {}
        if not isinstance(records, dict):
            raise ValueError("corrupt scope registry")
        key = os.path.normcase(relative)
        existing = records.get(key)
        identity = (owner.get("run_id"), str(owner.get("family_id")))
        if existing and (existing.get("run_id"), str(existing.get("family_id"))) != identity:
            raise RuntimeError("path is already owned by another task family: {}".format(relative))
        records[key] = {"path": relative, "run_id": identity[0], "family_id": identity[1]}
        fd, temp = tempfile.mkstemp(prefix="scope-", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(records, f, sort_keys=True, indent=2)
                f.flush(); os.fsync(f.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp): os.unlink(temp)
    finally:
        try: os.unlink(lock)
        except FileNotFoundError: pass
