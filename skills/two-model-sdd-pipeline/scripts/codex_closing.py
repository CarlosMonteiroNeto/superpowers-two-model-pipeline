"""Candidate-bound Codex closing request and result validation."""
import hashlib
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import dispatch_contract


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def capture_snapshot(repository_root, plan_path, spec_path, ledger_path):
    root = pathlib.Path(repository_root).resolve()
    plan = pathlib.Path(plan_path).resolve()
    spec = pathlib.Path(spec_path).resolve() if spec_path else None
    ledger = pathlib.Path(ledger_path).resolve()
    if not plan.is_file() or not ledger.is_file():
        raise ValueError("canonical plan and run ledger must exist before closing")
    if spec and not spec.is_file():
        raise ValueError("canonical spec is missing")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(root), text=True).strip()
    return {"candidate_commit": head, "plan_hash": _sha(plan.read_bytes()),
        "spec_hash": _sha(spec.read_bytes()) if spec else _sha(b""),
        "ledger_revision": _sha(ledger.read_bytes())}


def validate_closing_result(result, snapshot, request):
    """Require a complete normalized result belonging to this exact snapshot."""
    if not isinstance(snapshot, dict) or set(snapshot) != {
            "candidate_commit", "plan_hash", "spec_hash", "ledger_revision"}:
        raise ValueError("closing snapshot is incomplete")
    clean = dispatch_contract.validate_result(result, request)
    if clean["backend"] != "codex" or clean["role"] != "director":
        raise ValueError("closing result must be from the Codex director")
    if clean["output_schema"] != "closing-result-v1":
        raise ValueError("closing result must use closing-result-v1")
    if clean["candidate_commit"] != snapshot["candidate_commit"]:
        raise ValueError("closing verdict belongs to a stale candidate commit")
    if clean["plan_revision"] != snapshot["plan_hash"]:
        raise ValueError("closing verdict belongs to a stale canonical plan")
    snapshot_hash = _sha(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode())
    expected_dispatch = _sha((clean["run_id"] + "\0closing\0" + snapshot_hash).encode())[:32]
    if clean["dispatch_id"] != expected_dispatch:
        raise ValueError("closing request is not bound to current plan/spec/ledger snapshot")
    return clean["final_output"]


def assert_candidate_current(repository_root, snapshot):
    head = subprocess.check_output(["git", "rev-parse", "HEAD"],
        cwd=str(pathlib.Path(repository_root).resolve()), text=True).strip()
    if head != snapshot["candidate_commit"]:
        raise ValueError("candidate changed after director closing; rerun closing")


def assert_snapshot_current(repository_root, plan_path, spec_path, ledger_path, snapshot):
    current = capture_snapshot(repository_root, plan_path, spec_path, ledger_path)
    if current != snapshot:
        raise ValueError("plan, spec, candidate, or ledger changed during closing")


def build_request(workspace, prompt_path, snapshot, output_path):
    ws = pathlib.Path(workspace).resolve()
    identity = json.loads((ws / ".pipeline-identity.json").read_text(encoding="utf-8"))
    runtime_path = pathlib.Path(__import__("os").environ["CODEX_RUNTIME_JSON"])
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    manifest = runtime.get("manifest", {})
    role = manifest.get("roles", {}).get("director", {})
    if manifest.get("backend") != "codex" or not role.get("model"):
        raise ValueError("Codex director role is not configured")
    prompt = pathlib.Path(prompt_path).resolve()
    if not prompt.is_file():
        raise ValueError("closing prompt is missing")
    run_id = identity["run_id"]
    snapshot_hash = _sha(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode())
    dispatch_id = _sha((run_id + "\0closing\0" + snapshot_hash).encode())[:32]
    root = pathlib.Path(identity["repository_root"]).resolve()
    config_hash = manifest.get("config_hash") or runtime.get("config_hash")
    if not config_hash:
        raise ValueError("Codex runtime config hash is missing")
    evidence = ws / "attempts" / "closing" / dispatch_id
    request = {"version":1,"backend":"codex","run_id":run_id,"dispatch_id":dispatch_id,
        "task_id":1,"task_family":1,"episode_id":run_id+"-closing-"+snapshot_hash[:16],
        "role":"director","repository_id":identity["repository_id"],"worktree":str(root),
        "plan_revision":snapshot["plan_hash"],"base_commit":snapshot["candidate_commit"],
        "config_hash":config_hash,"prompt_hash":_sha(prompt.read_bytes()),
        "requested_model":role["model"],"requested_effort":role.get("settings",{}).get("model_reasoning_effort") or "medium",
        "evidence_paths":{"request_path":str(evidence/"request.json"),"prompt_path":str(prompt),
          "events_path":str(evidence/"events.jsonl"),"stderr_path":str(evidence/"stderr.log"),
          "final_path":str(evidence/"final.json"),"result_path":str(evidence/"result.json")},
        }
    dispatch_contract.validate_request(request)
    target = pathlib.Path(output_path); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(request, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")
    return request
