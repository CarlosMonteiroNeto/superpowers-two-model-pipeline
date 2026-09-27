"""Candidate-bound reviewer dispatch and recoverable review-pending state."""
import copy
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import codex_dispatch
import codex_sessions
import dispatch_contract


def _semantic(value):
    # Reuse the canonical strict schema validator used at the transport seam.
    return dispatch_contract._validate_reviewer(value)


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
    semantic = _semantic(result.get("final_output"))
    # A full normalized dispatch result gets all transport/hash checks too.
    if set(dispatch_contract.RESULT_FIELDS).issubset(result):
        req = {k: v for k, v in request.items() if k in dispatch_contract.REQUEST_FIELDS}
        req.setdefault("role", "reviewer")
        result = dispatch_contract.validate_result(result, req)
        semantic = result["final_output"]
    return semantic


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
        result = codex_dispatch.run_dispatch(req, dispatch_runtime)
        semantic = _validated_result(result, req)
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
