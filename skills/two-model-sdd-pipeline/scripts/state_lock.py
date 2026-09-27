"""Exclusive state locks carrying verifiable process and run ownership."""
import contextlib
import json
import os
import socket
import tempfile
import time
import sys
import subprocess


def _start_identity(pid):
    if pid == os.getpid():
        return str(int(time.time() * 1000))
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
            kernel.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
            kernel.GetProcessTimes.restype = wintypes.BOOL
            handle = kernel.OpenProcess(0x1000, False, pid)
            if not handle: return None
            creation, exit_time, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
            try:
                ok = kernel.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exit_time), ctypes.byref(kernel_time), ctypes.byref(user_time))
                if not ok: return None
                return "{}:{}".format(creation.dwHighDateTime, creation.dwLowDateTime)
            finally:
                kernel.CloseHandle(handle)
        except Exception:
            return None
    try:
        with open("/proc/{}/stat".format(pid), encoding="ascii") as f:
            return f.read().split(") ", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


@contextlib.contextmanager
def acquire_lock(path: str, owner: dict):
    if not isinstance(owner, dict) or not all(owner.get(k) for k in ("repository_id", "branch", "run_id")):
        raise ValueError("lock owner requires repository_id, branch and run_id")
    absolute = os.path.abspath(path)
    os.makedirs(os.path.dirname(absolute) or ".", exist_ok=True)
    data = dict(owner, pid=os.getpid(), process_start=_start_identity(os.getpid()), hostname=socket.gethostname(), acquired_at=time.time())
    fd = None
    try:
        fd = os.open(absolute, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            fd = None
            json.dump(data, f, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
    except FileExistsError as exc:
        try:
            with open(absolute, encoding="utf-8") as f: existing = json.load(f)
            owner_summary = "pid={}, start={}, run={}".format(existing.get("pid"), existing.get("process_start"), existing.get("run_id"))
        except Exception:
            owner_summary = "owner metadata is unreadable"
        raise RuntimeError("integration state is owned at {} ({})".format(absolute, owner_summary)) from exc
    finally:
        if fd is not None:
            os.close(fd)
    try:
        yield data
    finally:
        try:
            with open(absolute, encoding="utf-8") as f:
                current = json.load(f)
            if current.get("pid") == data["pid"] and current.get("run_id") == data["run_id"] and current.get("process_start") == data["process_start"]:
                os.unlink(absolute)
        except FileNotFoundError:
            pass


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 4 or argv[0] != "--run":
        print("usage: state_lock.py --run LOCK OWNER_JSON -- COMMAND [ARGS...]", file=sys.stderr)
        return 2
    path, owner_json = argv[1], argv[2]
    if argv[3] != "--" or len(argv) < 5:
        return 2
    try:
        owner = json.loads(owner_json)
        with acquire_lock(path, owner):
            env = dict(os.environ, PIPELINE_LOCK_HELD="1")
            return subprocess.call(argv[4:], env=env)
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print("STATE-LOCK: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
