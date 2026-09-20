"""Offline, explicit Site 5 fusion application."""
import copy
import math

from fusion_candidates import _tasks_by_id, _topological_order, canonical_json, pair_reasons, plan_hash, validate_plan


POLICY_VERSION = "site5-v1"
_TASK_FIELDS = {"id", "title", "summary", "touches", "acceptance", "spec_refs", "depends_on"}


def _hash_report(report):
    from fusion_candidates import canonical_json
    import hashlib
    return hashlib.sha256(canonical_json(report).encode("utf-8")).hexdigest()


def _qualifying_pairs(report):
    result = {}
    for pair in report.get("pairs", []):
        if not isinstance(pair, dict) or not isinstance(pair.get("ids"), list) or len(pair["ids"]) != 2:
            continue
        key = tuple(sorted(pair["ids"]))
        probabilities = pair.get("probabilities")
        numeric = list(probabilities.values()) if isinstance(probabilities, dict) else []
        if (pair.get("choice") == "same_shape_fuse" and isinstance(pair.get("confidence"), (int, float)) and math.isfinite(pair["confidence"]) and 0 <= pair["confidence"] <= 1 and pair["confidence"] >= .9
                and isinstance(probabilities, dict) and set(probabilities) == {"same_shape_fuse", "keep_separate"}
                and all(isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= 1 for value in numeric)
                and abs(sum(numeric) - 1) <= 1e-6 and probabilities["same_shape_fuse"] >= probabilities["keep_separate"]):
            result[key] = pair
    return result


def _stable_union(*values):
    result = []
    for value in values:
        for item in value:
            if item not in result:
                result.append(item)
    return result


def candidate_hash(plan, ids):
    tasks = _tasks_by_id(plan)
    first, second = sorted(ids)
    return __import__("hashlib").sha256(canonical_json({"left": tasks[first], "right": tasks[second]}).encode("utf-8")).hexdigest()


def _validate_selection(plan, report, selection):
    if not isinstance(report, dict) or report.get("draft_hash") != plan_hash(plan):
        raise ValueError("stale report draft hash")
    if report.get("policy_version") != POLICY_VERSION:
        raise ValueError("changed policy version")
    if canonical_json(report.get("source_snapshot")) != canonical_json(plan):
        raise ValueError("report source snapshot does not match draft")
    if not isinstance(selection, dict) or selection.get("draft_hash") != plan_hash(plan):
        raise ValueError("stale selection draft hash")
    if selection.get("report_hash") != _hash_report(report):
        raise ValueError("stale selection report hash")
    selected = selection.get("pairs")
    if not isinstance(selected, list):
        raise ValueError("selection pairs must be a list")
    return selected, _qualifying_pairs(report)


def apply_selection(plan, report, selection):
    """Apply an explicitly selected, qualifying report offline.

    Returns a new consecutive-ID plan and a string-keyed original-to-final map.
    """
    validate_plan(plan)
    source = copy.deepcopy(plan)
    selected, qualifying = _validate_selection(source, report, selection)
    tasks = _tasks_by_id(source)
    participating = set()
    normalized = []
    for selected_pair in selected:
        if not isinstance(selected_pair, dict):
            raise ValueError("selected pair must be an object")
        ids = selected_pair.get("ids")
        if not isinstance(ids, list) or len(ids) != 2 or any(not isinstance(item, int) for item in ids) or ids[0] == ids[1]:
            raise ValueError("selected pair IDs are invalid")
        key = tuple(sorted(ids))
        if key not in qualifying:
            raise ValueError("selected pair is not a qualifying recommendation")
        if qualifying[key].get("candidate_hash") != candidate_hash(source, key):
            raise ValueError("selected pair candidate identity is stale or forged")
        if pair_reasons(tasks, key[0], key[1]):
            raise ValueError("selected pair is no longer candidate-eligible")
        if any(identifier in participating for identifier in key):
            raise ValueError("selected pairs have duplicate participation")
        for field in ("title", "summary", "rationale"):
            if not isinstance(selected_pair.get(field), str) or not selected_pair[field].strip():
                raise ValueError("selected pair requires a nonempty {}".format(field))
        for identifier in key:
            if identifier not in tasks:
                raise ValueError("selected pair refers to an unknown task")
            if set(tasks[identifier]) - _TASK_FIELDS:
                raise ValueError("selected task has unsupported metadata")
        participating.update(key)
        normalized.append((key, selected_pair))
    if not normalized:
        return source, {str(identifier): identifier for identifier in sorted(tasks)}
    replacements = {}
    fused = {}
    for (first, second), selected_pair in normalized:
        left, right = tasks[first], tasks[second]
        fused[first] = {
            "id": first,
            "title": selected_pair["title"],
            "summary": selected_pair["summary"],
            "touches": _stable_union(left["touches"], right["touches"]),
            "acceptance": left["acceptance"] + right["acceptance"],
            "spec_refs": _stable_union(left["spec_refs"], right["spec_refs"]),
            "depends_on": [],
            "fused_from": [first, second],
        }
        replacements[first] = first
        replacements[second] = first
    for identifier in tasks:
        replacements.setdefault(identifier, identifier)
    contracted = {}
    for identifier in sorted(tasks):
        if identifier in participating and replacements[identifier] != identifier:
            continue
        value = fused.get(identifier, copy.deepcopy(tasks[identifier]))
        source_dependencies = []
        for source_id in ([identifier] if identifier not in fused else fused[identifier]["fused_from"]):
            source_dependencies.extend(tasks[source_id].get("depends_on", []))
        dependencies = _stable_union([replacements[dependency] for dependency in source_dependencies])
        value["depends_on"] = [dependency for dependency in dependencies if dependency != identifier]
        contracted[identifier] = value
    _topological_order(contracted)
    order = _topological_order(contracted)
    final_ids = {source_id: index + 1 for index, source_id in enumerate(order)}
    output_tasks = []
    for source_id in order:
        task = copy.deepcopy(contracted[source_id])
        task["id"] = final_ids[source_id]
        task["depends_on"] = sorted({final_ids[dependency] for dependency in task["depends_on"]})
        output_tasks.append(task)
    output = copy.deepcopy(source)
    output["tasks"] = output_tasks
    output["source_draft_hash"] = plan_hash(source)
    source_id_map = {str(source_id): final_ids[replacements[source_id]] for source_id in sorted(tasks)}
    output["source_id_map"] = source_id_map
    validate_plan({**output, "tasks": [
        {key: value for key, value in task.items() if key != "fused_from"} for task in output_tasks
    ]})
    return output, source_id_map
