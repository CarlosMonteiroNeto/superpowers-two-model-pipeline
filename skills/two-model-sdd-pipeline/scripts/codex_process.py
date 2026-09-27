"""Owned, bounded subprocess capture for worker adapters."""
import os
import signal
import subprocess
import time


def _start_identity(pid):
    if os.name == "nt":
        query = "$p=Get-Process -Id %d -ErrorAction Stop; $p.StartTime.ToUniversalTime().Ticks" % pid
        result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", query], capture_output=True, text=True, timeout=5)
        return result.stdout.strip() if result.returncode == 0 else None
    stat = "/proc/%d/stat" % pid
    try:
        fields = open(stat, encoding="ascii").read().split()
        return fields[21]
    except (OSError, IndexError):
        # macOS/other POSIX: use ps start time as a best-effort stable identity.
        result = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=5)
        return result.stdout.strip() or None


def run_owned(argv, cwd, stdin_text="", timeout=None, env=None, on_start=None):
    if not isinstance(argv, (list, tuple)) or not argv or not all(isinstance(x, str) for x in argv):
        raise ValueError("argv must be a nonempty string array")
    kwargs = {"cwd": cwd, "stdin": subprocess.PIPE, "stdout": subprocess.PIPE,
              "stderr": subprocess.PIPE, "env": env, "text": False}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(list(argv), **kwargs)
    started = time.time()
    start_identity = _start_identity(proc.pid)
    ownership = {"pid": proc.pid, "start_identity": start_identity}
    if not start_identity:
        stop_owned_processes([ownership], 0)
        raise RuntimeError("could not verify process start identity")
    if on_start is not None:
        if not callable(on_start): raise ValueError("on_start must be callable")
        try: on_start(dict(ownership))
        except Exception:
            stop_owned_processes([ownership], 0)
            raise
    try:
        out, err = proc.communicate(stdin_text.encode("utf-8"), timeout=timeout)
    except subprocess.TimeoutExpired:
        stop_owned_processes([ownership], 1.0)
        out, err = proc.communicate()
    return {"pid": proc.pid, "started": started, "start_identity": start_identity, "returncode": proc.returncode,
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
        except ProcessLookupError:
            pass
        except OSError:
            pass
