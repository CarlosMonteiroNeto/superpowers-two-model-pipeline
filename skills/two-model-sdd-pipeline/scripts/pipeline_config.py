"""Shared runtime configuration for the two-model pipeline (Round 1 Task 2).

The runtime config is a backend-neutral manifest: ``version: 1``,
``backend`` ("codex" or "opencode"), explicit per-role models with
backend-specific settings, toolchains, retention/cycle budgets,
an explicit publication choice, an explicit concurrency limit, and a
positive dispatch timeout. No product model is ever defaulted: a missing
model is a validation error, never a silent substitution.

Model selection itself is obtained from the user by the interactive launch
setup before implementation; this read-only round only exposes
``needs_configuration`` (through the adapter capability reports) and never
launches an LLM to ask. A confirmed selection carries the backend, the
roles, a configuration hash, and confirmation provenance; the hash binds
the effective (normalized) selection, so a stale confirmation is rejected
while normalization-added defaults stay transparent across load/probe
passes.

Canonical hash contract (also used for the immutable manifest bindings):
sha256 over canonical JSON (sorted keys, compact separators, unicode
preserved) encoded as UTF-8.

Usage: pipeline_config.load_runtime(path: str) -> dict; strict validation.
Invalid inputs raise pipeline_config.RuntimeConfigError (a ValueError).
"""

import copy
import hashlib
import json
import os
import sys

VERSION = 1
BACKENDS = ("codex", "opencode")
PUBLICATIONS = ("local", "pull_request")

DEFAULT_RETENTION_DAYS = 30
DEFAULT_CODER_CYCLE_LIMITS = [5, 3, 3]

REQUIRED_TOP_FIELDS = (
    "version",
    "backend",
    "roles",
    "toolchains",
    "publication",
    "max_parallel",
    "dispatch_timeout_seconds",
)
OPTIONAL_TOP_FIELDS = (
    "retention_days",
    "coder_cycle_limits",
    "confirmation",
    "plan_path",
    "run_id",
)

# Backend-specific role settings. Codex roles carry an explicit reasoning
# effort (sandbox mode optional); OpenCode roles carry an explicit variant
# (agent optional). Cross-backend keys are unsupported combinations.
CODEX_REQUIRED_SETTINGS = ("model_reasoning_effort",)
CODEX_OPTIONAL_SETTINGS = ("sandbox_mode",)
OPENCODE_REQUIRED_SETTINGS = ("variant",)
OPENCODE_OPTIONAL_SETTINGS = ("agent",)

# Spec section 4: Codex maps the operator policy to workspace-write and the
# reviewer/director policies to read-only. OpenCode uses its own policy
# representation, validated for presence only.
CODEX_OPERATOR_POLICY = "workspace-write"
CODEX_READONLY_POLICY = "read-only"

CONTRACT_FILES = (
    os.path.join("schemas", "runtime.schema.json"),
    os.path.join("scripts", "pipeline_config.py"),
    os.path.join("scripts", "codex_capabilities.py"),
    os.path.join("scripts", "opencode_capabilities.py"),
)


class RuntimeConfigError(ValueError):
    """A runtime configuration file or value failed strict validation."""


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def configuration_hash(config):
    """Hash the recorded selection bytes (everything but confirmation)."""
    if not isinstance(config, dict):
        raise RuntimeConfigError("configuration must be an object")
    body = {key: value for key, value in config.items()
            if key != "confirmation"}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def role_hash(role):
    """Hash one role binding for the immutable manifest."""
    if not isinstance(role, dict):
        raise RuntimeConfigError("role must be an object")
    return hashlib.sha256(_canonical(role).encode("utf-8")).hexdigest()


def bundle_hash(skill_dir=None):
    """Hash the canonical contract files of this skill bundle.

    Binds the exact validation/probe code a manifest was produced with.
    """
    root = skill_dir or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    digest = hashlib.sha256()
    for rel in CONTRACT_FILES:
        path = os.path.join(root, rel)
        try:
            with open(path, "rb") as handle:
                content = handle.read()
        except OSError as exc:
            raise RuntimeConfigError(
                "cannot read contract file %s: %s" % (rel, exc))
        digest.update(rel.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(content)
        digest.update(b"\x00")
    return digest.hexdigest()


def _fail(message):
    raise RuntimeConfigError(message)


def _nonempty_string(value, label):
    if not isinstance(value, str) or not value.strip():
        _fail("%s must be a nonempty string" % label)
    return value


def _positive_int(value, label):
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("%s must be an integer" % label)
    if value < 1:
        _fail("%s must be positive" % label)
    return value


def _validate_settings(backend, role_name, settings):
    if not isinstance(settings, dict):
        _fail("roles.%s.settings must be an object" % role_name)
    if backend == "codex":
        allowed = set(CODEX_REQUIRED_SETTINGS) | set(CODEX_OPTIONAL_SETTINGS)
        for key in CODEX_REQUIRED_SETTINGS:
            value = settings.get(key)
            if not isinstance(value, str) or not value.strip():
                _fail("roles.%s.settings.%s is required for codex"
                      % (role_name, key))
    else:
        allowed = (set(OPENCODE_REQUIRED_SETTINGS)
                   | set(OPENCODE_OPTIONAL_SETTINGS))
        for key in OPENCODE_REQUIRED_SETTINGS:
            value = settings.get(key)
            if not isinstance(value, str) or not value.strip():
                _fail("roles.%s.settings.%s is required for opencode"
                      % (role_name, key))
    for key in settings:
        if key not in allowed:
            _fail("roles.%s.settings.%s is not supported for backend %s"
                  % (role_name, key, backend))
    return dict(settings)


def _validate_role(backend, role_name, role):
    if not isinstance(role, dict):
        _fail("roles.%s must be an object" % role_name)
    model = role.get("model")
    if not isinstance(model, str) or not model.strip():
        _fail("roles.%s.model is required; no model is ever defaulted"
              % role_name)
    settings = _validate_settings(backend, role_name, role.get("settings"))
    policy = role.get("policy")
    if not isinstance(policy, str) or not policy.strip():
        _fail("roles.%s.policy is required" % role_name)
    if backend == "codex":
        if role_name == "operator" and policy != CODEX_OPERATOR_POLICY:
            _fail("codex roles.operator.policy must be %r"
                  % CODEX_OPERATOR_POLICY)
        if role_name != "operator" and policy != CODEX_READONLY_POLICY:
            _fail("codex roles.%s.policy must be %r"
                  % (role_name, CODEX_READONLY_POLICY))
    _nonempty_string(role.get("instruction"),
                     "roles.%s.instruction" % role_name)
    return {
        "model": model,
        "settings": settings,
        "policy": policy,
        "instruction": role["instruction"],
    }


def normalize_config(config):
    """Strictly validate a decoded runtime config and apply documented
    defaults. Returns a new normalized dict; the input is never mutated."""
    if not isinstance(config, dict):
        _fail("runtime configuration must be a JSON object")
    for key in config:
        if key not in REQUIRED_TOP_FIELDS + OPTIONAL_TOP_FIELDS:
            _fail("unsupported configuration field: %r" % key)
    for key in REQUIRED_TOP_FIELDS:
        if key not in config:
            _fail("missing required configuration field: %r" % key)

    if isinstance(config.get("version"), bool) \
            or config.get("version") != VERSION:
        _fail("version must be exactly %d" % VERSION)
    backend = config.get("backend")
    if backend not in BACKENDS:
        _fail("backend must be one of %s" % (list(BACKENDS),))

    roles = config.get("roles")
    if not isinstance(roles, dict):
        _fail("roles must be an object")
    normalized_roles = {}
    for role_name in ("operator", "reviewer"):
        if role_name not in roles:
            _fail("roles.%s is required" % role_name)
        normalized_roles[role_name] = _validate_role(
            backend, role_name, roles[role_name])
    if "director" in roles:
        normalized_roles["director"] = _validate_role(
            backend, "director", roles["director"])
    else:
        # The director defaults to the confirmed reviewer model unless the
        # user explicitly overrides it at launch.
        normalized_roles["director"] = copy.deepcopy(
            normalized_roles["reviewer"])

    toolchains = config.get("toolchains")
    if not isinstance(toolchains, dict) or not toolchains:
        _fail("toolchains must be a nonempty object")
    for name, descriptor in toolchains.items():
        if not isinstance(descriptor, dict):
            _fail("toolchains.%s must be an object" % name)

    if "retention_days" in config:
        retention_days = _positive_int(config["retention_days"],
                                       "retention_days")
    else:
        retention_days = DEFAULT_RETENTION_DAYS

    if "coder_cycle_limits" in config:
        limits = config["coder_cycle_limits"]
        if (not isinstance(limits, list) or len(limits) != 3
                or any(isinstance(item, bool) or not isinstance(item, int)
                       or item < 1 for item in limits)):
            _fail("coder_cycle_limits must be three positive integers")
        coder_cycle_limits = list(limits)
    else:
        coder_cycle_limits = list(DEFAULT_CODER_CYCLE_LIMITS)

    if config.get("publication") not in PUBLICATIONS:
        _fail("publication must be one of %s; it is an explicit "
              "launch-time choice" % (list(PUBLICATIONS),))
    _positive_int(config["max_parallel"], "max_parallel")
    timeout = config["dispatch_timeout_seconds"]
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        _fail("dispatch_timeout_seconds must be a number")
    if not timeout > 0:
        _fail("dispatch_timeout_seconds must be positive")

    normalized = {
        "version": VERSION,
        "backend": backend,
        "roles": normalized_roles,
        "toolchains": copy.deepcopy(toolchains),
        "retention_days": retention_days,
        "coder_cycle_limits": coder_cycle_limits,
        "publication": config["publication"],
        "max_parallel": config["max_parallel"],
        "dispatch_timeout_seconds": timeout,
    }

    if "plan_path" in config:
        normalized["plan_path"] = _nonempty_string(config["plan_path"],
                                                   "plan_path")
    if "run_id" in config:
        normalized["run_id"] = _nonempty_string(config["run_id"], "run_id")

    if "confirmation" in config:
        confirmation = config["confirmation"]
        if not isinstance(confirmation, dict):
            _fail("confirmation must be an object")
        confirmed = confirmation.get("confirmed", False)
        if not isinstance(confirmed, bool):
            _fail("confirmation.confirmed must be a boolean")
        if confirmed:
            # The hash binds the effective (normalized) selection, so
            # normalization-added defaults stay transparent: verifying
            # after defaulting makes confirmation idempotent across
            # load -> probe passes over the same selection.
            expected = configuration_hash(normalized)
            actual = confirmation.get("configuration_hash")
            if actual != expected:
                _fail("confirmation.configuration_hash does not match "
                      "the current backend/roles; re-confirm the selection")
            _nonempty_string(confirmation.get("provenance"),
                             "confirmation.provenance")
            normalized["confirmation"] = {
                "confirmed": True,
                "configuration_hash": actual,
                "provenance": confirmation["provenance"],
            }
        else:
            normalized["confirmation"] = {"confirmed": False}
    return normalized


def load_runtime(path):
    """Load and strictly validate the runtime configuration at *path*."""
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except FileNotFoundError:
        raise RuntimeConfigError("no such configuration file: %s" % path)
    except OSError as exc:
        raise RuntimeConfigError(
            "cannot read configuration file %s: %s" % (path, exc))
    except ValueError as exc:
        raise RuntimeConfigError(
            "configuration file %s is not valid JSON: %s" % (path, exc))
    return normalize_config(raw)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="pipeline_config")
    parser.add_argument("--validate", required=True,
                        help="runtime configuration file to validate")
    args = parser.parse_args(argv)
    try:
        config = load_runtime(args.validate)
    except RuntimeConfigError as exc:
        print("pipeline_config: invalid configuration: %s" % exc,
              file=sys.stderr)
        return 2
    print(json.dumps(config, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
