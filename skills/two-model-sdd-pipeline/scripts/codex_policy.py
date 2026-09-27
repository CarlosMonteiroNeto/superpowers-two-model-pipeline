"""Attempt-bound Codex invocation settings and PreToolUse policy checks."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shlex
import subprocess


class PolicyUnavailable(ValueError):
    """Raised when a requested role cannot be safely enforced."""


ROLES = {"operator", "reviewer", "director"}
CAPABILITY_FLAGS = ("hooks_enabled", "hooks_trusted", "sandbox_enforced",
                    "bash_hook_covered", "apply_patch_hook_covered")
CAPABILITY_LISTS = ("unhooked_mutating_tools", "managed_policy_conflicts",
                    "inherited_instruction_conflicts")
_SHELL_SYNTAX = re.compile(r"[\n\r;&|<>`]|\$\(|\$\{|\x00")
_PATCH_TARGET = re.compile(r"^\*\*\* (Update|Add|Delete) File: (.+?)\s*$")
_REVIEW_FORBIDDEN_TOOLS = {
    "pytest", "py.test", "unittest", "tox", "nox", "jest", "vitest",
    "mocha", "cargo", "go", "ruff", "mypy", "pyright", "eslint",
    "tsc", "prettier", "black", "yapf", "isort", "autopep8",
    # Reviewer argv descriptors cannot safely authorize arbitrary code runners:
    # test launchers can be hidden behind `python -m`, `node`, or `npx`.
    "python", "python2", "python3", "py", "node", "nodejs", "npx",
    "deno", "bun", "ruby", "perl", "php", "java", "javac",
    "npm", "pnpm", "yarn", "pip", "pip3", "poetry", "uv",
}


def _review_safe_read_only(argv):
    """Keep reviewer descriptors limited to inspection, never validation/mutation."""
    if not isinstance(argv, list) or not argv or not all(isinstance(v, str) and v for v in argv):
        return False
    executable = pathlib.PurePath(argv[0].replace("\\", "/")).name.casefold()
    if executable.endswith((".exe", ".cmd", ".bat")):
        executable = executable.rsplit(".", 1)[0]
    if executable in _REVIEW_FORBIDDEN_TOOLS:
        return False
    action_tokens = {token.casefold() for token in argv[1:]}
    if executable in {"make", "gmake", "cmake"} and action_tokens.intersection(
            {"test", "check", "lint", "format", "fmt", "analyze", "analyse"}):
        return False
    return True


def _fail(message):
    raise PolicyUnavailable(message)


def _validate_codex(role, runtime, request):
    if role not in ROLES or not isinstance(runtime, dict) or runtime.get("backend") != "codex":
        _fail("Codex role/backend is invalid")
    roles = runtime.get("roles")
    config = roles.get(role) if isinstance(roles, dict) else None
    if not isinstance(config, dict):
        _fail("role configuration is missing")
    model = config.get("model")
    settings = config.get("settings")
    effort = settings.get("model_reasoning_effort") if isinstance(settings, dict) else None
    if not isinstance(model, str) or not model.strip() or not isinstance(effort, str) or not effort.strip():
        _fail("explicit Codex model and reasoning effort are required")
    if config.get("policy") != ("workspace-write" if role == "operator" else "read-only"):
        _fail("role sandbox policy does not match its required boundary")
    if not isinstance(request, dict) or not isinstance(request.get("developer_instructions"), str):
        _fail("packaged developer instructions are required")
    capabilities = request.get("capabilities")
    if not isinstance(capabilities, dict):
        _fail("Codex capability report is required")
    for key in CAPABILITY_FLAGS:
        if capabilities.get(key) is not True:
            _fail("required capability unavailable: " + key)
    for key in CAPABILITY_LISTS:
        value = capabilities.get(key)
        if not isinstance(value, list) or value:
            _fail("conflicting capability state: " + key)
    return config, settings


def build_overrides(role, runtime, request):
    """Return documented per-invocation Codex options; never writes config."""
    config, settings = _validate_codex(role, runtime, request)
    argv = ["--model", config["model"], "--sandbox", config["policy"],
            "--ask-for-approval", "never"]
    values = {"developer_instructions": request["developer_instructions"],
              "model_reasoning_effort": settings["model_reasoning_effort"],
              "agents.enabled": False, "features.apps": False,
              "web_search": "disabled"}
    if role == "director":
        values["features.shell_tool"] = False
        values["features.unified_exec"] = False
    for key, value in values.items():
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        argv.extend(("--config", key + "=" + encoded))
    return argv


def _deny(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                  "permissionDecision": "deny", "reason": str(reason)}}


def _allow():
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                  "permissionDecision": "allow"}}


def _policy_root(policy):
    required = ("role", "workspace_root", "task_id", "attempt_id", "touches",
                "new_test_files", "protected_paths", "runner_commands", "read_only_commands",
                "supervisor_path_grants", "director_approved_existing_changes")
    if not isinstance(policy, dict) or any(key not in policy for key in required):
        raise ValueError("incomplete attempt-bound policy")
    if (not isinstance(policy.get("touches"), list) or
            not all(isinstance(value, str) for value in policy["touches"]) or
            not isinstance(policy.get("new_test_files"), list) or
            not all(isinstance(value, str) for value in policy["new_test_files"]) or
            not isinstance(policy.get("protected_paths"), list) or
            not all(isinstance(value, str) for value in policy["protected_paths"]) or
            not isinstance(policy.get("runner_commands"), dict) or
            not isinstance(policy.get("read_only_commands"), list) or
            not isinstance(policy.get("supervisor_path_grants"), list) or
            not isinstance(policy.get("director_approved_existing_changes"), list)):
        raise ValueError("malformed attempt-bound policy")
    root = pathlib.Path(policy["workspace_root"]).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("workspace root is not a directory")
    if policy.get("role") not in ROLES or not policy.get("task_id") or not policy.get("attempt_id"):
        raise ValueError("invalid attempt policy identity")
    if policy.get("role") == "reviewer" and any(
            not _review_safe_read_only(argv) for argv in policy["read_only_commands"]):
        raise ValueError("reviewer read-only command descriptor is unsafe or unavailable")
    return root


def _relative(policy, value):
    root = _policy_root(policy)
    path = pathlib.Path(str(value).replace("\\", "/"))
    if path.is_absolute():
        resolved = path.resolve(strict=False)
    else:
        resolved = (root / path).resolve(strict=False)
    try:
        rel = resolved.relative_to(root)
    except ValueError:
        raise ValueError("path escapes workspace")
    if not rel.parts or any(part in ("..", "") for part in rel.parts):
        raise ValueError("invalid workspace path")
    return rel.as_posix()


def _is_protected(path, policy):
    canonical = path.casefold()
    for item in policy.get("protected_paths", []):
        try:
            if _relative(policy, item).casefold() == canonical:
                return True
        except Exception:
            return True
    basename = canonical.rsplit("/", 1)[-1]
    return (canonical == ".git" or canonical.startswith(".git/") or
            canonical.startswith(".superpowers/ledger") or
            basename in {"plan.json", "ledger.jsonl", "runtime.json"} or
            canonical.startswith(".superpowers/plan") or
            canonical.endswith("/runtime.json") or canonical == "runtime.json")


def _grant(path, policy, issuer, collection, *, approved=False):
    for grant in policy.get(collection, []):
        if not isinstance(grant, dict):
            continue
        try:
            same_path = _relative(policy, grant.get("path", "")).casefold() == path.casefold()
        except Exception:
            continue
        if (same_path and grant.get("issuer") == issuer and
                grant.get("task_id") == policy.get("task_id") and
                grant.get("attempt_id") == policy.get("attempt_id") and
                (not approved or grant.get("approved") is True)):
            return True
    return False


def _parse_patch(command, policy):
    lines = command.splitlines()
    if len(lines) < 3 or lines[0] != "*** Begin Patch" or lines[-1] != "*** End Patch":
        raise ValueError("malformed patch")
    targets = []
    for line in lines[1:-1]:
        if line.startswith("*** "):
            match = _PATCH_TARGET.fullmatch(line)
            if not match:
                if line.startswith("*** End of File"):
                    continue
                raise ValueError("unknown patch directive")
            targets.append((match.group(1), _relative(policy, match.group(2))))
    if not targets:
        raise ValueError("patch has no targets")
    root = _policy_root(policy)
    for operation, path in targets:
        if _is_protected(path, policy):
            raise ValueError("protected path")
        if operation == "Add":
            allowed = any(_relative(policy, item).casefold() == path.casefold()
                          for item in policy.get("new_test_files", []))
            allowed = allowed or _grant(path, policy, "supervisor", "supervisor_path_grants")
            if not allowed or (root / pathlib.PurePosixPath(path)).exists():
                raise ValueError("new path is not authorized")
        else:
            exists_touched = any(_relative(policy, item).casefold() == path.casefold()
                                 for item in policy.get("touches", []))
            exists_approved = _grant(path, policy, "director", "director_approved_existing_changes", approved=True)
            if not (exists_touched or exists_approved):
                raise ValueError("existing path is not authorized")


def _parse_command(command):
    if not isinstance(command, str) or not command.strip() or _SHELL_SYNTAX.search(command):
        raise ValueError("unsafe or malformed command")
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as exc:
        raise ValueError("malformed command quoting") from exc
    if not tokens:
        raise ValueError("empty command")
    lowered = [token.casefold() for token in tokens]
    first = pathlib.PurePath(lowered[0].replace("\\", "/")).name
    if first in {"git", "git.exe", "bash", "sh", "zsh", "cmd", "cmd.exe", "powershell", "pwsh", "python", "python3", "py"}:
        raise ValueError("direct Git and command wrappers are forbidden")
    return tokens


def _check_command(command, policy):
    role = policy.get("role")
    tokens = _parse_command(command)
    if role == "director":
        raise ValueError("director has no shell capability")
    root = _policy_root(policy)
    if role == "operator":
        runners = policy.get("runner_commands", {})
        if isinstance(runners, dict):
            for descriptor in runners.values():
                if not isinstance(descriptor, dict):
                    continue
                argv, cwd = descriptor.get("argv"), descriptor.get("cwd")
                resolved_cwd = None
                if isinstance(cwd, str):
                    cwd_path = pathlib.Path(cwd)
                    resolved_cwd = (cwd_path if cwd_path.is_absolute() else root / cwd_path).resolve(strict=False)
                if (isinstance(argv, list) and all(isinstance(v, str) for v in argv) and
                        resolved_cwd == root and tokens == argv):
                    return
    for argv in policy.get("read_only_commands", []):
        if (role == "reviewer" and not _review_safe_read_only(argv)):
            continue
        if isinstance(argv, list) and tokens == argv:
            return
    raise ValueError("command is not an exact approved descriptor")


def check_tool_call(event, policy):
    """Return Codex's documented PreToolUse decision object, failing closed."""
    try:
        if not isinstance(event, dict) or event.get("hook_event_name") != "PreToolUse":
            raise ValueError("invalid hook event")
        _policy_root(policy)
        tool = event.get("tool_name")
        tool_input = event.get("tool_input")
        if not isinstance(tool_input, dict) or set(tool_input) != {"command"}:
            raise ValueError("missing tool input")
        if tool == "Bash":
            _check_command(tool_input.get("command"), policy)
        elif tool == "apply_patch":
            if policy.get("role") != "operator":
                raise ValueError("role cannot edit")
            _parse_patch(tool_input.get("command"), policy)
        else:
            raise ValueError("unknown tool")
        return _allow()
    except Exception as exc:
        return _deny(exc or "policy rejected tool call")


def capture_protected_state(request):
    """Hash protected files and Git state, bound to this work attempt."""
    if not isinstance(request, dict):
        _fail("request is required")
    try:
        root = pathlib.Path(request["workspace_root"]).resolve(strict=True)
        if not root.is_dir() or not request.get("task_id") or not request.get("attempt_id"):
            _fail("invalid protected-state identity")
        files = {}
        for item in request.get("protected_paths", []):
            rel = _relative({"role": "operator", "workspace_root": str(root),
                             "task_id": request["task_id"], "attempt_id": request["attempt_id"],
                             "touches": [], "new_test_files": [], "protected_paths": [],
                             "runner_commands": {}, "read_only_commands": [],
                             "supervisor_path_grants": [],
                             "director_approved_existing_changes": []}, item)
            path = root / pathlib.PurePosixPath(rel)
            if path.exists() and not path.is_file():
                _fail("protected path is not a file: " + rel)
            digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            files[rel] = {"exists": path.is_file(), "sha256": digest}
        head_result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root), capture_output=True,
                                     text=True, check=True, timeout=10)
        status_result = subprocess.run(["git", "status", "--porcelain=v1", "-z"], cwd=str(root),
                                       capture_output=True, check=True, timeout=10)
        if status_result.stderr:
            _fail("could not capture Git status")
        git_head = head_result.stdout.strip()
        status_bytes = status_result.stdout if isinstance(status_result.stdout, bytes) else status_result.stdout.encode("utf-8")
        status_hash = "sha256:" + hashlib.sha256(status_bytes).hexdigest()
        identity = {"version": 1, "workspace_root": str(root), "task_id": request["task_id"],
                    "attempt_id": request["attempt_id"], "git_head": git_head,
                    "git_status_sha256": status_hash, "protected_files": files}
        fingerprint = "sha256:" + hashlib.sha256(json.dumps(identity, sort_keys=True,
                                     ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
        return {**identity, "fingerprint": fingerprint}
    except PolicyUnavailable:
        raise
    except Exception as exc:
        _fail("protected-state capture failed: " + str(exc))
