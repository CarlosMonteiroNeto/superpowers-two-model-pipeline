"""Strict validation for the semantic director proposal contract."""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import dispatch_contract


def validate_proposal(value: dict, expected: dict) -> dict:
    """Validate proposal schema and bind it to the requested episode/plan."""
    if not isinstance(expected, dict):
        raise ValueError("expected director identity must be an object")
    result = dispatch_contract._validate_director_proposal(value)
    for key in ("mode", "source_plan_hash", "target_task"):
        if key in expected and result.get(key) != expected[key]:
            raise ValueError("director proposal {} does not match current request".format(key))
    return result


def build_request(workspace: str, task_id: int, mode: str, prompt_path: str, output_path: str) -> dict:
    """Build a strict fresh director dispatch request from owned artifacts."""
    ws = pathlib.Path(workspace).resolve()
    prompt = pathlib.Path(prompt_path).resolve()
    identity_path = ws / ".pipeline-identity.json"
    plan_path = ws / "plan.json"
    runtime_path = os.environ.get("CODEX_RUNTIME_JSON")
    for path in (identity_path, plan_path, prompt):
        if not path.is_file():
            raise ValueError("required director artifact is missing: {}".format(path))
    if not runtime_path or not pathlib.Path(runtime_path).is_file():
        raise ValueError("CODEX_RUNTIME_JSON is required for director dispatch")
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    runtime = json.loads(pathlib.Path(runtime_path).read_text(encoding="utf-8"))
    manifest = runtime.get("manifest", {})
    role = manifest.get("roles", {}).get("director", {})
    if manifest.get("backend") != "codex" or not role.get("model"):
        raise ValueError("selected runtime has no Codex director role")
    if mode not in ("correction", "arbitration"):
        raise ValueError("unsupported director proposal mode")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    tasks = {str(task.get("id")): task for task in plan.get("tasks", [])}
    task = tasks.get(str(task_id))
    if task is None:
        raise ValueError("target task is missing from current plan")
    family = task
    seen = set()
    while family.get("corrects") is not None:
        parent = str(family["corrects"])
        if parent in seen or parent not in tasks:
            raise ValueError("invalid correction family chain")
        seen.add(parent); family = tasks[parent]
    root = pathlib.Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"],
        cwd=str(ws), text=True).strip()).resolve()
    plan_bytes = plan_path.read_bytes()
    plan_hash = hashlib.sha256(plan_bytes).hexdigest()
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(root), text=True).strip()
    run_id = identity.get("run_id"); repository_id = identity.get("repository_id")
    config_hash = manifest.get("config_hash") or runtime.get("config_hash")
    if not run_id or not repository_id or not config_hash:
        raise ValueError("pipeline identity/runtime config hash is incomplete")
    original_prompt = prompt.read_text(encoding="utf-8")
    context = [original_prompt, "\n\nIMPORTANT: use the full current snapshot below; it supersedes any earlier plan path or target excerpt.\n",
        "## Scope rules\nNewly authored tests stay in verification.new_test_files. Keep touches for implementation paths. Never move a declared test path into touches to satisfy scope; doing so is invalid and will be rejected.\n",
        "## Current canonical plan snapshot (read-only)\n",
        "Snapshot SHA-256: {}\n".format(plan_hash),
        json.dumps(plan, ensure_ascii=False, indent=2),
        "\n## Current target task\n", json.dumps(task, ensure_ascii=False, indent=2)]
    review_path = ws / ("task-{}-review.json".format(task_id))
    if review_path.is_file():
        context.extend(["\n## Recorded review findings / escalation\n",
            review_path.read_text(encoding="utf-8")])
    materialized_prompt = pathlib.Path(output_path).with_suffix(".prompt.md")
    materialized_prompt.write_text("".join(context), encoding="utf-8")
    prompt = materialized_prompt
    # Hash the exact normalized UTF-8 text codex_dispatch reads on Windows;
    # raw bytes retain CRLF after write_text and would fail validation.
    prompt_hash = hashlib.sha256(prompt.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    episode_id = "{}-family-{}-{}".format(run_id, family["id"], mode)
    dispatch_id = hashlib.sha256("\0".join((episode_id, str(task_id), plan_hash, prompt_hash)).encode()).hexdigest()[:32]
    # Keep caller-bound artifacts close to the worktree root. On Windows the
    # full workspace/attempts/task/role/dispatch/result.tmp path can exceed
    # MAX_PATH even though Codex's own immutable attempt is stored elsewhere.
    evidence = pathlib.Path(runtime.get("attempt_root",str(root/".superpowers"/"codex"))) / "published" / ("director-"+dispatch_id)
    result_path = evidence / "result.json"
    request = {"version":1,"backend":"codex","run_id":run_id,"dispatch_id":dispatch_id,
        "task_id":int(task_id),"task_family":int(family["id"]),"episode_id":episode_id,
        "role":"director","repository_id":repository_id,"worktree":str(root),
        "plan_revision":plan_hash,"base_commit":base,"config_hash":config_hash,
        "prompt_hash":prompt_hash,"requested_model":role["model"],
        "requested_effort":role.get("settings",{}).get("model_reasoning_effort") or "medium",
        "evidence_paths":{"request_path":str(evidence/(dispatch_id+"-request.json")),"prompt_path":str(prompt),
            "events_path":str(evidence/"events.jsonl"),"stderr_path":str(evidence/"stderr.log"),
            "final_path":str(evidence/"final.json"),"result_path":str(result_path)}}
    dispatch_contract.validate_request(request)
    target = pathlib.Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix="director-request-", dir=str(target.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(request,stream,ensure_ascii=False,indent=2); stream.write("\n")
        os.replace(temp,target)
    finally:
        if os.path.exists(temp): os.unlink(temp)
    return request
