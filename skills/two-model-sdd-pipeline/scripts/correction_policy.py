"""Script-owned decision for a validated semantic review correction."""

import pathlib
import json
import sys
import os
import importlib.util


_grant_spec = importlib.util.spec_from_file_location("scope_grants", pathlib.Path(__file__).with_name("scope_grants.py"))
scope_grants = importlib.util.module_from_spec(_grant_spec)
_grant_spec.loader.exec_module(scope_grants)


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


def decide(review: dict, task: dict, *, issued_grants=None, identity=None, grant_key=None) -> dict:
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
        # Plan fields are worker-readable and cannot issue new scope. Only a
        # supervisor record matching this run, family, task, and attempt may
        # extend it. A missing authoritative record grants nothing.
        if issued_grants is not None:
            if not isinstance(issued_grants, list) or not isinstance(identity, dict):
                raise ValueError("issued grants require an identity")
            for grant in issued_grants:
                if not isinstance(grant, dict):
                    raise ValueError("issued grant is malformed")
                if (not scope_grants.verify_issued(grant, grant_key) or
                        any(str(grant.get(key)) != str(identity.get(key)) for key in
                            ("run_id", "family_id", "task_id", "attempt_id")) or
                        not all(identity.get(key) for key in
                            ("run_id", "family_id", "task_id", "attempt_id"))):
                    continue
                approved_paths.update(_paths([grant["path"]]))
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
    if len(sys.argv) not in (4, 5):
        raise SystemExit("usage: correction_policy.py REVIEW.json PLAN.json TASK [WORKSPACE]")
    try:
        with open(sys.argv[1], encoding="utf-8") as handle:
            review = json.load(handle)
        with open(sys.argv[2], encoding="utf-8") as handle:
            plan = json.load(handle)
        task = next(t for t in plan["tasks"] if str(t["id"]) == sys.argv[3])
        grants = None
        grant_identity = None
        if len(sys.argv) == 5:
            ws = pathlib.Path(sys.argv[4])
            registry = ws / "scope-grants.json"
            if registry.is_file():
                records = json.loads(registry.read_text(encoding="utf-8"))
                if not isinstance(records, dict):
                    raise ValueError("scope grant registry is malformed")
                grants = list(records.values())
                run = json.loads((ws / ".pipeline-identity.json").read_text(encoding="utf-8"))
                state = json.loads((ws / ("task-{}-review-state.json".format(sys.argv[3]))).read_text(encoding="utf-8"))
                items = {str(t["id"]): t for t in plan["tasks"]}
                family = task
                seen = set()
                while family.get("corrects") is not None:
                    parent = str(family["corrects"])
                    if parent in seen or parent not in items:
                        raise ValueError("invalid task family")
                    seen.add(parent)
                    family = items[parent]
                grant_identity = {"run_id": run["run_id"], "family_id": family["id"],
                                  "task_id": task["id"], "attempt_id": state["candidate_commit"]}
        result = decide(review, task, issued_grants=grants, identity=grant_identity,
                        grant_key=os.environ.get("PIPELINE_SCOPE_GRANT_KEY"))
    except (OSError, ValueError, KeyError, StopIteration, TypeError) as exc:
        result = {"action": "block", "reason": str(exc)}
    print(result["action"])
