"""Durable family-scoped budget for external operator invocations."""

import json
import os
import tempfile
import pathlib
import hashlib
import sys
from contextlib import contextmanager


DEFAULT_POLICY = {"cycle_allowances": [5, 3, 3], "max_cycles": 3}


def _validated(identity, policy):
    if not isinstance(identity, dict) or any(not identity.get(key) for key in ("run_id", "task_family", "task_id", "role", "dispatch_id")):
        raise ValueError("complete dispatch identity required")
    if identity["role"] != "operator":
        raise ValueError("only external operator invocations consume this budget")
    if not isinstance(policy, dict):
        raise ValueError("budget policy must be an object")
    allowances = policy.get("cycle_allowances", DEFAULT_POLICY["cycle_allowances"])
    maximum = policy.get("max_cycles", len(allowances))
    if (not isinstance(allowances, list) or not allowances or not all(type(x) is int and x > 0 for x in allowances)
            or type(maximum) is not int or maximum < 1 or maximum > len(allowances)):
        raise ValueError("invalid cycle allowances")
    return allowances[:maximum]


def _reserve_in_memory(identity, policy, state):
    allowances = _validated(identity, policy)
    family_key = json.dumps([identity["run_id"], str(identity["task_family"])], separators=(",", ":"))
    family = state.setdefault(family_key, {"reservations": {}, "cycle_allowances": allowances,
                                            "transport_attempts": 0})
    if family["cycle_allowances"] != allowances:
        raise ValueError("budget policy cannot change during a task family")
    key = identity["dispatch_id"]
    prior = family["reservations"].get(key)
    if prior:
        if prior["task_id"] != identity["task_id"] or prior["role"] != identity["role"]:
            raise ValueError("dispatch identity reused for a different task or role")
        return dict(prior["result"])
    count = len(family["reservations"])
    if count >= sum(allowances):
        raise ValueError("coder invocation budget exhausted")
    cycle = 1
    used = count
    for allowance in allowances:
        if used < allowance:
            break
        used -= allowance
        cycle += 1
    if policy.get("require_assessment") and cycle > int(policy.get("director_assessments", 0)) + 1:
        raise RuntimeError("director assessment required before next coder cycle")
    total = count + 1
    result = {"cycle_allowances": list(allowances), "cycle": cycle,
              "cycle_invocations": used + 1, "coder_invocations": total,
              "transport_attempts": family["transport_attempts"],
              "director_required": used + 1 == allowances[cycle - 1],
              "pause": total == sum(allowances)}
    family["reservations"][key] = {"task_id": identity["task_id"], "role": identity["role"], "result": result}
    return dict(result)


def _record_prestart_in_memory(identity, state):
    family_key = json.dumps([identity["run_id"], str(identity["task_family"])], separators=(",", ":"))
    family = state.get(family_key)
    if not family:
        raise ValueError("no budget reservation for this family")
    if identity["dispatch_id"] not in family["reservations"]:
        raise ValueError("no budget reservation for this dispatch")
    del family["reservations"][identity["dispatch_id"]]
    family["transport_attempts"] += 1
    return family["transport_attempts"]


@contextmanager
def _locked(path):
    # Kernel locks are released after a crash; a stale O_EXCL lock file would
    # prevent the required recovery of already-reserved invocation identities.
    with open(path, "a+b") as handle:
        if os.name == "nt":
            import msvcrt
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _mutate(identity, policy, *, state=None, state_path=None, prestart=False):
    if (state is None) == (state_path is None):
        raise ValueError("provide exactly one of state or state_path")
    if state is not None:
        if not isinstance(state, dict):
            raise ValueError("state must be an object")
        return _record_prestart_in_memory(identity, state) if prestart else _reserve_in_memory(identity, policy, state)
    path = os.path.abspath(state_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lock = path + ".lock"
    with _locked(lock):
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("dispatch budget registry is corrupt")
        result = _record_prestart_in_memory(identity, data) if prestart else _reserve_in_memory(identity, policy, data)
        fd, temp = tempfile.mkstemp(prefix="budget-", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        return result


def reserve(identity: dict, policy: dict, *, state=None, state_path=None) -> dict:
    """Reserve once per dispatch id, atomically when a durable path is supplied."""
    return _mutate(identity, policy, state=state, state_path=state_path)


def record_prestart_failure(identity: dict, *, state=None, state_path=None) -> int:
    """Release an invocation only after the adapter proves no worker started."""
    return _mutate(identity, None, state=state, state_path=state_path, prestart=True)


def status(run_id, task_family, *, state=None, state_path=None):
    """Describe whether the next cycle needs a director assessment."""
    if state is None:
        try:
            with open(state_path, encoding="utf-8") as handle:
                state = json.load(handle)
        except FileNotFoundError:
            state = {}
    family_key = json.dumps([run_id, str(task_family)], separators=(",", ":"))
    family = state.get(family_key)
    if not family:
        return {"coder_invocations": 0, "director_required": False, "pause": False}
    count = len(family["reservations"])
    allowances = family["cycle_allowances"]
    return {"coder_invocations": count,
            "director_required": count in [sum(allowances[:i]) for i in range(1, len(allowances) + 1)],
            "pause": count >= sum(allowances)}


def family_for_task(plan, task_id):
    items = {str(item["id"]): item for item in plan["tasks"]}
    item = items[str(task_id)]
    seen = set()
    while item.get("corrects") is not None:
        key = str(item["corrects"])
        if key in seen or key not in items:
            raise ValueError("invalid corrective task family")
        seen.add(key)
        item = items[key]
    return item["id"]


def workspace_status(workspace, task_id):
    ws = pathlib.Path(workspace)
    with open(ws / ".pipeline-identity.json", encoding="utf-8") as handle:
        identity = json.load(handle)
    with open(ws / "plan.json", encoding="utf-8") as handle:
        plan = json.load(handle)
    family = family_for_task(plan, task_id)
    return status(identity["run_id"], family, state_path=str(ws / "dispatch-budget.json"))


def opencode_policy(workspace):
    """Read the launch choice; the first reservation freezes it for the family."""
    manifest = pathlib.Path(workspace) / "run-manifest.json"
    if manifest.is_file():
        limits = json.loads(manifest.read_text(encoding="utf-8")).get(
            "coder_cycle_limits", DEFAULT_POLICY["cycle_allowances"])
    elif os.environ.get("PIPELINE_CODER_CYCLE_LIMITS"):
        limits = json.loads(os.environ["PIPELINE_CODER_CYCLE_LIMITS"])
    else:
        limits = DEFAULT_POLICY["cycle_allowances"]
    if not isinstance(limits, list) or len(limits) != 3:
        raise ValueError("coder cycle limits must contain three allowances")
    _validated({"run_id": "config", "task_family": "config", "task_id": 1,
                "role": "operator", "dispatch_id": "config"}, {"cycle_allowances": limits})
    return {"cycle_allowances": limits, "max_cycles": len(limits)}


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "status":
        try:
            print("assess" if workspace_status(sys.argv[2], sys.argv[3])["director_required"] else "continue")
        except FileNotFoundError:
            print("continue")
    elif len(sys.argv) == 6 and sys.argv[1] in ("reserve-opencode", "release-opencode"):
        ws = pathlib.Path(sys.argv[2]); task_id = sys.argv[3]
        prompt_path = pathlib.Path(sys.argv[4]); session = sys.argv[5]
        identity = json.loads((ws / ".pipeline-identity.json").read_text(encoding="utf-8"))
        plan = json.loads((ws / "plan.json").read_text(encoding="utf-8"))
        family = family_for_task(plan, task_id)
        stamp = str(prompt_path.stat().st_mtime_ns)
        dispatch_id = hashlib.sha256("\0".join((identity["run_id"],str(task_id),str(prompt_path),stamp,session)).encode()).hexdigest()[:32]
        ledger = ws / "ledger.jsonl"
        assessments = 0
        if ledger.exists():
            for line in ledger.read_text(encoding="utf-8").splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") == "budget_cycle_assessed" and str(event.get("task_family")) == str(family):
                    assessments += 1
        operator_identity={"run_id": identity["run_id"], "task_family": family, "task_id": int(task_id),
                           "role": "operator", "dispatch_id": dispatch_id}
        if sys.argv[1] == "release-opencode":
            record_prestart_failure(operator_identity,state_path=str(ws / "dispatch-budget.json"))
        else:
            policy = dict(opencode_policy(ws), require_assessment=True, director_assessments=assessments)
            reserve(operator_identity, policy,state_path=str(ws / "dispatch-budget.json"))
    else:
        raise SystemExit("usage: dispatch_budget.py status WORKSPACE TASK | reserve-opencode|release-opencode WORKSPACE TASK PROMPT SESSION")
