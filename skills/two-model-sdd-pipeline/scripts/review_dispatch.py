"""Candidate-bound reviewer dispatch and recoverable review-pending state."""
import copy
import hashlib
import json
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import codex_dispatch
import codex_sessions
import dispatch_contract


def _sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def _family(plan, task_id):
    tasks = {str(item.get("id")): item for item in plan.get("tasks", [])}
    item = tasks.get(str(task_id))
    if item is None:
        raise ValueError("task is missing from canonical plan snapshot")
    seen = set()
    while item.get("corrects") is not None:
        parent = str(item["corrects"])
        if parent in seen or parent not in tasks:
            raise ValueError("invalid task correction-family chain")
        seen.add(parent)
        item = tasks[parent]
    return int(item["id"])


def build_request(workspace, task_id, output):
    """Construct the strict dispatch request from script-owned artifacts."""
    ws = pathlib.Path(workspace).resolve()
    state_path = ws / ("task-{}-review-state.json".format(task_id))
    plan_path = ws / "plan.json"
    package_path = ws / ("task-{}-review-package.diff".format(task_id))
    identity_path = ws / ".pipeline-identity.json"
    runtime_path = os.environ.get("CODEX_RUNTIME_JSON")
    for required in (state_path, plan_path, package_path, identity_path):
        if not required.is_file():
            raise ValueError("required review artifact is missing: {}".format(required))
    if not runtime_path or not pathlib.Path(runtime_path).is_file():
        raise ValueError("CODEX_RUNTIME_JSON must point to the selected Codex runtime envelope")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    runtime = json.loads(pathlib.Path(runtime_path).read_text(encoding="utf-8"))
    manifest = runtime.get("manifest", {})
    if manifest.get("backend") != "codex":
        raise ValueError("Codex review requires an explicitly selected Codex runtime")
    role = manifest.get("roles", {}).get("reviewer", {})
    config_hash = manifest.get("config_hash") or runtime.get("config_hash")
    if not config_hash or not role.get("model"):
        raise ValueError("Codex runtime is missing reviewer configuration identity")
    candidate = state.get("candidate_commit")
    base = state.get("base_commit")
    repository_root = pathlib.Path(subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], cwd=str(ws), text=True).strip()).resolve()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(repository_root), text=True).strip()
    if candidate != head or not base:
        raise ValueError("review candidate/base no longer matches committed attempt")
    task_family = _family(plan, task_id)
    run_id = identity.get("run_id")
    repository_id = identity.get("repository_id")
    if not run_id or not repository_id:
        raise ValueError("canonical pipeline identity is incomplete")
    plan_hash = _sha(plan_path)
    if state.get("plan_hash") and state["plan_hash"] != plan_hash:
        raise ValueError("review plan changed after candidate preparation")
    brief_path = ws / ("task-{}-brief.md".format(task_id))
    context_hash = hashlib.sha256((plan_hash + _sha(brief_path) + _sha(package_path)).encode()).hexdigest()
    if state.get("context_hash") and state["context_hash"] != context_hash:
        raise ValueError("review context differs from recorded candidate context")
    dispatch_id = hashlib.sha256("\0".join((run_id, str(task_id), candidate, context_hash)).encode()).hexdigest()[:32]
    evidence_root = ws / "attempts" / str(task_family) / "reviewer" / dispatch_id
    request = {
        "version": 1, "backend": "codex", "run_id": run_id,
        "dispatch_id": dispatch_id, "task_id": int(task_id),
        "task_family": task_family, "episode_id": "{}-family-{}".format(run_id, task_family),
        "role": "reviewer", "repository_id": repository_id,
        "worktree": str(repository_root), "plan_revision": plan_hash,
        "base_commit": base, "candidate_commit": candidate,
        "attempt_base": base, "context_hash": context_hash,
        "requested_model": role["model"],
        "requested_effort": role.get("settings", {}).get("model_reasoning_effort"),
        "config_hash": config_hash, "prompt_hash": _sha(package_path),
        "evidence_paths": {
            "request_path": str(evidence_root / "request.json"),
            "prompt_path": str(package_path),
            "events_path": str(evidence_root / "events.jsonl"),
            "stderr_path": str(evidence_root / "stderr.log"),
            "final_path": str(evidence_root / "final.json"),
            "result_path": str(evidence_root / "result.json"),
        },
        "review_state_path": str(state_path),
    }
    dispatch_contract.validate_request({k: v for k, v in request.items()
                                       if k in dispatch_contract.REQUEST_FIELDS})
    target = pathlib.Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(target)
    return request


def load_review_result(request):
    path = request.get("result_path") or request.get("review_result_path")
    if not path:
        return None
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _matches(result, request):
    fields = ("role", "run_id", "task_id", "task_family", "base_commit", "candidate_commit")
    return isinstance(result, dict) and all(result.get(k) == request.get(k) for k in fields)


def _validated_result(result, request):
    if not _matches(result, request):
        raise ValueError("review result does not match current candidate identity")
    req = {k: v for k, v in request.items() if k in dispatch_contract.REQUEST_FIELDS}
    req.setdefault("role", "reviewer")
    clean_request = dispatch_contract.validate_request(req)
    # Every accepted result, including a cached/reused review, must satisfy the
    # complete normalized transport envelope and semantic schema. Matching
    # identity and a plausible verdict alone never constitute approval.
    clean_result = dispatch_contract.validate_result(result, clean_request)
    candidate = request.get("candidate_commit")
    attempt_base = request.get("attempt_base")
    if candidate is not None and clean_result["candidate_commit"] != candidate:
        raise ValueError("review result belongs to a stale candidate")
    if attempt_base is not None and clean_result["base_commit"] != attempt_base:
        raise ValueError("review result belongs to a stale attempt base")
    return clean_result["final_output"]


def ensure_review(request, runtime):
    """Return a matching reviewer verdict or dispatch exactly that review.

    A transport exception writes review_pending and is recoverable by calling
    this function again with the same request; the coder and candidate are not
    involved in that retry.
    """
    req = copy.deepcopy(request)
    req["role"] = "reviewer"
    previous = load_review_result(req)
    if _matches(previous, req):
        try:
            return _validated_result(previous, req)
        except (ValueError, KeyError):
            pass
    state_path = req.get("review_state_path")
    try:
        dispatch_runtime = dict(runtime)
        # Session identity is role- and family-scoped by the R2 adapter. Reuse
        # only the reviewer's own recorded session and always pass the newly
        # supplied complete package/request into that continuation.
        identity = {k: req[k] for k in ("backend", "run_id", "task_id", "task_family", "role",
                    "worktree", "requested_model", "requested_effort", "config_hash") if k in req}
        identity["session_dir"] = runtime.get("session_dir", req.get("worktree"))
        old_session = codex_sessions.load_session(identity)
        if old_session and old_session.get("session_id"):
            dispatch_runtime["resume"] = True
            dispatch_runtime["resume_session_id"] = old_session["session_id"]
        normalized_request = {k: v for k, v in req.items()
                              if k in dispatch_contract.REQUEST_FIELDS}
        result = codex_dispatch.run_dispatch(normalized_request, dispatch_runtime)
        semantic = _validated_result(result, req)
        normalized_result_path = req.get("normalized_result_path")
        if normalized_result_path:
            target = pathlib.Path(normalized_result_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(target.name + ".tmp")
            temp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temp.replace(target)
        if state_path:
            pathlib.Path(state_path).parent.mkdir(parents=True, exist_ok=True)
            pathlib.Path(state_path).write_text(json.dumps({"status": "completed", "identity": {
                k: req.get(k) for k in ("run_id", "task_id", "task_family", "base_commit", "candidate_commit")
            }, "result": result}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return semantic
    except Exception as exc:
        if state_path:
            pathlib.Path(state_path).parent.mkdir(parents=True, exist_ok=True)
            pathlib.Path(state_path).write_text(json.dumps({"status": "review_pending", "identity": {
                k: req.get(k) for k in ("run_id", "task_id", "task_family", "base_commit", "candidate_commit")
            }, "error": str(exc)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"status": "review_pending", "candidate_commit": req.get("candidate_commit"), "error": str(exc)}
