"""Backend-neutral classified retry policy."""
def retry_decision(exit_code, attempt, max_attempts=3, started=False):
    if isinstance(exit_code, bool) or not isinstance(exit_code, int): raise ValueError("exit code must be integer")
    if attempt < 1 or max_attempts < 1: raise ValueError("attempt counts must be positive")
    retry = exit_code == 5 and not started and attempt < min(max_attempts, 3)
    return {"retry": retry, "delay_seconds": (1 if attempt == 1 else 3) if retry else 0,
            "reason": "confirmed_pre_exec_transient" if retry else "do_not_replay"}
