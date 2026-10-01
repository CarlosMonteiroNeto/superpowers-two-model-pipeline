"""Build OpenCode-native role settings and report policy coverage honestly."""

from __future__ import annotations

import pathlib


_ROLES = {"operator", "reviewer", "director"}
_REVIEW_FORBIDDEN_TOOLS = {
    "pytest", "py.test", "unittest", "tox", "nox", "jest", "vitest",
    "mocha", "cargo", "go", "ruff", "mypy", "pyright", "eslint",
    "tsc", "prettier", "black", "yapf", "isort", "autopep8",
    # Do not let a reviewer descriptor invoke arbitrary code through a runtime
    # or package runner (`python -m pytest`, `node ...jest`, `npx jest`).
    "python", "python2", "python3", "py", "node", "nodejs", "npx",
    "deno", "bun", "ruby", "perl", "php", "java", "javac",
    "npm", "pnpm", "yarn", "pip", "pip3", "poetry", "uv",
}


def _valid_pattern_argv(argv):
    # OpenCode v1 patterns match command values using * and ?. Joining argv
    # cannot preserve shell quoting, and wildcard characters broaden access.
    return (isinstance(argv, list) and bool(argv) and
            all(isinstance(value, str) and value and
                not any(ch.isspace() or ch in "*?;|&<>`$()" for ch in value)
                for value in argv))


def _review_safe_argv(argv):
    if not _valid_pattern_argv(argv):
        return False
    executable = pathlib.PurePath(argv[0].replace("\\", "/")).name.casefold()
    if executable.endswith((".exe", ".cmd", ".bat")):
        executable = executable.rsplit(".", 1)[0]
    if executable in _REVIEW_FORBIDDEN_TOOLS:
        return False
    action_tokens = {token.casefold() for token in argv[1:]}
    return not (executable in {"make", "gmake", "cmake"} and action_tokens.intersection(
        {"test", "check", "lint", "format", "fmt", "analyze", "analyse"}))


def _rel(root, value):
    path = pathlib.Path(str(value).replace("\\", "/"))
    resolved = (path if path.is_absolute() else root / path).resolve(strict=False)
    return resolved.relative_to(root).as_posix()


def build_settings(role, runtime, request):
    if role not in _ROLES or not isinstance(runtime, dict) or runtime.get("backend") != "opencode":
        raise ValueError("OpenCode backend and supported role are required")
    roles = runtime.get("roles")
    item = roles.get(role) if isinstance(roles, dict) else None
    if not isinstance(item, dict) or not isinstance(item.get("model"), str) or not item["model"]:
        raise ValueError("explicit OpenCode role model is required")
    settings = item.get("settings")
    if not isinstance(settings, dict) or not all(isinstance(settings.get(k), str) and settings[k]
                                                for k in ("variant", "agent")):
        raise ValueError("explicit OpenCode variant and agent are required")
    if not isinstance(request, dict) or not isinstance(request.get("workspace_root"), str):
        raise ValueError("workspace_root is required")
    root = pathlib.Path(request["workspace_root"]).resolve(strict=True)
    caps = request.get("capabilities")
    if not isinstance(caps, dict) or caps.get("permission_schema") != "v1":
        raise ValueError("OpenCode permission schema is unavailable")

    permission = {
        "read": "allow", "edit": {"*": "deny"}, "glob": "allow", "grep": "allow",
        "list": "allow", "bash": {"*": "deny"}, "task": "deny",
        "external_directory": "deny", "webfetch": "deny", "websearch": "deny",
    }
    enforced = ["default-deny tools", "protected-path deny rules"]
    uncovered = caps.get("uncovered_mutating_tools", [])
    if not isinstance(uncovered, list) or not all(isinstance(value, str) for value in uncovered):
        unsupported = ["malformed uncovered_mutating_tools capability report"]
    else:
        unsupported = list(uncovered)
    available_paths = True
    if role == "operator":
        try:
            for value in request.get("touches", []) + request.get("new_test_files", []):
                path = _rel(root, value)
                name = path.rsplit("/", 1)[-1].casefold()
                if (path.startswith(".superpowers/") or path == ".git" or path.startswith(".git/") or
                        name in {"plan.json", "ledger.jsonl", "runtime.json"}):
                    raise ValueError("protected path cannot be writable")
                permission["edit"][path] = "allow"
            permission["edit"]["*"] = "deny"
            enforced.append("path-scoped edits")
        except (OSError, ValueError):
            available_paths = False
            unsupported.append("path-scoped edits")
        runners = request.get("runner_commands", {})
        if not isinstance(runners, dict):
            unsupported.append("malformed scoped runner descriptors")
            runners = {}
        for descriptor in runners.values():
            argv = descriptor.get("argv") if isinstance(descriptor, dict) else None
            if not _valid_pattern_argv(argv):
                unsupported.append("ambiguous scoped runner argv")
                continue
            permission["bash"][" ".join(argv)] = "allow"
        for command in request.get("read_only_commands", []):
            if not _valid_pattern_argv(command):
                unsupported.append("ambiguous read-only command argv")
                continue
            permission["bash"][" ".join(command)] = "allow"
        if permission["bash"] != {"*": "deny"}:
            enforced.append("exact declared command allowlist")
    elif role == "reviewer":
        permission["edit"] = "deny"
        permission["bash"] = {"*": "deny"}
        for command in request.get("read_only_commands", []):
            if not _review_safe_argv(command):
                unsupported.append("invalid or disallowed reviewer command descriptor")
                continue
            permission["bash"][" ".join(command)] = "allow"
        enforced.append("read-only review")
    else:
        permission["edit"] = "deny"
        permission["bash"] = "deny"
        enforced.append("proposal-only director")
    # A final rule keeps protected paths denied even when a task touches list is malformed.
    if isinstance(permission["edit"], dict):
        for value in request.get("protected_paths", []):
            try:
                permission["edit"][_rel(root, value)] = "deny"
            except (OSError, ValueError):
                unsupported.append("protected path outside workspace: " + str(value))
    if unsupported:
        enforced = [entry for entry in enforced if entry not in unsupported]
    scope = request.get("scope")
    scope_record = None
    if (isinstance(scope, dict) and scope.get("mode") == "areas"
            and isinstance(scope.get("roots"), list)
            and all(isinstance(item, str) for item in scope["roots"])):
        enforced.append("directory-scoped edits")
        scope_record = {"mode": "areas", "roots": list(scope["roots"])}
    config = {"agent": {settings["agent"]: {"model": item["model"], "variant": settings["variant"],
                                             "prompt": request.get("developer_instructions", item.get("instruction", "")),
                                             "permission": permission}}}
    capabilities = {"enforced": sorted(set(enforced)),
                    "unsupported": sorted(set(str(v) for v in unsupported)),
                    "available": not unsupported and available_paths}
    if scope_record is not None:
        capabilities["scope"] = scope_record
    return {"config": config, "capabilities": capabilities}
