"""Private, site-isolated persistence for Jev cache, circuit and advisory data."""
import hashlib
import json
import os
import pathlib
import tempfile
import time
from contextlib import contextmanager


def _site_dir(workspace, site):
    if not isinstance(site, str) or not site or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in site):
        raise ValueError("site must be a lowercase namespace")
    path = pathlib.Path(workspace) / ".jev" / site
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_json(path, value):
    path = pathlib.Path(path)
    fd, name = tempfile.mkstemp(prefix=".jev-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        deadline = time.monotonic() + 2
        while True:
            try:
                os.replace(name, path)
                break
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.02)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
        return value
    except (OSError, ValueError, json.JSONDecodeError):
        return default


def cache_path(workspace, site, identity):
    return _site_dir(workspace, site) / "cache" / (identity + ".json")


def read_cache(workspace, site, identity):
    value = _read_json(cache_path(workspace, site, identity))
    return value if isinstance(value, dict) else None


def write_cache(workspace, site, identity, envelope):
    path = cache_path(workspace, site, identity)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json(path, envelope)
    return str(path)


def circuit_state(workspace, site):
    value = _read_json(_site_dir(workspace, site) / "circuit.json", {})
    return value if isinstance(value, dict) else {"failures": 0}


@contextmanager
def _locked(directory):
    """Cross-process lock using exclusive create, supported by Windows NTFS."""
    lock = pathlib.Path(directory) / "circuit.lock"
    deadline = time.monotonic() + 5
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise RuntimeError("timed out waiting for Jev persistence lock")
            time.sleep(.02)
    try:
        yield
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def write_circuit(workspace, site, failures):
    directory = _site_dir(workspace, site)
    _atomic_json(directory / "circuit.json", {"failures": int(failures), "updated_at": time.time()})


def reset_circuit(workspace, site):
    directory = _site_dir(workspace, site)
    with _locked(directory):
        _atomic_json(directory / "circuit.json", {"failures": 0, "updated_at": time.time()})


def record_failure(workspace, site):
    directory = _site_dir(workspace, site)
    with _locked(directory):
        current = _read_json(directory / "circuit.json", {})
        failures = int(current.get("failures", 0)) + 1 if isinstance(current, dict) else 1
        _atomic_json(directory / "circuit.json", {"failures": failures, "updated_at": time.time()})
        return failures


def record_success(workspace, site):
    reset_circuit(workspace, site)


def write_record(workspace, site, identity, record):
    """Write an advisory record. This never touches the pipeline ledger."""
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    required = {"state_identity", "policy_identity", "decision", "actual_action", "fallback", "timing", "usage"}
    if not isinstance(record, dict) or required - set(record):
        raise ValueError("advisory record lacks required evidence")
    if not isinstance(record["timing"], dict):
        raise ValueError("advisory timing must be an object")
    value = dict(record)
    value.update({"site": site, "identity": identity, "recorded_at": time.time()})
    directory = _site_dir(workspace, site) / "advisory"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (digest + ".json")
    _atomic_json(path, value)
    return str(path)
