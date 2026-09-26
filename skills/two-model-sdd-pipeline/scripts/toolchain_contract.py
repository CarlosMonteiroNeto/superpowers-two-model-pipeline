"""Validate and resolve immutable, argv-based toolchain descriptors."""

from __future__ import annotations

import json
import os
import shutil
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


ADAPTER_LANGUAGES = {
    "flutter_machine": {"flutter", "dart"},
    "pytest_json_report": {"python"},
    "unittest": {"python", "unittest"},
    "go_test_json": {"go"},
}


def _failure(message: str) -> dict[str, Any]:
    return {"available": False, "error": message}


def _resolve_executable(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError("%s must name an executable" % label)
    candidate = shutil.which(value)
    if candidate:
        return os.path.abspath(candidate)
    path = Path(value).expanduser()
    if path.is_file():
        return str(path.resolve())
    raise ValueError("%s is unavailable: %s" % (label, value))


def _resolve_cwd(value: Any, root: Path, label: str) -> str:
    if value is None:
        value = "."
    if not isinstance(value, str) or "\x00" in value:
        raise ValueError("%s cwd must be a relative path" % label)
    candidate = Path(value)
    root_display = Path(os.path.abspath(str(root)))
    root_real = root_display.resolve()
    if candidate.is_absolute():
        target_display = Path(os.path.abspath(str(candidate)))
    else:
        target_display = Path(os.path.abspath(str(root_display / candidate)))
    target = target_display.resolve()
    try:
        target.relative_to(root_real)
    except ValueError as exc:
        raise ValueError("%s cwd escapes the project root" % label) from exc
    if not target.is_dir():
        raise ValueError("%s cwd does not exist: %s" % (label, target))
    return str(target_display)


def _resolve_command(name: str, raw: Any, root: Path) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("commands.%s must be an object" % name)
    argv = raw.get("argv")
    if not isinstance(argv, list) or not argv or not all(
        isinstance(part, str) and part and "\x00" not in part for part in argv
    ):
        raise ValueError("commands.%s.argv must be a nonempty string array" % name)
    executable = _resolve_executable(argv[0], "commands.%s.argv[0]" % name)
    normalized_argv = [executable, *argv[1:]]
    env = raw.get("env", raw.get("environment", {}))
    if not isinstance(env, dict) or not all(
        isinstance(key, str) and key and isinstance(value, str)
        and "\x00" not in key and "\x00" not in value
        for key, value in env.items()
    ):
        raise ValueError("commands.%s env must map strings to strings" % name)
    normalized_env = dict(sorted(env.items()))
    return {
        "argv": normalized_argv,
        "cwd": _resolve_cwd(raw.get("cwd", "."), root, "commands.%s" % name),
        "env": normalized_env,
        "environment": normalized_env,
    }


def resolve_toolchain(task: dict, runtime: dict, project_root: str) -> dict:
    """Resolve only the descriptor named by ``task.toolchain_id``.

    A missing or unsupported descriptor is returned as an explicit preflight
    failure. No language/ledger order fallback is attempted.
    """
    if not isinstance(task, dict) or not isinstance(runtime, dict):
        return _failure("task and runtime must be objects")
    toolchain_id = task.get("toolchain_id")
    if not isinstance(toolchain_id, str) or not toolchain_id.strip():
        return _failure("task has no explicit toolchain_id")
    all_toolchains = runtime.get("toolchains")
    if not isinstance(all_toolchains, dict) or toolchain_id not in all_toolchains:
        return _failure("unknown toolchain_id: %s" % toolchain_id)
    raw = all_toolchains[toolchain_id]
    if not isinstance(raw, dict):
        return _failure("toolchain %s must be an object" % toolchain_id)
    try:
        adapter = raw.get("red_adapter")
        if not isinstance(adapter, str) or adapter not in ADAPTER_LANGUAGES:
            raise ValueError("unsupported or missing RED adapter for toolchain %s" % toolchain_id)
        language = raw.get("language")
        if not language:
            language = toolchain_id.split("-", 1)[0].lower()
        if language not in ADAPTER_LANGUAGES[adapter]:
            raise ValueError("RED adapter %s is not tested for language %s" % (adapter, language))
        executable = _resolve_executable(raw.get("executable"), "toolchain executable")
        commands = raw.get("commands")
        if not isinstance(commands, dict):
            raise ValueError("toolchain commands must be an object")
        missing = [name for name in ("red", "test") if name not in commands]
        if missing:
            raise ValueError("toolchain is missing configured command(s): %s" % ", ".join(missing))
        root = Path(os.path.abspath(str(project_root)))
        if not root.resolve().is_dir():
            raise ValueError("project root does not exist: %s" % root)
        resolved_commands = {
            name: _resolve_command(name, command, root)
            for name, command in sorted(commands.items())
        }
        return {
            "available": True,
            "toolchain_id": toolchain_id,
            "language": language,
            "executable": executable,
            "commands": resolved_commands,
            "red_adapter": adapter,
            "project_root": str(root),
            "network_access": raw.get("network_access", []),
            "cache_access": raw.get("cache_access", []),
        }
    except (OSError, ValueError, TypeError) as exc:
        return _failure(str(exc))


def _language_for_marker(marker: str) -> str:
    return {
        "pubspec.yaml": "flutter",
        "pyproject.toml": "python",
        "requirements.txt": "python",
        "go.mod": "go",
        "package.json": "node",
        "Cargo.toml": "rust",
    }[marker]


def _default_descriptor(marker: str) -> tuple[str, dict[str, Any]]:
    language = _language_for_marker(marker)
    if language == "flutter":
        toolchain_id, exe, adapter = "flutter-default", "flutter", "flutter_machine"
        commands = {
            "red": {"argv": [exe, "test", "--machine", "{test_paths}"], "cwd": ".", "env": {}},
            "test": {"argv": [exe, "test"], "cwd": ".", "env": {}},
            "analyze": {"argv": [exe, "analyze"], "cwd": ".", "env": {}},
            "format": {"argv": ["dart", "format", "--set-exit-if-changed", "."], "cwd": ".", "env": {}},
        }
    elif language == "python":
        toolchain_id, exe, adapter = "python-pytest", "pytest", "pytest_json_report"
        commands = {
            "red": {"argv": [exe, "-q", "--json-report", "--json-report-file={evidence_path}", "{test_paths}"], "cwd": ".", "env": {}},
            "test": {"argv": [exe, "-q"], "cwd": ".", "env": {}},
            "analyze": {"argv": ["ruff", "check", "."], "cwd": ".", "env": {}},
        }
    elif language == "go":
        toolchain_id, exe, adapter = "go-default", "go", "go_test_json"
        commands = {
            "red": {"argv": [exe, "test", "-json", "{test_paths}"], "cwd": ".", "env": {}},
            "test": {"argv": [exe, "test", "./..."], "cwd": ".", "env": {}},
            "analyze": {"argv": [exe, "vet", "./..."], "cwd": ".", "env": {}},
        }
    else:
        raise ValueError("unsupported toolchain %s: configure an explicitly tested RED adapter" % language)
    return toolchain_id, {
        "language": language,
        "executable": exe,
        "commands": commands,
        "red_adapter": adapter,
    }


def _load_runtime(path: str | None) -> dict[str, Any]:
    if not path:
        return {"toolchains": {}}
    with open(path, encoding="utf-8") as stream:
        runtime = json.load(stream)
    if not isinstance(runtime, dict):
        raise ValueError("runtime manifest must be a JSON object")
    return runtime


def _marker_files(root: Path) -> list[str]:
    return sorted(marker for marker in (
        "Cargo.toml", "go.mod", "package.json", "pubspec.yaml",
        "pyproject.toml", "requirements.txt",
    ) if (root / marker).is_file())


def _configured_for_language(runtime: dict[str, Any], language: str) -> list[tuple[str, dict[str, Any]]]:
    result = []
    for toolchain_id, descriptor in (runtime.get("toolchains") or {}).items():
        if not isinstance(descriptor, dict):
            continue
        declared = descriptor.get("language") or str(toolchain_id).split("-", 1)[0].lower()
        if declared == language:
            result.append((toolchain_id, descriptor))
    return sorted(result, key=lambda item: item[0])


def resolve_cli(workspace: str, root_value: str, all_markers: bool, runtime_path: str | None) -> int:
    root = Path(root_value).resolve()
    if not root.is_dir():
        print("RESOLVE-TOOLCHAIN: project root does not exist: %s" % root, file=sys.stderr)
        return 2
    markers = _marker_files(root)
    if not markers:
        print("RESOLVE-TOOLCHAIN: no supported ecosystem marker in %s" % root, file=sys.stderr)
        return 2
    if len(markers) > 1 and not all_markers:
        print("RESOLVE-TOOLCHAIN: ambiguous markers; use --all or an explicit runtime configuration: %s" %
              ", ".join(markers), file=sys.stderr)
        return 1
    try:
        runtime = _load_runtime(runtime_path)
    except (OSError, ValueError) as exc:
        print("RESOLVE-TOOLCHAIN: invalid runtime manifest: %s" % exc, file=sys.stderr)
        return 2

    results = []
    errors = []
    for marker in markers:
        language = _language_for_marker(marker)
        configured = _configured_for_language(runtime, language)
        if configured:
            candidates = configured
        else:
            try:
                candidates = [_default_descriptor(marker)]
            except ValueError as exc:
                errors.append(str(exc))
                continue
        for toolchain_id, descriptor in candidates:
            resolved = resolve_toolchain(
                {"toolchain_id": toolchain_id},
                {"toolchains": {toolchain_id: descriptor}},
                str(root),
            )
            if not resolved.get("available"):
                message = resolved.get("error", "preflight failed")
                # Keep the historical monorepo inventory useful on hosts
                # where Go is not installed, while marking the descriptor as
                # unavailable. scoped-run revalidates it and fails preflight;
                # this record can never authorize a command or a coder loop.
                if (runtime_path is None and toolchain_id == "go-default"
                        and "executable is unavailable: go" in message):
                    commands = {}
                    for name, command in descriptor["commands"].items():
                        commands[name] = {
                            "argv": list(command["argv"]),
                            "cwd": str(root),
                            "env": dict(command.get("env", {})),
                            "environment": dict(command.get("env", {})),
                        }
                    results.append((marker, {
                        "available": False,
                        "preflight_error": message,
                        "toolchain_id": toolchain_id,
                        "language": language,
                        "executable": "go",
                        "commands": commands,
                        "red_adapter": "go_test_json",
                        "project_root": str(root),
                        "network_access": [],
                        "cache_access": [],
                    }))
                    continue
                errors.append("%s: %s" % (toolchain_id, message))
                continue
            results.append((marker, resolved))

    if not results:
        for error in errors:
            print("RESOLVE-TOOLCHAIN: " + error, file=sys.stderr)
        return 3 if errors else 2

    ledger = Path(workspace) / "ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    append_script = Path(__file__).with_name("ledger-append")
    for marker, descriptor in results:
        language = descriptor["language"]
        commands = descriptor["commands"]
        payload = json.dumps(descriptor, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        # Legacy gates retain printable command summaries. New scoped workers
        # consume the structured descriptor and never shell-split these fields.
        test_summary = shlex.join(commands["test"]["argv"])
        analyze_command = commands.get("analyze")
        analyze_summary = (
            shlex.join(analyze_command["argv"])
            if analyze_command is not None else ""
        )
        analyze_available = "true" if analyze_command is not None else "false"
        fields = [
            "gate", "-", "resolved %s (%s)" % (descriptor["toolchain_id"], marker),
            "toolchain_id=" + descriptor["toolchain_id"],
            "toolchain_descriptor=" + payload,
            "test_cmd=" + test_summary,
            "analyze_cmd=" + analyze_summary,
            "analyze_available=" + analyze_available,
            "red_adapter=" + descriptor["red_adapter"],
            "lang=" + language,
            "detected=auto",
        ]
        # On Windows the launcher has Git Bash; callers already use this
        # script through Bash, so inherit that executable explicitly.
        bash = os.environ.get("BASH_BIN") or shutil.which("bash") or "bash"
        result = subprocess.run(
            [bash, str(append_script), "--stdin-tsv", str(ledger)],
            input="\t".join(fields) + "\n",
            capture_output=True, text=True, encoding="utf-8",
        )
        if result.returncode:
            print(result.stdout, end="")
            print(result.stderr, end="", file=sys.stderr)
            return result.returncode
        print("TOOLCHAIN_ID=%s" % descriptor["toolchain_id"])
        print("LANG=%s" % language)
        print("TEST_CMD=%s" % shlex.join(commands["test"]["argv"]))
        if analyze_command is None:
            print("ANALYZE_UNAVAILABLE=%s (no analyzer configured)" % descriptor["toolchain_id"])
        print("ledgered: %s" % descriptor["toolchain_id"])
    for error in errors:
        print("RESOLVE-TOOLCHAIN: " + error, file=sys.stderr)
    return 3 if errors else 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--resolve-cli":
        # Internal entrypoint called only by the fixed resolve-toolchain
        # wrapper; no arbitrary command string is accepted.
        all_markers = sys.argv[2] == "1"
        workspace, root = sys.argv[3], sys.argv[4]
        runtime = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] else None
        sys.exit(resolve_cli(workspace, root, all_markers, runtime))
    print("toolchain_contract.py is a library; use resolve-toolchain", file=sys.stderr)
    sys.exit(2)
