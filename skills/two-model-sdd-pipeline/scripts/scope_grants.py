"""Atomically reserve task write paths for supervisor-issued scope grants."""
import json
import os
import tempfile
import hashlib
import hmac


_BUILTIN_PROTECTED_PREFIXES = (".git/", ".superpowers/")
_BUILTIN_PROTECTED_BASENAMES = frozenset({
    "package.json", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock",
    "pnpm-lock.yaml", "requirements.txt", "requirements-dev.txt",
    "Cargo.toml", "Cargo.lock", "go.mod", "go.sum", "pubspec.yaml",
    "pubspec.lock", "Gemfile", "Gemfile.lock", "poetry.lock",
    "composer.json", "composer.lock", "Pipfile", "Pipfile.lock", "pom.xml",
    "build.gradle", "build.gradle.kts",
})


def is_protected(relative_path: str) -> bool:
    """True when a canonical repo-relative path is always off-limits.

    Covers pipeline control state and dependency manifests/lockfiles: Git
    metadata, control state, manifests, and ``*.lock``. Plans, ledgers, and
    permission configuration travel through explicit protected_paths; the
    builtins here are the categories no task may ever claim.
    """
    if not isinstance(relative_path, str) or not relative_path:
        return True
    lowered = relative_path.casefold()
    for prefix in _BUILTIN_PROTECTED_PREFIXES:
        if lowered == prefix.rstrip("/") or lowered.startswith(prefix):
            return True
    base = lowered.rsplit("/", 1)[-1]
    return base in _BUILTIN_PROTECTED_BASENAMES or base.endswith(".lock")


_SIGNED_FIELDS = ("path", "run_id", "family_id", "task_id", "attempt_id",
                  "grant_id", "issuer", "contracts")


def _signing_key(value):
    if not isinstance(value, str):
        raise ValueError("supervisor signing key is required")
    try:
        key = bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError("supervisor signing key must be hex") from exc
    if len(key) < 32:
        raise ValueError("supervisor signing key must be at least 32 bytes")
    return key


def sign_issued(record, key):
    """Authenticate the exact fields the correction router will consume."""
    if record.get("issuer") != "supervisor" or not all(record.get(k) for k in _SIGNED_FIELDS):
        raise ValueError("incomplete supervisor grant")
    if not isinstance(record["contracts"], list) or not all(isinstance(x, str) and x for x in record["contracts"]):
        raise ValueError("invalid supervisor contracts")
    payload = {name: record[name] for name in _SIGNED_FIELDS}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hmac.new(_signing_key(key), raw, hashlib.sha256).hexdigest()


def verify_issued(record, key):
    if not isinstance(record, dict) or not key:
        return False
    try:
        expected = sign_issued(record, key)
    except (ValueError, KeyError, TypeError):
        return False
    return hmac.compare_digest(expected, str(record.get("signature", "")))


def _in_granted_areas(path: str, ownership: dict) -> bool:
    """True when a canonical path sits inside the owner's directory scope.

    ``ownership["scope"]`` carries normalized ``roots`` (``"."`` is the
    repository itself). Comparison is case-aware per platform and treats
    ``src/a`` as covering ``src/a/x.py`` but never ``src/ab``.
    """
    scope = ownership.get("scope")
    if not isinstance(scope, dict):
        return False
    roots = scope.get("roots")
    if not isinstance(roots, list):
        return False
    folded = os.path.normcase(path.replace("/", os.sep))
    for root in roots:
        if not isinstance(root, str) or not root:
            continue
        if root == ".":
            return True
        folded_root = os.path.normcase(root.replace("/", os.sep))
        if folded == folded_root or folded.startswith(folded_root + os.sep):
            return True
    return False


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
    if is_protected(path):
        return {"decision": "block", "reason": "protected path", "path": path}
    in_area = _in_granted_areas(path, ownership)
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
    if kind == "existing_file" and path_key not in approved and not in_area:
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
    return {"decision": "grant", "path": path, "run_id": ownership.get("run_id"), "family_id": ownership.get("family_id"),
            "scope": "areas" if in_area else "exact"}


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
        record = {"path": relative, "run_id": identity[0], "family_id": identity[1]}
        if any(owner.get(field) for field in ("task_id", "attempt_id", "grant_id")):
            if not all(owner.get(field) for field in ("task_id", "attempt_id", "grant_id")):
                raise ValueError("incomplete supervisor grant identity")
            record.update(task_id=owner["task_id"], attempt_id=owner["attempt_id"],
                          grant_id=owner["grant_id"], issuer="supervisor",
                          contracts=owner.get("contracts", []))
            record["signature"] = sign_issued(record, os.environ.get("PIPELINE_SCOPE_GRANT_KEY"))
        records[key] = record
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
