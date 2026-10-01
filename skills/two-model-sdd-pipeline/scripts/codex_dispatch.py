"""Native Codex CLI dispatch with strict transport and semantic validation."""
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import uuid
import datetime
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import dispatch_contract
import codex_process
import codex_sessions
import codex_policy
import run_control


def ledger_append_argv(script, args, platform=None):
    """Build a native argv for the Bash-owned ledger writer."""
    if not isinstance(script, str) or not script or not isinstance(args, (list, tuple)):
        raise ValueError("ledger script and argument list are required")
    if not all(isinstance(value, str) for value in args):
        raise ValueError("ledger arguments must be strings")
    runtime_platform = os.name if platform is None else platform
    prefix = ["bash", script] if runtime_platform == "nt" else [script]
    return prefix + list(args)


def ledger_append_script(script_dir):
    """Return the packaged ledger writer path independent of caller cwd."""
    return str(pathlib.Path(script_dir).resolve() / "ledger-append")


def _atomic(path, content):
    p = pathlib.Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_name(p.name + "." + uuid.uuid4().hex + ".tmp")
    if isinstance(content, bytes): t.write_bytes(content)
    else: t.write_text(content, encoding="utf-8")
    os.replace(str(t), str(p))


def _json(path, value): _atomic(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def _protected_artifacts(request, attempt_dir):
    folder=pathlib.Path(attempt_dir)
    return {"before":folder/"protected-before.json",
            "after":folder/"protected-after.json",
            "comparison":folder/"protected-comparison.json"}


def _record_protected_after(request, policy, artifacts, before):
    protected_request={"workspace_root":policy["workspace_root"],
        "task_id":request["task_id"],"attempt_id":request["dispatch_id"],
        "protected_paths":policy["protected_paths"]}
    after=codex_policy.capture_protected_state(protected_request)
    comparison=codex_policy.compare_protected_state(before,after)
    _json(str(artifacts["after"]),after)
    _json(str(artifacts["comparison"]),comparison)
    return comparison


def publish_requested_result(request, result):
    """Publish normalized output at the result path bound into the request."""
    path = request.get("evidence_paths", {}).get("result_path")
    if not isinstance(path, str) or not path:
        raise ValueError("requested result path is missing")
    _json(path, result)


def publish_operator_session_locator(workspace, task_id, agent, result):
    """Atomically publish the completed operator session ID as a locator.

    Resume authorization and identity checks remain in run_dispatch; this file
    only helps the same task's correction caller find that validated session.
    """
    if (not isinstance(result, dict) or result.get("terminal_status") != "completed"
            or not isinstance(result.get("session_id"), str) or not result["session_id"]):
        raise ValueError("completed operator result with session ID is required")
    if (not isinstance(agent, str)
            or re.fullmatch(r"two-model-coder(?:-[A-Za-z0-9_]+)*", agent) is None
            or not str(task_id).isdigit()):
        raise ValueError("operator locator identity is invalid")
    target = pathlib.Path(workspace) / ("task-%s-%s-session.txt" % (task_id, agent))
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(result["session_id"] + "\n", encoding="utf-8")
    os.replace(str(temporary), str(target))
    return target


def _package_envelope_path(prompt_path):
    return str(pathlib.Path(prompt_path).parent / "envelope.json")


def _verify_package_envelope(prompt_path, prompt_hash):
    """Cross-check the prepare() envelope sibling when the caller used it.

    Returns the verified package envelope, or None for legacy callers that
    only carry prompt bytes. A present-but-divergent envelope fails closed:
    altered bytes must never reach a worker.
    """
    sidecar = pathlib.Path(prompt_path).parent / "envelope.json"
    if not sidecar.is_file():
        return None
    try:
        envelope = json.loads(sidecar.read_text(encoding="utf-8"))
    except ValueError:
        raise ValueError("prompt envelope is not valid JSON")
    if not isinstance(envelope, dict):
        raise ValueError("prompt envelope is not valid JSON")
    if envelope.get("prompt_sha256") != prompt_hash:
        raise ValueError("prompt envelope does not match prompt bytes")
    channels = envelope.get("channels")
    if not isinstance(channels, list) or not channels:
        raise ValueError("prompt envelope has no channels")
    canonical = {"role": envelope.get("role"),
                 "prompt_sha256": envelope.get("prompt_sha256"),
                 "policy_sha256": envelope.get("policy_sha256"),
                 "channels": channels}
    recomputed = hashlib.sha256(json.dumps(
        canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if recomputed != envelope.get("instruction_envelope_hash"):
        raise ValueError("prompt envelope hash mismatch")
    return envelope


def _submission_envelope(role, prompt_hash, package_envelope, prefix_bytes,
                         prefix_source, developer_instructions, resume_id,
                         submitted_sha):
    """Describe every submitted instruction channel with digests."""
    channels = [{"name": "prepared_prompt", "sha256": prompt_hash},
                {"name": "role_instruction", "source": prefix_source,
                 "sha256": hashlib.sha256(prefix_bytes).hexdigest()}]
    if isinstance(developer_instructions, str) and developer_instructions:
        channels.append({"name": "developer_instructions",
                         "sha256": hashlib.sha256(
                             developer_instructions.encode("utf-8")).hexdigest()})
    resume = None
    if isinstance(resume_id, str) and resume_id:
        resume = {"resumed_from": resume_id, "package_sha256": prompt_hash}
    body = {"role": role, "prompt_sha256": prompt_hash,
            "channels": channels, "resume": resume,
            "submitted_stdin_sha256": submitted_sha}
    body["instruction_envelope_hash"] = hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    body["prepared_envelope_hash"] = (package_envelope or {}).get(
        "instruction_envelope_hash")
    return body


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


def _structured_schema_path(request, runtime):
    configured = runtime.get("schema_path")
    if configured:
        return configured
    schemas = pathlib.Path(__file__).resolve().parent.parent / "schemas"
    if request["role"] == "director":
        episode = request.get("episode_id", "")
        if "-closing-" in episode:
            name = "closing-result.schema.json"
        elif "-arbitration" in episode:
            name = "director-arbitration.schema.json"
        else:
            name = "director-result.schema.json"
        return str(schemas / name)
    schema_name = {"operator-result-v1":"operator-result.schema.json",
                   "reviewer-result-v1":"reviewer-result.schema.json"}[_output_schema(request, runtime)]
    return str(schemas / schema_name)


def normalized_output_and_hash(role, payload, output_schema):
    normalized=dispatch_contract._validate_semantic(role,payload,output_schema)
    digest=hashlib.sha256(json.dumps(normalized,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")).hexdigest()
    return normalized,digest


def _worker_environment(runtime):
    """Build the model process environment without supervisor cache access."""
    env = dict(os.environ)
    if isinstance(runtime.get("env"), dict):
        env.update(runtime["env"])
    env.pop("PIPELINE_IMPACT_CACHE_ROOT", None)
    env.pop("PIPELINE_SCOPE_GRANT_KEY", None)
    return env


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
    package_envelope = _verify_package_envelope(prompt_path, req["prompt_hash"])
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
    role_instruction=runtime.get("role_instructions",{}).get(req["role"],"")
    if not role_instruction:
        role_file=pathlib.Path(__file__).resolve().parent.parent/"codex"/(req["role"]+".md")
        role_instruction=role_file.read_text(encoding="utf-8") if role_file.is_file() else ""
    if not isinstance(role_instruction,str) or not role_instruction.strip(): raise ValueError("packaged role instructions are missing")
    prefix_source = "runtime" if runtime.get("role_instructions",{}).get(req["role"]) else "codex/%s.md" % req["role"]
    prefix_bytes = (role_instruction.rstrip()+"\n\n").encode("utf-8")
    prompt=role_instruction.rstrip()+"\n\n"+prompt
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
    requested_root.mkdir(parents=True, exist_ok=True)
    attempt_dir = requested_root / ("attempt-" + req["dispatch_id"] + "-" + uuid.uuid4().hex)
    attempt_dir.mkdir(parents=True, exist_ok=False)
    policy_path=attempt_dir/"policy.json"
    policy=codex_policy.build_attempt_policy(req,runtime)
    _json(str(policy_path),policy)
    submitted_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    attempt_envelope = _submission_envelope(
        req["role"], req["prompt_hash"], package_envelope, prefix_bytes,
        prefix_source, runtime.get("developer_instructions"), resume_id,
        submitted_sha)
    prepared_text = pathlib.Path(ep["prompt_path"]).read_text(encoding="utf-8")
    if hashlib.sha256(prefix_bytes + prepared_text.encode("utf-8")).hexdigest() != submitted_sha:
        raise ValueError("submitted prompt does not match recorded channels")
    _json(str(attempt_dir/"envelope.json"), attempt_envelope)
    protected_artifacts=None
    protected_before=None
    if req["role"]=="operator":
        protected_artifacts=_protected_artifacts(req,attempt_dir)
        protected_request={"workspace_root":policy["workspace_root"],
            "task_id":req["task_id"],"attempt_id":req["dispatch_id"],
            "protected_paths":policy["protected_paths"]}
        protected_before=codex_policy.capture_protected_state(protected_request)
        _json(str(protected_artifacts["before"]),protected_before)
    for key, name in (("request_path", "request.json"), ("events_path", "events.jsonl"),
                      ("stderr_path", "stderr.log"), ("final_path", "final.json"),
                      ("result_path", "result.json")):
        ep[key] = str(attempt_dir / name)
    out_path = pathlib.Path(ep["final_path"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists(): out_path.unlink()
    args = list(executable) + overrides + ["exec"]
    if resume_id: args += ["resume", resume_id]
    schema_path = _structured_schema_path(req, runtime)
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
        control_path=runtime.get("process_registry_path")
        if control_path:
            run_control.register_process(control_path,req["run_id"],record)
        callback = runtime.get("on_process_start")
        if callback is not None:
            if not callable(callback): raise ValueError("on_process_start must be callable")
            callback(dict(record))
    lifecycle = {"session_id":resume_id, "status":"active", "started_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 "evidence_dir":str(attempt_dir), "context_reset":context_reset, "runtime_version":str(manifest.get("version", "unknown"))}
    codex_sessions.store_session(identity, lifecycle)
    try:
        env=_worker_environment(runtime)
        env["PIPELINE_ROLE_POLICY"]=str(policy_path)
        env["CODEX_SKILL_ROOT"]=str(pathlib.Path(__file__).resolve().parent.parent)
        captured = codex_process.run_owned(args, cwd, prompt, runtime.get("timeout"), env, on_start=register_process)
        if active_process and runtime.get("process_registry_path"):
            run_control.mark_process(runtime["process_registry_path"],req["run_id"],active_process[0],
                "completed" if captured["returncode"]==0 and not captured.get("timed_out") else "failed")
    except codex_process.ProcessLaunchError:
        lifecycle.update(status="preexec_failed", error="Codex executable could not be started")
        codex_sessions.store_session(identity, lifecycle)
        raise
    except Exception:
        if protected_artifacts is not None:
            try: _record_protected_after(req,policy,protected_artifacts,protected_before)
            except Exception: pass
        if active_process and runtime.get("process_registry_path"):
            try: run_control.mark_process(runtime["process_registry_path"],req["run_id"],active_process[0],"interrupted")
            except Exception: pass
        lifecycle.update(status="unresolved", error="process start/capture did not complete")
        codex_sessions.store_session(identity, lifecycle)
        raise
    _atomic(ep["events_path"], captured["stdout"])
    _atomic(ep["stderr_path"], captured["stderr"])
    _json(ep["request_path"], req)
    if protected_artifacts is not None:
        comparison=_record_protected_after(req,policy,protected_artifacts,protected_before)
        if not comparison["integrity_ok"]:
            changed=", ".join(comparison["changed_protected_paths"])
            if comparison["git_head_changed"]: changed=(changed+", " if changed else "")+"HEAD"
            raise ValueError("operator changed protected state: " + changed)
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
    final,payload_hash = normalized_output_and_hash(req["role"],final,schema)
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
