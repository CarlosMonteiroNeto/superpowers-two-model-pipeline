"""Read-only OpenCode adapter capability probe (Round 1 Task 2).

inspects the validated runtime configuration and the local project without
installing, upgrading, dispatching, editing user config, launching a model,
or exposing credentials:

  opencode_capabilities.inspect_runtime(config: dict, project: str) -> dict

The probe resolves the native OpenCode executable (Windows launcher
discovery prefers a native executable over a PowerShell wrapper), captures
its --version/--help output, checks the required CLI options, validates
the per-role OpenCode settings, and records unknown live model/auth/policy
support as "unverified": help/version checks never certify live behavior.
A config for the other backend is refused outright; there is no fallback
to a different model or backend.

OpenCode setting/event/session semantics live in this module only and are
never shared with the Codex adapter.
"""

import os
import subprocess

import pipeline_config

BACKEND = "opencode"
EXECUTABLE = "opencode"

# OpenCode-only role settings: an explicit variant per role (agent
# optional). Codex effort/sandbox keys are unsupported combinations here.
REQUIRED_SETTINGS = ("variant",)
OPTIONAL_SETTINGS = ("agent",)

# Verified against the dispatch boundary in scripts/dispatch
# (opencode run --agent NAME --format json ...).
REQUIRED_OPTIONS = ("run", "--agent", "--format")

# Adapter-specific event vocabulary, verified against the dispatch digest
# consumer (JSONL events with type "text" and sessionID). Codex uses its own
# thread/turn vocabulary; the two lists are never merged.
EVENT_NAMES = ("text",)
SESSION_KIND = "opencode-session"

# Presence signal only: existence is reported, contents are never read, and
# live readiness always stays "unverified".
AUTH_FILE_PARTS = (".config", "opencode", "opencode.json")

PROBE_TIMEOUT_SECONDS = 10


class CapabilityError(ValueError):
    """The config/project cannot be probed for this backend."""


def _discover(exe_name):
    """Resolve *exe_name* on PATH, preferring native executables.

    Within each PATH directory the order is native first (name.exe, bare
    name) then launcher wrappers (.cmd/.bat, .ps1); PATH order decides
    between directories. Returns (path, kind) where kind is "native",
    "shell-wrapper", "powershell-wrapper", or "missing" (path None).
    """
    suffixes = (
        exe_name + ".exe",
        exe_name,
        exe_name + ".cmd",
        exe_name + ".bat",
        exe_name + ".ps1",
    )
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        for candidate in suffixes:
            full = os.path.join(directory, candidate)
            try:
                if not os.path.isfile(full):
                    continue
            except OSError:
                continue
            lowered = candidate.lower()
            if lowered.endswith(".ps1"):
                return full, "powershell-wrapper"
            if lowered.endswith((".cmd", ".bat")):
                return full, "shell-wrapper"
            return full, "native"
    return None, "missing"


def _probe_output(argv):
    """Run a read-only probe (argv array, never a shell string).

    Returns stdout on success, None when the binary is unrunnable or the
    probe itself fails. Only --version/--help style probes run here; the
    adapter never invokes run/continue.
    """
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            env=dict(os.environ),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout or ""


def _git_head(project):
    try:
        completed = subprocess.run(
            ["git", "-C", project, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            env=dict(os.environ),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _credential_present():
    try:
        return os.path.isfile(
            os.path.join(os.path.expanduser("~"), *AUTH_FILE_PARTS))
    except OSError:
        return False


def inspect_runtime(config, project):
    """Probe OpenCode capabilities for a validated config and project dir."""
    if not isinstance(config, dict):
        raise CapabilityError("config must be an object")
    if config.get("backend") != BACKEND:
        raise CapabilityError(
            "opencode adapter cannot inspect a %r config; refusing to "
            "fall back to another backend" % (config.get("backend"),))
    normalized = pipeline_config.normalize_config(config)
    if not isinstance(project, str) or not project:
        raise CapabilityError("project must be a directory path")
    if not os.path.isdir(project):
        raise CapabilityError("no such project directory: %s" % project)

    exe_path, kind = _discover(EXECUTABLE)
    version = None
    help_text = None
    if exe_path is not None:
        out = _probe_output([exe_path, "--version"])
        if out is not None:
            first = out.strip().splitlines()
            version = first[0].strip()[:200] if first else None
            if not version:
                version = None
        help_text = _probe_output([exe_path, "--help"])
    options_supported = (
        help_text is not None
        and all(option in help_text for option in REQUIRED_OPTIONS)
    )

    confirmation = normalized.get("confirmation", {})
    needs_configuration = confirmation.get("confirmed") is not True

    roles = {}
    for name, role in normalized["roles"].items():
        roles[name] = {
            "model": role["model"],
            "settings": dict(role["settings"]),
            "policy": role["policy"],
            "instruction": role["instruction"],
            "supported": True,
            "reason": "opencode role settings validated "
                      "(variant explicit)",
        }

    manifest = {
        "backend": BACKEND,
        "config_hash": pipeline_config.configuration_hash(config),
        "role_hashes": {name: pipeline_config.role_hash(role)
                        for name, role in config.get("roles", {}).items()
                        if isinstance(role, dict)},
        "bundle_hash": pipeline_config.bundle_hash(),
        "executable_path": exe_path,
        "executable_version": version,
        "project_path": os.path.realpath(os.path.abspath(project)),
        "project_git_head": _git_head(project),
        "plan_path": normalized.get("plan_path"),
        "run_id": normalized.get("run_id"),
    }

    return {
        "backend": BACKEND,
        "needs_configuration": needs_configuration,
        "executable": {
            "name": EXECUTABLE,
            "path": exe_path,
            "kind": kind,
            "available": exe_path is not None,
            "version": version,
            "required_options": list(REQUIRED_OPTIONS),
            "options_supported": options_supported,
        },
        "roles": roles,
        "setting_keys": {
            "required": list(REQUIRED_SETTINGS),
            "optional": list(OPTIONAL_SETTINGS),
        },
        "events": list(EVENT_NAMES),
        "session": {
            "kind": SESSION_KIND,
            "id": None,
            "resumed_from": None,
            "note": "R1 defines contracts only; worker resume is a later "
                    "round",
        },
        "auth": {
            "credential_file": os.path.join(*AUTH_FILE_PARTS),
            "credential_present": _credential_present(),
            "live": "unverified",
        },
        "live": {
            "model": "unverified",
            "auth": "unverified",
            "policy": "unverified",
            "note": "help/version checks do not certify live behavior; "
                    "live model/auth/policy support is unverified",
        },
        "manifest": manifest,
        "credentials_exposed": False,
    }
