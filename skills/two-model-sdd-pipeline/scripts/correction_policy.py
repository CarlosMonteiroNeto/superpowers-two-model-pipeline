"""Script-owned decision for a validated semantic review correction."""

import pathlib
import json
import sys


def _paths(values):
    if not isinstance(values, list) or not values:
        raise ValueError("affected paths must be a nonempty list")
    result = set()
    for value in values:
        if not isinstance(value, str) or not value or "\\" in value:
            raise ValueError("invalid affected path")
        path = pathlib.PurePosixPath(value)
        if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")) or ":" in value:
            raise ValueError("invalid affected path")
        result.add(value)
    return result


def _contracts(values):
    if not isinstance(values, list) or not values or not all(isinstance(x, str) and x.strip() for x in values):
        raise ValueError("affected contracts must be a nonempty list")
    return set(values)


def decide(review: dict, task: dict) -> dict:
    """Return coder, director, or block; fail closed on malformed metadata."""
    if not isinstance(review, dict) or not isinstance(task, dict):
        return {"action": "block", "reason": "review or task is malformed"}
    verdict = review.get("verdict")
    if verdict == "APPROVED":
        return {"action": "complete", "reason": "review approved"}
    if verdict == "ESCALATE":
        return {"action": "director", "reason": "review escalated"}
    if verdict != "SEND_BACK" or not isinstance(review.get("findings"), list) or not review["findings"]:
        return {"action": "block", "reason": "review verdict or findings are malformed"}
    try:
        approved_paths = _paths(task["touches"])
        approved_contracts = _contracts(task["acceptance"])
        grants = task.get("scope_grants", [])
        if not isinstance(grants, list):
            raise ValueError("scope grants are malformed")
        for grant in grants:
            if not isinstance(grant, dict):
                raise ValueError("scope grant is malformed")
            approved_paths.update(_paths(grant["paths"]))
            approved_contracts.update(_contracts(grant["contracts"]))
        checked = []
        for finding in review["findings"]:
            if not isinstance(finding, dict) or finding.get("correction_scope") not in ("in_scope", "structural", "uncertain"):
                raise ValueError("finding scope is malformed")
            paths = _paths(finding["affected_paths"])
            contracts = _contracts(finding["affected_contracts"])
            checked.append((finding["correction_scope"], paths, contracts))
        for scope, paths, contracts in checked:
            if scope != "in_scope":
                return {"action": "director", "reason": "structural or uncertain correction"}
            if not paths <= approved_paths or not contracts <= approved_contracts:
                return {"action": "director", "reason": "correction exceeds approved scope"}
    except (KeyError, ValueError) as exc:
        return {"action": "block", "reason": str(exc)}
    return {"action": "coder", "reason": "correction fits approved task scope"}


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: correction_policy.py REVIEW.json PLAN.json TASK")
    try:
        with open(sys.argv[1], encoding="utf-8") as handle:
            review = json.load(handle)
        with open(sys.argv[2], encoding="utf-8") as handle:
            plan = json.load(handle)
        task = next(t for t in plan["tasks"] if str(t["id"]) == sys.argv[3])
        result = decide(review, task)
    except (OSError, ValueError, KeyError, StopIteration, TypeError) as exc:
        result = {"action": "block", "reason": str(exc)}
    print(result["action"])
