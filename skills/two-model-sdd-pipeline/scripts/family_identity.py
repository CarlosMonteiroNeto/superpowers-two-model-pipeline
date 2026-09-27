"""Correction-family identity helpers shared by dispatch and resume paths."""
import json
import pathlib
import sys


def resolve_family(plan, task_id):
    tasks=plan.get("tasks",[]) if isinstance(plan,dict) else []
    by_id={str(task.get("id")):task for task in tasks}
    key=str(task_id)
    if key not in by_id: raise ValueError("task is missing from canonical plan")
    chain=[]; seen=set(); current=by_id[key]
    while True:
        current_id=str(current["id"])
        if current_id in seen: raise ValueError("correction-family cycle")
        seen.add(current_id); chain.append(int(current["id"]))
        parent=current.get("corrects")
        if parent is None: return {"root":int(current["id"]),"chain":chain}
        if str(parent) not in by_id: raise ValueError("correction-family parent is missing")
        current=by_id[str(parent)]


def is_descendant(plan, child_id, parent_id):
    chain=resolve_family(plan,child_id)["chain"]
    return int(parent_id) in chain[1:]


if __name__ == "__main__":
    if len(sys.argv)!=5 or sys.argv[1]!="--is-descendant":
        print("usage: family_identity.py --is-descendant PLAN CHILD PARENT",file=sys.stderr); raise SystemExit(2)
    plan=json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
    raise SystemExit(0 if is_descendant(plan,int(sys.argv[3]),int(sys.argv[4])) else 1)
