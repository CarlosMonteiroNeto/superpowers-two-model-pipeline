"""Deterministic Site 5 task-fusion validation and candidate construction."""
import hashlib
import json
import os
import pathlib
import subprocess
import sys

from pathclass import is_test_path


MAX_FILES = 6
MAX_ACCEPTANCE = 12
MAX_QUESTIONS = 32
MAX_REQUEST_BYTES = 65536


def canonical_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def plan_hash(plan):
    return hashlib.sha256(canonical_json(plan).encode("utf-8")).hexdigest()


def _canonical_touch(path):
    return (isinstance(path, str) and bool(path) and path == path.replace("\\", "/")
            and not path.startswith("/") and not path.startswith("./") and ":" not in path
            and "//" not in path and ".." not in path.split("/")
            and not any(mark in path for mark in ("*", "?", "[", "]")))


def _tasks_by_id(plan):
    tasks = plan.get("tasks") if isinstance(plan, dict) else None
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("plan requires a nonempty tasks list")
    result = {}
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError("each task must be an object")
        identifier = task.get("id")
        if not isinstance(identifier, int) or isinstance(identifier, bool) or identifier <= 0 or identifier in result:
            raise ValueError("task IDs must be unique positive integers")
        result[identifier] = task
    return result


def validate_plan(plan):
    """Validate the draft before any candidate or provider work."""
    tasks = _tasks_by_id(plan)
    for identifier, task in tasks.items():
        for field in ("title", "summary"):
            if not isinstance(task.get(field), str) or not task[field].strip():
                raise ValueError("task {} requires a nonempty {}".format(identifier, field))
        for field in ("acceptance", "spec_refs", "touches"):
            value = task.get(field)
            if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item.strip() for item in value):
                raise ValueError("task {} requires nonempty {} strings".format(identifier, field))
        for path in task["touches"]:
            if not _canonical_touch(path):
                raise ValueError("task {} has noncanonical touch path".format(identifier))
            if is_test_path(path):
                raise ValueError("task {} touch path is a test path".format(identifier))
        dependencies = task.get("depends_on", [])
        if not isinstance(dependencies, list) or any(not isinstance(dep, int) or isinstance(dep, bool) for dep in dependencies):
            raise ValueError("task {} requires integer dependencies".format(identifier))
        if len(set(dependencies)) != len(dependencies) or identifier in dependencies or any(dep not in tasks for dep in dependencies):
            raise ValueError("task {} has invalid dependencies".format(identifier))
    _topological_order(tasks)


def _topological_order(tasks):
    pending = {identifier: set(task.get("depends_on", [])) for identifier, task in tasks.items()}
    order = []
    while pending:
        ready = sorted(identifier for identifier, dependencies in pending.items() if not dependencies)
        if not ready:
            raise ValueError("task dependencies contain a cycle")
        # Reconsider newly-ready nodes after every pop so original ID is the
        # stable priority across the whole sort, not merely one wave.
        identifier = ready[0]
        order.append(identifier)
        del pending[identifier]
        completed = {identifier}
        for dependencies in pending.values():
            dependencies.difference_update(completed)
    return order


def _depends_on(tasks, start, target):
    todo = list(tasks[start].get("depends_on", []))
    seen = set()
    while todo:
        current = todo.pop()
        if current == target:
            return True
        if current not in seen:
            seen.add(current)
            todo.extend(tasks[current].get("depends_on", []))
    return False


def _overlap(left, right):
    return bool(set(left["touches"]) & set(right["touches"]))


def pair_reasons(tasks, left_id, right_id, overlap=None):
    left, right = tasks[left_id], tasks[right_id]
    reasons = []
    if left.get("corrects") is not None or right.get("corrects") is not None:
        reasons.append("corrective tasks are not eligible")
    if left.get("fused_from") is not None or right.get("fused_from") is not None:
        reasons.append("already-fused tasks are not eligible")
    if _depends_on(tasks, left_id, right_id) or _depends_on(tasks, right_id, left_id):
        reasons.append("tasks have a transitive dependency")
    if overlap if overlap is not None else _overlap(left, right):
        reasons.append("touches overlap")
    if len(set(left["touches"]) | set(right["touches"])) > MAX_FILES or len(left["acceptance"]) + len(right["acceptance"]) > MAX_ACCEPTANCE:
        reasons.append("pair exceeds limits")
    return reasons


def batch_pairs(pairs, *, model=None, schema_builder=None):
    """Split stable candidates without truncating any task evidence."""
    batches, oversized, current = [], [], []
    def request_bytes(values):
        if schema_builder is None:
            return canonical_json(values).encode("utf-8")
        schema = schema_builder(values)
        state = {"pairs": [{"left": value["left"], "right": value["right"]} for value in values]}
        request = {"model": model or schema.get("model"), "state": state, "questions": schema.get("questions")}
        return canonical_json(request).encode("utf-8")
    for pair in pairs:
        single = request_bytes([pair])
        if len(single) > MAX_REQUEST_BYTES:
            oversized.append(pair["ids"])
            continue
        proposed = current + [pair]
        if current and (len(proposed) > MAX_QUESTIONS or len(request_bytes(proposed)) > MAX_REQUEST_BYTES):
            batches.append(current)
            current = [pair]
        else:
            current = proposed
    if current:
        batches.append(current)
    return batches, oversized


def build_candidates(plan, workspace, overlap_runner=None):
    """Return deterministic eligible pairs plus exclusions for an exact draft."""
    validate_plan(plan)
    if not isinstance(workspace, (str, os.PathLike)) or not str(workspace):
        raise ValueError("workspace is required")
    tasks = _tasks_by_id(plan)
    snapshot = pathlib.Path(workspace) / ".jev" / "site5" / "fusion" / plan_hash(plan) / "plan.json"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(canonical_json(plan), encoding="utf-8")
    runner = overlap_runner or (lambda _left, _right: subprocess.run(
        [sys.executable, str(pathlib.Path(__file__).with_name("touches-overlap")), str(snapshot.parent), str(_left), str(_right)],
        text=True, capture_output=True).returncode)
    pairs, exclusions = [], {}
    identifiers = sorted(tasks)
    for offset, left_id in enumerate(identifiers):
        for right_id in identifiers[offset + 1:]:
            left, right = tasks[left_id], tasks[right_id]
            key = "{},{}".format(left_id, right_id)
            overlap_exit = runner(left_id, right_id)
            if overlap_exit == 2:
                raise ValueError("touches-overlap rejected exact draft snapshot")
            if overlap_exit not in (0, 1):
                raise ValueError("touches-overlap failed")
            reasons = pair_reasons(tasks, left_id, right_id, overlap=overlap_exit == 1)
            if reasons:
                exclusions[key] = reasons
            else:
                pairs.append({"ids": [left_id, right_id], "left": left, "right": right,
                              "candidate_hash": hashlib.sha256(canonical_json({"left": left, "right": right}).encode("utf-8")).hexdigest()})
    return {"draft_hash": plan_hash(plan), "pairs": pairs, "exclusions": exclusions}
