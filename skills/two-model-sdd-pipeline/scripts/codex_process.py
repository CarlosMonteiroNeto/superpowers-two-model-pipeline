"""Owned, bounded subprocess capture for worker adapters."""
import os
import signal
import subprocess
import time


class ProcessLaunchError(OSError):
    """The child process could not be created; no provider work began."""


def _start_identity(pid):
    if os.name == "nt":
        query = "$p=Get-Process -Id %d -ErrorAction Stop; $p.StartTime.ToUniversalTime().Ticks" % pid
        result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", query], capture_output=True, text=True, timeout=15)
        return result.stdout.strip() if result.returncode == 0 else None
    stat = "/proc/%d/stat" % pid
    try:
        fields = open(stat, encoding="ascii").read().split()
        return fields[21]
    except (OSError, IndexError):
        # macOS/other POSIX: use ps start time as a best-effort stable identity.
        result = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=5)
        return result.stdout.strip() or None


def _kill_unverified_child(proc):
    """Stop the process tree created by this Popen before ownership is recorded."""
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            result = None
        if result is None or result.returncode != 0:
            try:
                proc.kill()
            except OSError:
                pass
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            try:
                proc.kill()
            except OSError:
                pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass
        proc.wait(timeout=5)


def _terminate_direct_child(proc, ownership, grace_seconds):
    """Terminate an owned process tree, then reap this exact Popen child.

    External cancellation has no Popen handle and must never wait on arbitrary
    PIDs. This helper is only for the direct child created by run_owned.
    """
    if (not isinstance(ownership, dict) or ownership.get("pid") != proc.pid
            or not isinstance(ownership.get("start_identity"), str)
            or not ownership["start_identity"]):
        raise ValueError("direct child ownership identity does not match Popen")
    if isinstance(grace_seconds, bool) or not isinstance(grace_seconds, (int, float)) or grace_seconds < 0:
        raise ValueError("grace_seconds must be nonnegative")
    identity = ownership["start_identity"]
    matches = _start_identity(proc.pid) == identity
    if matches:
        if os.name == "nt":
            try:
                result = subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                        capture_output=True, timeout=max(1, grace_seconds + 1))
            except (OSError, subprocess.SubprocessError):
                result = None
            if result is None or result.returncode != 0:
                try: proc.kill()
                except OSError: pass
        else:
            try: os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            deadline = time.monotonic() + grace_seconds
            while time.monotonic() < deadline and _start_identity(proc.pid) == identity:
                time.sleep(min(0.05, max(0, deadline - time.monotonic())))
            # Keep the unreaped direct child as the ownership anchor while
            # escalating the process group; a zombie still has its start id.
            if _start_identity(proc.pid) == identity:
                try: os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError: pass
    try:
        proc.wait(timeout=max(1.0, grace_seconds + 1.0))
    except subprocess.TimeoutExpired:
        if _start_identity(proc.pid) == identity:
            if os.name == "nt":
                try: proc.kill()
                except OSError: pass
            else:
                try: os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError: pass
            proc.wait(timeout=5)
        else:
            raise RuntimeError("owned direct child could not be reaped safely")
def run_owned(argv, cwd, stdin_text="", timeout=None, env=None, on_start=None):
    if not isinstance(argv, (list, tuple)) or not argv or not all(isinstance(x, str) for x in argv):
        raise ValueError("argv must be a nonempty string array")
    kwargs = {"cwd": cwd, "stdin": subprocess.PIPE, "stdout": subprocess.PIPE,
              "stderr": subprocess.PIPE, "env": env, "text": False}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(list(argv), **kwargs)
    except OSError as exc:
        raise ProcessLaunchError(str(exc)) from exc
    started = time.time()
    try:
        start_identity = _start_identity(proc.pid)
    except (OSError, subprocess.SubprocessError) as exc:
        _kill_unverified_child(proc)
        raise RuntimeError("could not verify process start identity") from exc
    ownership = {"pid": proc.pid, "start_identity": start_identity}
    if not start_identity:
        _kill_unverified_child(proc)
        raise RuntimeError("could not verify process start identity")
    if on_start is not None:
        if not callable(on_start): raise ValueError("on_start must be callable")
        try: on_start(dict(ownership))
        except Exception:
            _terminate_direct_child(proc, ownership, 0)
            raise
    timed_out = False
    try:
        out, err = proc.communicate(stdin_text.encode("utf-8"), timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_direct_child(proc, ownership, 1.0)
        out, err = proc.communicate(timeout=5)
    except KeyboardInterrupt:
        _terminate_direct_child(proc, ownership, 1.0)
        try: proc.communicate(timeout=5)
        finally: raise
    return {"pid": proc.pid, "started": started, "start_identity": start_identity, "returncode": proc.returncode,
            "timed_out": timed_out,
            "stdout": out.decode("utf-8", errors="strict"),
            "stderr": err.decode("utf-8", errors="strict"), "argv": list(argv),
            "cwd": os.path.abspath(cwd)}


def stop_owned_processes(records, grace_seconds):
    if isinstance(grace_seconds, bool) or not isinstance(grace_seconds, (int, float)) or grace_seconds < 0:
        raise ValueError("grace_seconds must be nonnegative")
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("pid"), int) or not isinstance(record.get("start_identity"), str) or not record.get("start_identity"):
            raise ValueError("process ownership record requires pid and verified start identity")
        pid = record["pid"]
        try:
            if _start_identity(pid) != record["start_identity"]:
                continue
            if os.name == "nt":
                # taskkill /T scopes termination to the recorded process tree.
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=max(1, grace_seconds + 1))
            else:
                os.killpg(pid, signal.SIGTERM)
                deadline = time.monotonic() + grace_seconds
                while time.monotonic() < deadline:
                    try: os.kill(pid, 0)
                    except OSError: break
                    time.sleep(.05)
                try: os.killpg(pid, signal.SIGKILL)
                except OSError: pass
            deadline = time.monotonic() + max(1.0, grace_seconds + 1.0)
            while time.monotonic() < deadline and _start_identity(pid) == record["start_identity"]:
                time.sleep(.05)
            if _start_identity(pid) == record["start_identity"]:
                raise RuntimeError("owned process did not terminate: {}".format(pid))
        except ProcessLookupError:
            pass
        except OSError:
            pass
