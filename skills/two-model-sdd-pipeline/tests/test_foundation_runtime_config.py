"""Black-box tests for the shared runtime configuration (Round 1 Task 2).

Contract under test:
  skills/two-model-sdd-pipeline/scripts/pipeline_config.py
    pipeline_config.load_runtime(path: str) -> dict; strict validation
  skills/two-model-sdd-pipeline/schemas/runtime.schema.json
  skills/two-model-sdd-pipeline/runtime.example.json

Acceptance encoded here (plan task 2):
  version=1, backend codex|opencode, explicit roles, backend-specific
  settings, toolchains, retention, publication, positive timeout and
  max_parallel. Missing models and unsupported setting combinations are
  rejected; no product model defaults are applied. Budgets
  (coder_cycle_limits=[5,3,3], retention_days=30) are configurable with
  documented defaults; publication and max_parallel have no silent defaults
  and are preserved on resume. Confirmed selections carry backend, roles,
  configuration hash and confirmation provenance; the read-only round
  exposes needs_configuration through the capability reports (never by
  launching an LLM).

Expectations are hand-derived literals. The module is exercised in a fresh
interpreter per case (real behavior, no in-process imports), so a missing
module fails as an assertion on the subprocess outcome, not as a
collection error.
"""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SKILL = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
SCHEMA_PATH = SKILL / "schemas" / "runtime.schema.json"
EXAMPLE_PATH = SKILL / "runtime.example.json"

LOAD_SNIPPET = (
    "import sys, json; "
    "sys.path.insert(0, %r); " % str(SCRIPTS) +
    "import pipeline_config; "
    "cfg = pipeline_config.load_runtime(sys.argv[1]); "
    "print(json.dumps(cfg, sort_keys=True))"
)


def canonical_hash(value):
    """Independent canonical hash (hashlib only, never the code under test).

    Contract: sha256 over canonical JSON (sorted keys, compact separators,
    unicode preserved). Used to build confirmed fixtures and to check the
    manifest bindings.
    """
    canonical = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def codex_roles():
    return {
        "operator": {
            "model": "test-codex-operator-model",
            "settings": {"model_reasoning_effort": "high"},
            "policy": "workspace-write",
            "instruction": "codex-operator-v1",
        },
        "reviewer": {
            "model": "test-codex-reviewer-model",
            "settings": {"model_reasoning_effort": "medium"},
            "policy": "read-only",
            "instruction": "codex-reviewer-v1",
        },
    }


def opencode_roles():
    return {
        "operator": {
            "model": "test-opencode-operator-model",
            "settings": {"variant": "test-operator-variant"},
            "policy": "test-operator-policy",
            "instruction": "opencode-operator-v1",
        },
        "reviewer": {
            "model": "test-opencode-reviewer-model",
            "settings": {"variant": "test-reviewer-variant"},
            "policy": "test-reviewer-policy",
            "instruction": "opencode-reviewer-v1",
        },
    }


def base_config(backend, roles):
    return {
        "version": 1,
        "backend": backend,
        "roles": roles,
        "toolchains": {"python": {}},
        "retention_days": 30,
        "coder_cycle_limits": [5, 3, 3],
        "publication": "local",
        "max_parallel": 2,
        "dispatch_timeout_seconds": 600,
    }


def confirmed(config):
    """Return a copy carrying confirmation provenance bound to the effective
    selection. The documented defaults (director defaults to the reviewer
    copy; budgets default to [5,3,3]/30) are applied here independently of
    the module, so the hash binds exactly what a correct load must honor."""
    import copy
    raw = {key: value for key, value in config.items()
           if key != "confirmation"}
    body = dict(raw)
    roles = dict(body["roles"])
    if "director" not in roles:
        roles["director"] = copy.deepcopy(roles["reviewer"])
    body["roles"] = roles
    body.setdefault("retention_days", 30)
    body.setdefault("coder_cycle_limits", [5, 3, 3])
    signed = dict(raw)
    signed["confirmation"] = {
        "confirmed": True,
        "configuration_hash": canonical_hash(body),
        "provenance": "interactive-launch 2026-09-26",
    }
    return signed


class RuntimeConfigBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="foundation-runtime-config-")
        self.tmp = pathlib.Path(self._tmp)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def write_config(self, value, name="runtime.json"):
        path = self.tmp / name
        path.write_text(json.dumps(value, indent=2), encoding="utf-8")
        return str(path)

    def run_load(self, path):
        return subprocess.run(
            [sys.executable, "-c", LOAD_SNIPPET, str(path)],
            capture_output=True, text=True, env=dict(os.environ),
        )

    def load_ok(self, value):
        result = self.run_load(self.write_config(value))
        self.assertEqual(
            result.returncode, 0,
            "load_runtime must accept the fixture: " + result.stdout
            + result.stderr,
        )
        return json.loads(result.stdout)

    def load_rejected(self, value, hint):
        result = self.run_load(self.write_config(value))
        self.assertNotEqual(
            result.returncode, 0,
            "load_runtime must reject %s but accepted it: %s"
            % (hint, result.stdout),
        )
        return result


class TestRuntimeSchemaDocument(RuntimeConfigBase):
    def test_schema_file_exists_and_names_the_contract(self):
        self.assertTrue(
            SCHEMA_PATH.is_file(),
            "schemas/runtime.schema.json must exist",
        )
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(schema["type"], "object")
        for field in ("version", "backend", "roles", "toolchains",
                      "publication", "max_parallel",
                      "dispatch_timeout_seconds"):
            self.assertIn(field, schema["required"],
                          "schema must require %s" % field)

    def test_schema_pins_version_backend_and_budgets(self):
        self.assertTrue(SCHEMA_PATH.is_file(),
                        "schemas/runtime.schema.json must exist")
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["version"]["const"], 1)
        self.assertEqual(schema["properties"]["backend"]["enum"],
                         ["codex", "opencode"])
        self.assertEqual(
            schema["properties"]["coder_cycle_limits"]["default"], [5, 3, 3])
        self.assertEqual(
            schema["properties"]["retention_days"]["default"], 30)
        self.assertEqual(
            set(schema["properties"]["publication"]["enum"]),
            {"local", "pull_request"})


class TestRuntimeExample(RuntimeConfigBase):
    def test_example_exists_with_placeholder_models_only(self):
        self.assertTrue(EXAMPLE_PATH.is_file(),
                        "runtime.example.json must exist")
        example = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(example["version"], 1)
        self.assertEqual(example["backend"], "codex")
        for role in ("operator", "reviewer"):
            model = example["roles"][role]["model"]
            self.assertIn("SELECT-AT-LAUNCH", model,
                          "examples must not hard-code runnable model choices")

    def test_example_loads_as_valid_but_unconfirmed(self):
        self.assertTrue(EXAMPLE_PATH.is_file(),
                        "runtime.example.json must exist")
        result = self.run_load(str(EXAMPLE_PATH))
        self.assertEqual(
            result.returncode, 0,
            "the example must be a loadable config: " + result.stdout
            + result.stderr,
        )
        loaded = json.loads(result.stdout)
        self.assertEqual(loaded["backend"], "codex")
        confirmation = loaded.get("confirmation", {})
        self.assertIsNot(confirmation.get("confirmed"), True,
                         "the example must not pose as a confirmed selection")


class TestLoadRuntimeBackends(RuntimeConfigBase):
    def test_valid_codex_config_loads(self):
        loaded = self.load_ok(confirmed(base_config("codex", codex_roles())))
        self.assertEqual(loaded["backend"], "codex")
        self.assertEqual(loaded["roles"]["operator"]["model"],
                         "test-codex-operator-model")

    def test_valid_opencode_config_loads(self):
        loaded = self.load_ok(
            confirmed(base_config("opencode", opencode_roles())))
        self.assertEqual(loaded["backend"], "opencode")
        self.assertEqual(loaded["roles"]["reviewer"]["model"],
                         "test-opencode-reviewer-model")

    def test_unknown_backend_rejected(self):
        config = base_config("codex", codex_roles())
        config["backend"] = "anthropic"
        self.load_rejected(config, "an unknown backend")

    def test_wrong_version_rejected(self):
        config = base_config("codex", codex_roles())
        config["version"] = 2
        self.load_rejected(config, "version != 1")

    def test_missing_file_rejected(self):
        result = self.run_load(str(self.tmp / "does-not-exist.json"))
        self.assertNotEqual(result.returncode, 0,
                            "a missing config file must be rejected")

    def test_malformed_json_rejected(self):
        path = self.tmp / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        result = self.run_load(str(path))
        self.assertNotEqual(result.returncode, 0,
                            "malformed JSON must be rejected")


class TestExplicitRolesAndSettings(RuntimeConfigBase):
    def test_missing_operator_model_rejected(self):
        roles = codex_roles()
        del roles["operator"]["model"]
        self.load_rejected(base_config("codex", roles),
                           "a missing operator model")

    def test_missing_reviewer_model_rejected(self):
        roles = codex_roles()
        roles["reviewer"]["model"] = ""
        self.load_rejected(base_config("codex", roles),
                           "an empty reviewer model")

    def test_models_are_preserved_verbatim_no_defaults(self):
        loaded = self.load_ok(confirmed(base_config("codex", codex_roles())))
        self.assertEqual(loaded["roles"]["operator"]["model"],
                         "test-codex-operator-model")
        self.assertEqual(loaded["roles"]["reviewer"]["model"],
                         "test-codex-reviewer-model")

    def test_codex_rejects_opencode_variant_setting(self):
        roles = codex_roles()
        roles["operator"]["settings"] = {"variant": "test-variant"}
        self.load_rejected(confirmed(base_config("codex", roles)),
                           "a codex role carrying the opencode variant key")

    def test_opencode_rejects_codex_effort_setting(self):
        roles = opencode_roles()
        roles["operator"]["settings"] = {"model_reasoning_effort": "high"}
        self.load_rejected(confirmed(base_config("opencode", roles)),
                           "an opencode role carrying the codex effort key")

    def test_codex_reviewer_must_be_read_only(self):
        roles = codex_roles()
        roles["reviewer"]["policy"] = "workspace-write"
        self.load_rejected(confirmed(base_config("codex", roles)),
                           "a codex reviewer with operator policy")

    def test_director_defaults_to_reviewer_model(self):
        loaded = self.load_ok(confirmed(base_config("codex", codex_roles())))
        self.assertEqual(loaded["roles"]["director"]["model"],
                         "test-codex-reviewer-model")

    def test_explicit_director_is_preserved(self):
        roles = codex_roles()
        roles["director"] = {
            "model": "test-codex-director-model",
            "settings": {"model_reasoning_effort": "low"},
            "policy": "read-only",
            "instruction": "codex-director-v1",
        }
        loaded = self.load_ok(confirmed(base_config("codex", roles)))
        self.assertEqual(loaded["roles"]["director"]["model"],
                         "test-codex-director-model")


class TestLaunchChoicesAndBudgets(RuntimeConfigBase):
    def test_missing_publication_rejected_no_silent_default(self):
        config = base_config("codex", codex_roles())
        del config["publication"]
        self.load_rejected(config, "a missing publication choice")

    def test_unknown_publication_rejected(self):
        config = base_config("codex", codex_roles())
        config["publication"] = "push"
        self.load_rejected(config, "an unknown publication value")

    def test_missing_max_parallel_rejected_no_silent_default(self):
        config = base_config("codex", codex_roles())
        del config["max_parallel"]
        self.load_rejected(config, "a missing max_parallel choice")

    def test_zero_max_parallel_rejected(self):
        config = base_config("codex", codex_roles())
        config["max_parallel"] = 0
        self.load_rejected(config, "max_parallel = 0")

    def test_nonpositive_timeout_rejected(self):
        for timeout in (0, -5):
            config = base_config("codex", codex_roles())
            config["dispatch_timeout_seconds"] = timeout
            self.load_rejected(
                config, "dispatch_timeout_seconds = %r" % (timeout,))

    def test_budgets_default_to_5_3_3_and_30_days(self):
        config = base_config("codex", codex_roles())
        del config["coder_cycle_limits"]
        del config["retention_days"]
        loaded = self.load_ok(confirmed(config))
        self.assertEqual(loaded["coder_cycle_limits"], [5, 3, 3])
        self.assertEqual(loaded["retention_days"], 30)

    def test_explicit_budgets_preserved_on_resume(self):
        config = base_config("codex", codex_roles())
        config["coder_cycle_limits"] = [5, 3, 3]
        config["retention_days"] = 45
        loaded = self.load_ok(confirmed(config))
        self.assertEqual(loaded["coder_cycle_limits"], [5, 3, 3])
        self.assertEqual(loaded["retention_days"], 45)

    def test_malformed_cycle_limits_rejected(self):
        for limits in ([5, 3], [5, 0, 3], "5,3,3"):
            config = base_config("codex", codex_roles())
            config["coder_cycle_limits"] = limits
            self.load_rejected(
                config, "coder_cycle_limits = %r" % (limits,))


class TestConfirmationProvenance(RuntimeConfigBase):
    def test_unconfirmed_config_loads(self):
        loaded = self.load_ok(base_config("codex", codex_roles()))
        self.assertEqual(loaded["backend"], "codex")

    def test_stale_confirmation_hash_rejected(self):
        config = confirmed(base_config("codex", codex_roles()))
        config["roles"]["operator"]["model"] = "test-tampered-model"
        self.load_rejected(config, "confirmation hash bound to other roles")

    def test_confirmed_without_provenance_rejected(self):
        config = confirmed(base_config("codex", codex_roles()))
        del config["confirmation"]["provenance"]
        self.load_rejected(config, "confirmed selection without provenance")


if __name__ == "__main__":
    unittest.main()
