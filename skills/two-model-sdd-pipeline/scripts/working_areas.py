"""Directory authority and atomic scheduling reservations.

Tasks opt in through ``task["working_areas"]`` (canonical repository-relative
directories; ``"."`` is the repository root and is never inferred). Tasks
without it keep legacy exact-path authority. Overlapping reservations run
sequentially even across worktrees; disjoint scopes may run concurrently.

 Reservations persist in a JSON registry guarded by state_lock mutual
exclusion. A live owner is never retired by timeout alone: retirement
requires verified process termination. A correction in the same family
retains its reservation.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from state_lock import acquire_lock


def _creation_identity(pid: int):
    """Start identity observable by other processes.

    Mirrors state_lock process tracking without its self-process shortcut
    (a timestamp), so a stored identity always matches what a later
    liveness check observes for the same process.
    """
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = (
                wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
            kernel.GetProcessTimes.argtypes = (
                wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
            kernel.GetProcessTimes.restype = wintypes.BOOL
            kernel.GetExitCodeProcess.argtypes = (
                wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
            kernel.GetExitCodeProcess.restype = wintypes.BOOL
            handle = kernel.OpenProcess(0x1000, False, pid)
            if not handle:
                return None
            try:
                times = [wintypes.FILETIME() for _ in range(4)]
                if not kernel.GetProcessTimes(
                        handle, *[ctypes.byref(item) for item in times]):
                    return None
                exit_code = wintypes.DWORD()
                if not kernel.GetExitCodeProcess(
                        handle, ctypes.byref(exit_code)):
                    return None
                if exit_code.value != 259:  # STILL_ACTIVE
                    return None
                creation = times[0]
                return "{}:{}".format(
                    creation.dwHighDateTime, creation.dwLowDateTime)
            finally:
                kernel.CloseHandle(handle)
        except Exception:
            return None
    try:
        with open("/proc/{}/stat".format(pid), encoding="ascii") as handle:
            fields = handle.read().split(") ", 1)[1].split()
            if fields[0] == "Z":
                return None
            return fields[19]
    except (OSError, IndexError):
        return None


def _repo_root(repo_root: str) -> str:
    if not isinstance(repo_root, str) or not repo_root:
        raise ValueError("repository root is required")
    return os.path.realpath(repo_root)


def _canonical(repo_root: str, value: str) -> str:
    """Canonicalize one repo-relative directory or file path.

    ``"."`` addresses the repository itself. Everything else must stay
    inside the root after alias resolution (symlinks, junctions, case).
    Nonexistent descendants are allowed; traversal is not.
    """
    if not isinstance(value, str) or not value.strip() or "\\" in value:
        raise ValueError("invalid working area: %r" % (value,))
    cleaned = value.strip()
    if cleaned == ".":
        return "."
    cleaned = cleaned.rstrip("/")
    if (cleaned.startswith("/") or len(cleaned) > 1 and cleaned[1] == ":"
            or any(part in ("", ".", "..")
                   for part in cleaned.split("/"))):
        raise ValueError("working area escapes the repository: %r" % (value,))
    absolute = os.path.realpath(
        os.path.join(repo_root, *cleaned.split("/")))
    try:
        if os.path.commonpath((repo_root, absolute)) != repo_root:
            raise ValueError(
                "working area resolves outside the repository: %r" % (value,))
    except ValueError:
        raise ValueError(
            "working area resolves outside the repository: %r" % (value,))
    return os.path.relpath(absolute, repo_root).replace(os.sep, "/")


def _legacy_paths(task: dict) -> list:
    paths = []
    for key in ("touches", "new_test_files", "shared_resources", "resources"):
        values = task.get(key) or []
        if not isinstance(values, list):
            raise ValueError("task %r must be a list" % key)
        paths.extend(values)
    verification = task.get("verification") or {}
    if isinstance(verification, dict):
        for key in ("new_test_files",):
            values = verification.get(key) or []
            if not isinstance(values, list):
                raise ValueError("task verification paths must be a list")
            paths.extend(values)
    return [str(path) for path in paths]


def normalize(task: dict, repo_root: str) -> dict:
    """Return the canonical scheduling scope for one task.

    ``{"mode": "areas", "roots": [...], "exact_paths": []}`` when the task
    opts in through a non-empty ``working_areas`` list, else legacy
    ``{"mode": "legacy", "roots": [], "exact_paths": [...]}``.
    """
    if not isinstance(task, dict):
        raise ValueError("task must be an object")
    root = _repo_root(repo_root)
    areas = task.get("working_areas")
    if isinstance(areas, list) and areas:
        if not all(isinstance(item, str) and item.strip() for item in areas):
            raise ValueError("working_areas must be non-empty strings")
        return {"mode": "areas",
                "roots": sorted({_canonical(root, item) for item in areas}),
                "exact_paths": []}
    return {"mode": "legacy", "roots": [],
            "exact_paths": sorted(
                {_canonical(root, item) for item in _legacy_paths(task)})}


def _fold(path: str) -> str:
    return os.path.normcase(path.replace("/", os.sep))


def _root_covers(container: str, inner: str) -> bool:
    if container == "." or inner == ".":
        return True
    folded_container = _fold(container)
    folded_inner = _fold(inner)
    return (folded_inner == folded_container
            or folded_inner.startswith(folded_container + os.sep))


def _path_in_root(path: str, root: str) -> bool:
    if root == ".":
        return True
    folded_path = _fold(path)
    folded_root = _fold(root)
    return (folded_path == folded_root
            or folded_path.startswith(folded_root + os.sep))


def _scopes_overlap(first: dict, second: dict) -> bool:
    for left in first.get("roots", []):
        for right in second.get("roots", []):
            if _root_covers(left, right) or _root_covers(right, left):
                return True
    for root in list(first.get("roots", [])) + list(second.get("roots", [])):
        for path in (list(first.get("exact_paths", []))
                     + list(second.get("exact_paths", []))):
            if _path_in_root(path, root):
                return True
    first_paths = {os.path.normcase(path)
                   for path in first.get("exact_paths", [])}
    second_paths = {os.path.normcase(path)
                    for path in second.get("exact_paths", [])}
    return bool(first_paths & second_paths)


def overlap(left: dict, right: dict, repo_root: str) -> bool:
    """True when two normalized scopes must not run concurrently.

    Equal or nested directory roots overlap; ``src/a`` never covers
    ``src/ab``. A legacy exact path conflicts with an enclosing area and
    with an identical legacy path. An explicit ``"."`` root covers every
    scope. ``repo_root`` is accepted for signature symmetry with
    normalize; scopes must already share one canonical root.
    """
    if not isinstance(left, dict) or not isinstance(right, dict):
        raise ValueError("scopes must be objects")
    _repo_root(repo_root)
    return _scopes_overlap(left, right)


def _owner_identity(owner: dict) -> dict:
    if not isinstance(owner, dict):
        raise ValueError("reservation owner must be an object")
    run_id = owner.get("run_id")
    family_id = owner.get("family_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("reservation owner requires run_id")
    if family_id is None or isinstance(family_id, bool):
        raise ValueError("reservation owner requires family_id")
    identity = {"run_id": run_id, "family_id": family_id}
    if owner.get("task_id") is not None:
        identity["task_id"] = owner["task_id"]
    return identity


def _check_scope(scope: dict) -> dict:
    if not isinstance(scope, dict):
        raise ValueError("reservation scope must be an object")
    roots = scope.get("roots", [])
    exact = scope.get("exact_paths", [])
    if (not isinstance(roots, list) or not isinstance(exact, list)
            or not all(isinstance(item, str) and item for item in roots)
            or not all(isinstance(item, str) and item for item in exact)):
        raise ValueError("reservation scope paths must be strings")
    if not roots and not exact:
        raise ValueError("reservation scope must claim at least one path")
    return {"roots": sorted(set(roots)), "exact_paths": sorted(set(exact))}


def _alive(pid, start) -> bool:
    if pid == os.getpid():
        return True
    if not isinstance(start, str) or not start:
        return False
    try:
        current = _creation_identity(pid)
    except Exception:
        return False
    return current is not None and current == start


def _load_registry(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            records = json.load(handle)
    except FileNotFoundError:
        return {"reservations": []}
    if not isinstance(records, dict) or not isinstance(
            records.get("reservations"), list):
        raise ValueError("corrupt reservation registry")
    return records


def _store_registry(path: str, records: dict):
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".registry.tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(records, handle, sort_keys=True, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(str(tmp), str(target))


def _lock_owner(run_id: str) -> dict:
    return {"repository_id": "working-areas", "branch": "reservations",
            "run_id": run_id}


@contextlib.contextmanager
def _registry_locked(registry_path: str, run_id: str):
    """Mutual exclusion with bounded retries on contention.

    Concurrent schedulers serialize here; the loser retries instead of
    failing, so exactly one overlapping claim wins the race.
    """
    last = None
    for _ in range(200):
        try:
            with acquire_lock(
                    str(registry_path) + ".lock", _lock_owner(run_id)):
                yield
            return
        except RuntimeError as exc:
            if "is owned at" not in str(exc):
                raise
            last = exc
            time.sleep(0.05)
    raise last


def reserve(registry_path: str, owner: dict, scope: dict) -> dict:
    """Atomically claim directory authority for one owner.

    Same-family claims retain the existing reservation. A conflicting
    family wins only after verified termination of the recorded owner;
    a live owner is reported as a conflict with its identity. Returns
    ``{"decision": "granted"|"conflict", "owner": {...},
    "recovered": bool}``.
    """
    if not isinstance(registry_path, str) or not registry_path:
        raise ValueError("registry path is required")
    identity = _owner_identity(owner)
    claim = _check_scope(scope)
    recovered = False
    with _registry_locked(registry_path, identity["run_id"]):
        records = _load_registry(registry_path)
        reservations = records["reservations"]
        for existing in list(reservations):
            if not _scopes_overlap(
                    {"roots": existing.get("roots", []),
                     "exact_paths": existing.get("exact_paths", [])}, claim):
                continue
            held = existing.get("owner", {})
            if held.get("family_id") == identity["family_id"]:
                return {"decision": "granted", "owner": held,
                        "recovered": False}
            if _alive(existing.get("pid"), existing.get("process_start")):
                return {"decision": "conflict", "owner": held,
                        "recovered": False}
            reservations.remove(existing)
            recovered = True
        try:
            process_start = _creation_identity(os.getpid())
        except Exception:
            process_start = None
        reservations.append({
            "owner": identity,
            "roots": claim["roots"],
            "exact_paths": claim["exact_paths"],
            "pid": os.getpid(),
            "process_start": process_start,
            "acquired_at": time.time(),
        })
        _store_registry(registry_path, records)
    return {"decision": "granted", "owner": identity, "recovered": recovered}


def release(registry_path: str, owner: dict) -> None:
    """Release one reservation after verified lifecycle completion.

    The owner must match a held reservation on run, family, and task
    identity and must attest completion explicitly (``completed: True``).
    Anything else fails closed.
    """
    if not isinstance(registry_path, str) or not registry_path:
        raise ValueError("registry path is required")
    identity = _owner_identity(owner)
    if owner.get("task_id") is None or owner.get("completed") is not True:
        raise ValueError(
            "release requires matching task identity and verified "
            "lifecycle completion")
    identity["task_id"] = owner["task_id"]
    with _registry_locked(registry_path, identity["run_id"]):
        records = _load_registry(registry_path)
        reservations = records["reservations"]
        for existing in reservations:
            held = existing.get("owner", {})
            if (held.get("run_id") == identity["run_id"]
                    and held.get("family_id") == identity["family_id"]
                    and held.get("task_id") == identity["task_id"]):
                reservations.remove(existing)
                _store_registry(registry_path, records)
                return None
    raise ValueError("no matching reservation is held")


def check_area(repo_root: str, value: str) -> str:
    """Validate one opted-in directory entry, returning its canonical form."""
    return _canonical(_repo_root(repo_root), value)


def reserve_for_task(registry_path: str, workspace: str, task_id) -> dict:
    """Reserve one plan task's scope: family walks corrects, scope normalizes."""
    run_id, repo_root, family, item = _family_inputs(workspace, task_id)
    scope = normalize(item, repo_root)
    return reserve(registry_path,
                   {"run_id": run_id, "family_id": family,
                    "task_id": int(str(task_id))}, scope)


def _enclosing_repository(workspace: str) -> str:
    """Best-effort repository root for legacy identities without one."""
    try:
        import subprocess
        out = subprocess.run(
            ["git", "-C", workspace, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=30)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, ValueError):
        pass
    return workspace


def _family_inputs(workspace, task_id):
    ws = pathlib.Path(workspace)
    try:
        plan = json.loads((ws / "plan.json").read_text(encoding="utf-8"))
        identity = json.loads(
            (ws / ".pipeline-identity.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("run workspace plan or identity is missing") from exc
    run_id = identity.get("run_id")
    repo_root = identity.get("repository_root")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("pipeline identity run_id is missing")
    if not isinstance(repo_root, str) or not repo_root:
        repo_root = _enclosing_repository(str(ws))
    tasks = plan.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("workspace plan has no tasks list")
    try:
        wanted = int(str(task_id))
    except (TypeError, ValueError):
        raise ValueError("task id is invalid") from None
    items = {str(item.get("id")): item for item in tasks
             if isinstance(item, dict)}
    item = items.get(str(wanted))
    if item is None:
        raise ValueError("task is missing from workspace plan")
    seen = set()
    while item.get("corrects") is not None:
        parent = str(item["corrects"])
        if parent in seen or parent not in items:
            raise ValueError("invalid task correction-family chain")
        seen.add(parent)
        item = items[parent]
    return run_id, repo_root, int(item["id"]), items[str(wanted)]


def release_for_task(registry_path: str, workspace: str, task_id) -> None:
    """Release one plan task's reservation with lifecycle attestation."""
    run_id, repo_root, family, _item = _family_inputs(workspace, task_id)
    release(registry_path,
            {"run_id": run_id, "family_id": family,
             "task_id": int(str(task_id)), "completed": True})
    if len(argv) < 2:
        return 2
def _cli(argv):
    if len(argv) < 2:
        return 2
    command = argv[1]
    try:
        if command == "normalize" and len(argv) == 4:
            task = json.loads(argv[2])
            print(json.dumps(normalize(task, argv[3]), sort_keys=True))
            return 0
        if command == "reserve" and len(argv) == 5:
            result = reserve(argv[2], json.loads(argv[3]),
                             json.loads(argv[4]))
            print(json.dumps(result, sort_keys=True))
            return 0 if result["decision"] == "granted" else 1
        if command == "reserve-for-task" and len(argv) == 5:
            result = reserve_for_task(argv[2], argv[3], argv[4])
            print(json.dumps(result, sort_keys=True))
            return 0 if result["decision"] == "granted" else 1
        if command == "release-for-task" and len(argv) == 5:
            try:
                release_for_task(argv[2], argv[3], argv[4])
            except ValueError as exc:
                if str(exc) == "no matching reservation is held":
                    print(json.dumps({"decision": "no_match"},
                                     sort_keys=True))
                    return 1
                raise
            print(json.dumps({"decision": "released"}, sort_keys=True))
            return 0
        if command == "release" and len(argv) == 4:
            try:
                release(argv[2], json.loads(argv[3]))
            except ValueError as exc:
                if str(exc) == "no matching reservation is held":
                    print(json.dumps({"decision": "no_match"},
                                     sort_keys=True))
                    return 1
                raise
            print(json.dumps({"decision": "released"}, sort_keys=True))
            return 0
    except ValueError as exc:
        print("WORKING-AREAS: {}".format(exc), file=sys.stderr)
        return 2
    print("usage: working_areas.py normalize TASK_JSON REPO_ROOT | "
          "reserve REGISTRY OWNER_JSON SCOPE_JSON | "
          "reserve-for-task REGISTRY WORKSPACE TASK | "
          "release REGISTRY OWNER_JSON | "
          "release-for-task REGISTRY WORKSPACE TASK", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv))
