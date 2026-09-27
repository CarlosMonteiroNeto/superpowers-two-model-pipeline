"""Native Codex CLI dispatch with strict transport and semantic validation."""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import uuid
import datetime
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import dispatch_contract
import codex_process
import codex_sessions
import codex_policy


def _atomic(path, content):
    p = pathlib.Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_name(p.name + "." + uuid.uuid4().hex + ".tmp")
    if isinstance(content, bytes): t.write_bytes(content)
    else: t.write_text(content, encoding="utf-8")
    os.replace(str(t), str(p))


def _json(path, value): _atomic(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def _event_stream(raw):
    events = []
    for line in raw.splitlines():
        if not line.strip(): continue
        try: event = json.loads(line)
        except (ValueError, TypeError): raise ValueError("malformed Codex JSONL event")
        if not isinstance(event, dict) or not isinstance(event.get("type"), str): raise ValueError("malformed Codex event")
        kind = event["type"]
        if kind not in {"thread.started", "turn.started", "turn.completed", "turn.failed", "item.started", "item.updated", "item.completed", "error"}:
            raise ValueError("unknown Codex event: " + kind)
        events.append(event)
    return events


def _output_schema(request, runtime):
    if request["role"] == "director" and "-closing-" in request.get("episode_id", ""):
        return "closing-result-v1"
    return runtime.get("output_schema") or {"operator":"operator-result-v1", "reviewer":"reviewer-result-v1", "director":"director-result-v1"}[request["role"]]


def run_dispatch(request, runtime):
    req = dispatch_contract.validate_request(request)
    if req["backend"] != "codex": raise ValueError("Codex dispatch requires backend=codex")
    if not isinstance(runtime, dict): raise ValueError("runtime envelope required")
    manifest = runtime.get("manifest", {})
    if manifest.get("backend") != "codex": raise ValueError("Codex runtime manifest unavailable")
    executable = runtime.get("executable")
    if isinstance(executable, dict): executable = executable.get("argv") or executable.get("path")
    if isinstance(executable, str): executable = [executable]
    if not isinstance(executable, list) or not executable or not all(isinstance(v, str) and v for v in executable):
        raise ValueError("resolved Codex executable argv required")
    ep = dict(req["evidence_paths"])
    prompt_path = pathlib.Path(ep["prompt_path"])
    prompt = prompt_path.read_text(encoding="utf-8")
    if hashlib.sha256(prompt.encode("utf-8")).hexdigest() != req["prompt_hash"]:
        raise ValueError("prompt hash mismatch")
    capabilities = runtime.get("capabilities")
    if not isinstance(capabilities, dict): raise ValueError("Codex capability report required")
    role_config = manifest.get("roles", {}).get(req["role"], {})
    role_settings = role_config.get("settings", {}) if isinstance(role_config, dict) else {}
    if role_config.get("model") != req["requested_model"]:
        raise ValueError("requested model does not match role manifest")
    if role_settings.get("model_reasoning_effort") != req["requested_effort"]:
        raise ValueError("requested effort does not match role manifest")
    policy_request = {"developer_instructions": runtime.get("developer_instructions", ""), "capabilities": capabilities}
    overrides = codex_policy.build_overrides(req["role"], manifest, policy_request)
    resume_id = runtime.get("resume_session_id")
    recovery = runtime.get("recovery")
    if runtime.get("resume") and (not isinstance(resume_id, str) or not resume_id.strip()):
        raise ValueError("explicit resume session id required")
    if resume_id and not runtime.get("resume"):
        raise ValueError("session ID requires explicit identity-checked resume")
    identity = {k: req[k] for k in ("backend", "run_id", "task_id", "task_family", "role", "worktree", "requested_model", "requested_effort", "config_hash")}
    identity["session_dir"] = runtime.get("session_dir", req["worktree"])
    old = codex_sessions.load_session(identity) if runtime.get("resume") else None
    context_reset = False
    if runtime.get("resume"):
        if old is None and not recovery: raise ValueError("recorded session identity missing")
        if old and old.get("session_id") != resume_id: raise ValueError("session ID mismatch")
        if old is None and (not isinstance(recovery, dict) or recovery.get("fresh") is not True): raise ValueError("recovery must explicitly select fresh context")
        if old is None and isinstance(recovery, dict) and recovery.get("fresh") is True:
            context_reset = True
            resume_id = None
    # Evidence for each execution attempt is immutable and disjoint. Preserve
    # the caller's prompt source while placing generated artifacts together.
    requested_root = pathlib.Path(runtime.get("attempt_root") or pathlib.Path(ep["request_path"]).parent)
    attempt_dir = requested_root / ("attempt-" + req["dispatch_id"] + "-" + uuid.uuid4().hex)
    attempt_dir.mkdir(parents=True, exist_ok=False)
    for key, name in (("request_path", "request.json"), ("events_path", "events.jsonl"),
                      ("stderr_path", "stderr.log"), ("final_path", "final.json"),
                      ("result_path", "result.json")):
        ep[key] = str(attempt_dir / name)
    out_path = pathlib.Path(ep["final_path"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists(): out_path.unlink()
    args = list(executable) + overrides + ["exec"]
    if resume_id: args += ["resume", resume_id]
    schema_path = runtime.get("schema_path")
    if not schema_path:
        schema_name = {"operator-result-v1":"operator-result.schema.json", "reviewer-result-v1":"reviewer-result.schema.json", "director-result-v1":"director-result.schema.json", "closing-result-v1":"closing-result.schema.json"}[ _output_schema(req, runtime) ]
        schema_path = str(pathlib.Path(__file__).resolve().parent.parent / "schemas" / schema_name)
    args += ["--json", "--output-schema", str(schema_path), "--output-last-message", str(out_path), "-"]
    args = [a for a in args if a != ""]
    cwd = str(pathlib.Path(req["worktree"]).resolve())
    active_process = []
    def register_process(record):
        active_process[:] = [record]
        registry = runtime.get("process_registry")
        if registry is not None:
            if not isinstance(registry, list): raise ValueError("process_registry must be a list")
            registry.append(dict(record))
        callback = runtime.get("on_process_start")
        if callback is not None:
            if not callable(callback): raise ValueError("on_process_start must be callable")
            callback(dict(record))
    lifecycle = {"session_id":resume_id, "status":"active", "started_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 "evidence_dir":str(attempt_dir), "context_reset":context_reset, "runtime_version":str(manifest.get("version", "unknown"))}
    codex_sessions.store_session(identity, lifecycle)
    try:
        captured = codex_process.run_owned(args, cwd, prompt, runtime.get("timeout"), runtime.get("env"), on_start=register_process)
    except codex_process.ProcessLaunchError:
        lifecycle.update(status="preexec_failed", error="Codex executable could not be started")
        codex_sessions.store_session(identity, lifecycle)
        raise
    except Exception:
        lifecycle.update(status="unresolved", error="process start/capture did not complete")
        codex_sessions.store_session(identity, lifecycle)
        raise
    _atomic(ep["events_path"], captured["stdout"])
    _atomic(ep["stderr_path"], captured["stderr"])
    _json(ep["request_path"], req)
    if captured.get("timed_out"):
        lifecycle.update(status="unresolved", process_exit=124)
        codex_sessions.store_session(identity, lifecycle)
        raise TimeoutError("Codex dispatch timed out after process start")
    events = _event_stream(captured["stdout"])
    threads = [e.get("thread_id") for e in events if e["type"] == "thread.started"]
    completions = [e for e in events if e["type"] == "turn.completed"]
    failures = [e for e in events if e["type"] in ("turn.failed", "error")]
    if captured["returncode"] != 0 or failures or not completions or not threads:
        lifecycle.update(status="unresolved", process_exit=captured["returncode"])
        if threads and isinstance(threads[0], str): lifecycle["session_id"] = threads[0]
        codex_sessions.store_session(identity, lifecycle)
        raise ValueError("Codex transport did not complete successfully")
    session_id = threads[0]
    if not isinstance(session_id, str) or not session_id: raise ValueError("missing Codex thread identity")
    if resume_id and session_id != resume_id: raise ValueError("resumed Codex thread identity changed")
    if not out_path.is_file(): raise ValueError("Codex final output missing")
    final = json.loads(out_path.read_text(encoding="utf-8"))
    schema = _output_schema(req, runtime)
    payload_hash = hashlib.sha256(json.dumps(final, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, check=True)
    usage_event = completions[-1].get("usage", {})
    result = {k:req[k] for k in ("version","backend","run_id","dispatch_id","task_id","task_family","role","episode_id","repository_id","worktree","plan_revision","base_commit","requested_model","requested_effort","config_hash")}
    result.update(candidate_commit=git.stdout.strip(), runtime_version=str(manifest.get("version", "unknown")), session_id=session_id,
                  resumed_from=resume_id, process_exit=0, terminal_status="completed", output_schema=schema,
                  output_hash=payload_hash, final_output=final,
                  usage={"input_tokens":usage_event.get("input_tokens"), "cached_tokens":usage_event.get("cached_input_tokens"), "output_tokens":usage_event.get("output_tokens")}, error=None)
    validated = dispatch_contract.validate_result(result, req)
    _json(ep["result_path"], validated)
    codex_sessions.store_session(identity, {"session_id":session_id, "status":"completed", "completed_at":datetime.datetime.now(datetime.timezone.utc).isoformat(), "evidence_dir":str(attempt_dir), "context_reset":context_reset, "runtime_version":result["runtime_version"]})
    return validated
