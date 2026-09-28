"""Run deterministic Codex pipeline acceptance fixtures and archive evidence."""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import time
import uuid


ROOT = pathlib.Path(__file__).resolve().parents[3]
TESTS = ROOT / "skills" / "two-model-sdd-pipeline" / "tests"
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"
SCENARIOS = {
    "artifact_handoff_and_preflight": [
        "test_codex_context_package", "test_codex_launcher",
    ],
    "operator_red_green_and_review": [
        "test_codex_gate_results", "test_codex_flutter_gate_results",
        "test_codex_review_recovery",
    ],
    "director_correction_and_arbitration": [
        "test_codex_director_proposals", "test_codex_corrective_families",
        "test_codex_plan_transactions",
    ],
    "parallel_integration_and_recovery": [
        "test_codex_multitoolchain_integration", "test_codex_worktree_lifecycle",
        "test_codex_run_identity",
    ],
    "strict_closing_and_publication": [
        "test_codex_closing_gate", "test_codex_publication",
    ],
    "resume_cancellation_and_retention": [
        "test_codex_resume_and_retry", "test_codex_process_ownership",
        "test_codex_runtime_review_fixes",
    ],
    "worker_policy_and_distribution": [
        "test_codex_dispatch", "test_codex_role_policy",
        "test_codex_scoped_runner", "test_codex_worker_instructions",
        "test_r2_packaged_workers", "test_codex_skill_entry_contract",
        "test_foundation_harness_install", "test_foundation_project_binding",
    ],
}


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()


def _source_identity():
    head = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain", "--untracked-files=all")
    digest = hashlib.sha256()
    diff = subprocess.run(
        ["git", "diff", "--binary", "HEAD"], cwd=ROOT,
        capture_output=True, check=True,
    )
    digest.update(diff.stdout)
    paths = _git("ls-files", "--others", "--exclude-standard").splitlines()
    for relative in sorted(paths):
        path = ROOT / relative
        if path.is_file():
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
    return {"commit": head, "working_tree_status": status, "source_sha256": digest.hexdigest()}


def _tool_version(name, args):
    executable = shutil.which(name)
    if not executable:
        return {"available": False, "version": None}
    try:
        result = subprocess.run(
            [executable, *args], cwd=ROOT, capture_output=True, text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"available": True, "version": "probe_failed"}
    output = (result.stdout or result.stderr).strip().splitlines()
    return {
        "available": result.returncode == 0,
        "version": output[0][:240] if output else "probe_failed",
    }


def _scenario_environment():
    """Keep host Python import paths out of Git Bash/native subprocesses.

    Tests import scripts from their test process explicitly. Passing a native
    Windows PYTHONPATH into a Bash wrapper that appends POSIX paths creates a
    mixed-separator value that Python on Windows cannot reliably parse.
    """
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    return environment


def _bind_live_paths(runtime, run_dir, workspace):
    """Place bulky live evidence at shallow report-relative paths for Windows."""
    runtime.update(
        attempt_root=str(pathlib.Path(run_dir) / "attempts"),
        session_dir=str(pathlib.Path(run_dir) / "sessions"),
        process_registry_path=str(pathlib.Path(workspace) / "process-registry.json"),
    )
    return runtime


def _validate_live_role_result(role, result, resumed=False):
    if result.get("terminal_status") != "completed":
        raise ValueError("live %s transport did not complete" % role)
    output = result.get("final_output")
    if not isinstance(output, dict):
        raise ValueError("live %s returned no structured result" % role)
    expected = {
        "operator": "BLOCKED" if resumed else "DONE",
        "reviewer": "SEND_BACK",
        "director": "BLOCKED",
    }.get(role)
    key = "status" if role == "operator" else "verdict"
    if output.get(key) != expected:
        raise ValueError("live %s expected %s, got %r" % (role, expected, output.get(key)))
    if role == "operator" and not resumed and output.get("concerns"):
        raise ValueError("live operator DONE probe must not carry concerns")
    return expected


def _run_scenario(name, modules, run_dir):
    missing = [module for module in modules if not (TESTS / (module + ".py")).is_file()]
    if missing:
        return {"name": name, "status": "blocked", "missing_modules": missing}
    log_name = name + ".log"
    command = [sys.executable, "-m", "unittest", *modules, "-v"]
    started = time.monotonic()
    result = subprocess.run(
        command, cwd=TESTS, capture_output=True, text=True,
        env=_scenario_environment(),
    )
    elapsed = round(time.monotonic() - started, 3)
    log_path = run_dir / log_name
    log_path.write_text(result.stdout + result.stderr, encoding="utf-8")
    match = re.search(r"Ran (\d+) tests? in ([0-9.]+)s", result.stdout + result.stderr)
    return {
        "name": name,
        "status": "passed" if result.returncode == 0 and match else "failed",
        "exit_code": result.returncode,
        "tests_run": int(match.group(1)) if match else 0,
        "duration_seconds": elapsed,
        "command": command,
        "log": log_name,
    }


def _new_run_dir(output):
    output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = output / ("codex-acceptance-" + stamp + "-" + uuid.uuid4().hex[:8])
    candidate.mkdir()
    return candidate


def _run_live_role_probes(config_path, run_dir, hooks_trusted, policy_clean):
    sys.path.insert(0, str(SCRIPTS))
    import codex_dispatch
    import codex_launcher
    import pipeline_config

    config = pipeline_config.load_runtime(str(config_path))
    if config["backend"] != "codex":
        raise ValueError("live acceptance requires backend=codex")
    if config["publication"] != "local":
        raise ValueError("live acceptance requires publication=local")
    if config.get("confirmation", {}).get("confirmed") is not True:
        raise ValueError("live acceptance requires confirmed model/policy configuration")
    role_pairs = {
        (item["model"], item["settings"]["model_reasoning_effort"])
        for item in config["roles"].values()
    }
    if len(role_pairs) != 1:
        raise ValueError("live acceptance requires the same confirmed model and effort for every role")

    project = run_dir / "live-project"
    workspace = project / ".acceptance"
    workspace.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "Codex Acceptance"], check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "codex-acceptance@example.invalid"], check=True)
    (project / "README.md").write_text("Disposable Codex role probe.\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(project), "commit", "-qm", "fixture: start Codex acceptance"], check=True)
    base_commit = subprocess.check_output(["git", "-C", str(project), "rev-parse", "HEAD"], text=True).strip()
    task_plan = {
        "version": 1,
        "title": "Disposable Codex role probe",
        "tasks": [{"id": 1, "title": "Read-only role probe", "touches": ["probe.txt"],
                   "verification": {"new_test_files": []}}],
        "verification": {"toolchains": []},
    }
    plan_bytes = (json.dumps(task_plan, sort_keys=True, separators=(",", ":")) + "\n").encode()
    plan_path = workspace / "plan.json"
    plan_path.write_bytes(plan_bytes)
    plan_hash = hashlib.sha256(plan_bytes).hexdigest()
    run_id = uuid.uuid4().hex
    config_hash = pipeline_config.configuration_hash(config)
    doctor = codex_launcher._doctor(config_path, project, workspace)
    runtime = codex_launcher._compose_runtime(
        config, doctor, project, workspace, workspace / "process-registry.json",
        run_id, hooks_trusted, base_commit, "main",
    )
    if not policy_clean:
        raise ValueError("Codex managed policy and inherited instructions must be confirmed clean")
    _bind_live_paths(runtime, run_dir, workspace)
    prompts = {
        "operator": (
            "This is a live sandbox acceptance probe in a disposable repository. Create "
            "only probe.txt at the repository root with the exact text "
            "'codex-live-acceptance-ok'. Do not run commands or change any other path. "
            "Return a valid operator result with status DONE, summary 'live sandbox probe "
            "completed', changed_files ['probe.txt'], red_evidence {path:'not-applicable', "
            "runner:'sandbox-probe', exit_code:0}, and an empty concerns array. The summary "
            "must state that this is not a product task and no RED/GREEN approval is implied. "
            "Use JSON strings and keys exactly as required by the supplied output schema."
        ),
        "reviewer": (
            "This is a live acceptance transport probe, not a code review. Do not run "
            "commands or approve any branch. Return a valid reviewer result with verdict "
            "SEND_BACK, findings containing one Minor finding with all required fields "
            "(file 'probe.txt', line 0, correction_scope 'uncertain', affected_paths "
            "['probe.txt'], affected_contracts ['acceptance-probe']), empty minors, and "
            "a short summary. Use the supplied JSON output schema exactly."
        ),
        "director": (
            "This is a live acceptance transport probe, not a closing approval. Do not "
            "run commands or approve publication. Return a valid closing result with "
            "verdict BLOCKED, summary 'live role transport probe only', and empty findings, "
            "parked_minors, and proposed_tasks."
        ),
    }
    results = []
    for role in ("operator", "reviewer", "director"):
        prompt_path = workspace / (role + "-prompt.md")
        prompt_path.write_text(prompts[role], encoding="utf-8")
        evidence = {key: str(workspace / (role + "-" + key)) for key in (
            "request_path", "events_path", "stderr_path", "final_path", "result_path",
        )}
        evidence["prompt_path"] = str(prompt_path)
        request = {
            "version": 1, "backend": "codex", "run_id": run_id,
            "dispatch_id": uuid.uuid4().hex, "task_id": 1, "task_family": 1,
            "episode_id": "live-acceptance-" + role + ("-closing-" if role == "director" else ""),
            "role": role, "repository_id": hashlib.sha256(str(project).encode()).hexdigest(),
            "worktree": str(project), "plan_revision": plan_hash,
            "base_commit": base_commit, "config_hash": config_hash,
            "prompt_hash": hashlib.sha256(prompts[role].encode("utf-8")).hexdigest(),
            "requested_model": config["roles"][role]["model"],
            "requested_effort": config["roles"][role]["settings"]["model_reasoning_effort"],
            "evidence_paths": evidence,
        }
        result = codex_dispatch.run_dispatch(request, runtime)
        semantic = _validate_live_role_result(role, result)
        outcome = {
            "role": role, "status": result["terminal_status"],
            "schema": result["output_schema"], "semantic_result": semantic,
            "model": result["requested_model"],
            "reasoning_effort": result["requested_effort"],
        }
        if role == "operator":
            probe_file = project / "probe.txt"
            if not probe_file.is_file() or probe_file.read_text(encoding="utf-8").strip() != "codex-live-acceptance-ok":
                raise ValueError("operator did not create the single declared live sandbox probe file")
            resume_path = workspace / "operator-resume.md"
            resume_text = (
                "This is a resume-only live acceptance probe. Do not edit files, run "
                "commands, or claim product work. Return a valid operator result with "
                "status BLOCKED, summary 'explicit session resume verified', empty "
                "changed_files, red_evidence {path:'not-applicable', runner:'sandbox-probe', "
                "exit_code:0}, and a concern that no product task was run. Use the supplied "
                "JSON output schema exactly."
            )
            resume_path.write_text(resume_text, encoding="utf-8")
            resume_request = dict(
                request,
                dispatch_id=uuid.uuid4().hex,
                prompt_hash=hashlib.sha256(resume_text.encode("utf-8")).hexdigest(),
            )
            resume_request["evidence_paths"] = dict(evidence, prompt_path=str(resume_path))
            runtime["resume"] = True
            runtime["resume_session_id"] = result["session_id"]
            resumed = codex_dispatch.run_dispatch(resume_request, runtime)
            runtime.pop("resume", None)
            runtime.pop("resume_session_id", None)
            _validate_live_role_result("operator", resumed, resumed=True)
            outcome["explicit_session_resume"] = (
                resumed["session_id"] == result["session_id"]
                and resumed["resumed_from"] == result["session_id"]
            )
            if not outcome["explicit_session_resume"]:
                raise ValueError("operator resume did not preserve the explicit session identity")
        results.append(outcome)
    return {
        "status": "passed" if all(item["status"] == "completed" for item in results)
                            and results[0].get("explicit_session_resume") else "failed",
        "model": next(iter(role_pairs))[0],
        "reasoning_effort": next(iter(role_pairs))[1],
        "roles": results,
        "evidence_directory": str(workspace),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run offline Codex pipeline fixtures and preserve candidate-bound evidence."
    )
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), action="append")
    parser.add_argument("--list-scenarios", action="store_true")
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--confirm-hooks-trusted", action="store_true")
    parser.add_argument("--confirm-policy-clean", action="store_true")
    args = parser.parse_args(argv)
    if args.list_scenarios:
        print(json.dumps(SCENARIOS, sort_keys=True, indent=2))
        return 0
    if args.output is None:
        parser.error("--output is required")
    if args.live and args.config is None:
        parser.error("--config is required with --live")
    if args.live:
        if not args.confirm_hooks_trusted or not args.confirm_policy_clean:
            parser.error("--live requires --confirm-hooks-trusted and --confirm-policy-clean")

    selected = args.scenario or list(SCENARIOS)
    run_dir = _new_run_dir(args.output.resolve())
    identity = _source_identity()
    results = [_run_scenario(name, SCENARIOS[name], run_dir) for name in selected]
    tools = {
        "git": _tool_version("git", ["--version"]),
        "codex": _tool_version("codex", ["--version"]),
        "opencode": _tool_version("opencode", ["--version"]),
    }
    live_result = None
    if args.live:
        try:
            live_result = _run_live_role_probes(
                args.config.resolve(), run_dir, args.confirm_hooks_trusted,
                args.confirm_policy_clean,
            )
        except Exception as exc:
            live_result = {"status": "failed", "error": str(exc)}
    report = {
        "schema_version": 1,
        "mode": "offline+live" if args.live else "offline",
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "candidate_commit": identity["commit"],
        "source_sha256": identity["source_sha256"],
        "working_tree_status": identity["working_tree_status"],
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "tools": tools,
        },
        "live_validation": live_result["status"] if live_result else "not_run",
        "live_probe": live_result,
        "scenarios": results,
        "result": "passed" if all(item["status"] == "passed" for item in results)
                              and (live_result is None or live_result.get("status") == "passed") else "failed",
    }
    report_path = run_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(str(report_path))
    return 0 if report["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
