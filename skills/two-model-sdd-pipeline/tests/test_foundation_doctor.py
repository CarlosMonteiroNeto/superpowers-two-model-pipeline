"""Black-box tests for backend capability reports (Round 1 Task 2).

Contracts under test:
  skills/two-model-sdd-pipeline/scripts/codex_capabilities.py
    codex_capabilities.inspect_runtime(config: dict, project: str) -> dict
  skills/two-model-sdd-pipeline/scripts/opencode_capabilities.py
    opencode_capabilities.inspect_runtime(config: dict, project: str) -> dict
  skills/two-model-sdd-pipeline/scripts/pipeline-doctor
    pipeline-doctor --config FILE --project DIR --output REPORT
    exit 0 ready, 2 invalid input, 3 unavailable capability.

Acceptance encoded here: actual executable/help/version probes per backend
(fake binaries on a private PATH, no live calls); Windows launcher
discovery distinguishes native executables from PowerShell wrappers; Codex
and OpenCode setting/event/session semantics stay separate; unknown live
model/auth/policy support is recorded as unverified and reports never
expose credentials; immutable manifest bindings (backend/config/bundle/
role hashes, executable/version, project identity, canonical plan and run
identity) with no fallback to the other backend; the doctor never installs,
upgrades, dispatches, or edits user config.

Expectations are hand-derived literals. Binaries and configs are fixtures
built in disposable directories; the modules run in fresh interpreters and
the doctor runs as a real process.
"""
import hashlib
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

SKILL = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"

INSPECT_SNIPPET = (
    "import sys, json; "
    "sys.path.insert(0, %r); " % str(SCRIPTS) +
    "import {module}; "
    "config = json.load(open(sys.argv[1], encoding='utf-8')); "
    "report = {module}.inspect_runtime(config, sys.argv[2]); "
    "print(json.dumps(report, sort_keys=True))"
)

GIT = shutil.which("git") or "git"


def canonical_hash(value):
    """Independent canonical hash (hashlib only, never the code under test)."""
    canonical = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def effective_body(config):
    """Apply the documented defaults independently of the module: the
    director defaults to the reviewer copy and budgets default to
    [5,3,3]/30. The confirmation hash binds this effective selection."""
    import copy
    body = {key: value for key, value in config.items()
            if key != "confirmation"}
    roles = dict(body["roles"])
    if "director" not in roles:
        roles["director"] = copy.deepcopy(roles["reviewer"])
    body["roles"] = roles
    body.setdefault("retention_days", 30)
    body.setdefault("coder_cycle_limits", [5, 3, 3])
    return body


def codex_config(confirmed=True):
    config = {
        "version": 1,
        "backend": "codex",
        "roles": {
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
        },
        "toolchains": {"python": {}},
        "retention_days": 30,
        "coder_cycle_limits": [5, 3, 3],
        "publication": "local",
        "max_parallel": 2,
        "dispatch_timeout_seconds": 600,
    }
    if confirmed:
        config["confirmation"] = {
            "confirmed": True,
            "configuration_hash": canonical_hash(effective_body(config)),
            "provenance": "interactive-launch 2026-09-26",
        }
    return config


def opencode_config(confirmed=True):
    config = {
        "version": 1,
        "backend": "opencode",
        "roles": {
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
        },
        "toolchains": {"python": {}},
        "retention_days": 30,
        "coder_cycle_limits": [5, 3, 3],
        "publication": "pull_request",
        "max_parallel": 1,
        "dispatch_timeout_seconds": 300,
    }
    if confirmed:
        config["confirmation"] = {
            "confirmed": True,
            "configuration_hash": canonical_hash(effective_body(config)),
            "provenance": "interactive-launch 2026-09-26",
        }
    return config


class DoctorBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="foundation-doctor-")
        self.tmp = pathlib.Path(self._tmp)
        self.bindir = self.tmp / "bin"
        self.bindir.mkdir()
        self.project = self.tmp / "project"
        self.project.mkdir()
        (self.project / "file.txt").write_text("work\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    # --- fixtures ---

    def write_config(self, config, name="runtime.json"):
        path = self.tmp / name
        path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        return path

    def write_stub(self, name, per_os):
        """Write a runnable fake backend binary.

        per_os is (posix_body, windows_body). The POSIX stub logs its argv
        to $FAKE_LOG so tests can prove the doctor never launches a model.
        """
        path = self.bindir / name
        if os.name == "nt":
            path = self.bindir / (name + ".cmd")
            path.write_text(per_os[1], encoding="utf-8")
        else:
            path.write_text(per_os[0], encoding="utf-8")
            path.chmod(path.stat().st_mode
                       | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return path

    def codex_stub(self, log=None, help_text=None, version_text=None):
        version_text = version_text or "codex-cli 0.156.1"
        help_text = help_text or "usage: codex exec --json --help"
        posix = ("#!/usr/bin/env bash\n"
                 "echo \"$*\" >> \"${FAKE_LOG:-/dev/null}\"\n"
                 "if [ \"$1\" = \"--version\" ]; then echo \"%s\"; exit 0; fi\n"
                 "if [ \"$1\" = \"--help\" ]; then echo \"%s\"; exit 0; fi\n"
                 "exit 0\n" % (version_text, help_text))
        windows = ("@echo off\r\n"
                   "if defined FAKE_LOG echo %%*>>\"%%FAKE_LOG%%\"\r\n"
                   "if \"%%1\"==\"--version\" (echo %s& exit /b 0)\r\n"
                   "if \"%%1\"==\"--help\" (echo %s& exit /b 0)\r\n"
                   "exit /b 0\r\n" % (version_text, help_text))
        return self.write_stub("codex", (posix, windows))

    def opencode_stub(self, log=None, help_text=None, version_text=None):
        version_text = version_text or "opencode 0.1.0"
        help_text = help_text or "usage: opencode run --agent NAME --format json"
        posix = ("#!/usr/bin/env bash\n"
                 "echo \"$*\" >> \"${FAKE_LOG:-/dev/null}\"\n"
                 "if [ \"$1\" = \"--version\" ]; then echo \"%s\"; exit 0; fi\n"
                 "if [ \"$1\" = \"--help\" ]; then echo \"%s\"; exit 0; fi\n"
                 "exit 0\n" % (version_text, help_text))
        windows = ("@echo off\r\n"
                   "if defined FAKE_LOG echo %%*>>\"%%FAKE_LOG%%\"\r\n"
                   "if \"%%1\"==\"--version\" (echo %s& exit /b 0)\r\n"
                   "if \"%%1\"==\"--help\" (echo %s& exit /b 0)\r\n"
                   "exit /b 0\r\n" % (version_text, help_text))
        return self.write_stub("opencode", (posix, windows))

    # --- runners ---

    def env_with_bin(self, extra=None):
        env = dict(os.environ)
        env["PATH"] = str(self.bindir)
        fake_home = self.tmp / "home"
        fake_home.mkdir(exist_ok=True)
        env["HOME"] = str(fake_home)
        env["USERPROFILE"] = str(fake_home)
        if extra:
            env.update(extra)
        return env

    def run_inspect(self, module, config, project=None, env=None):
        config_path = self.write_config(
            config, name="inspect-%s.json" % module)
        code = INSPECT_SNIPPET.format(module=module)
        return subprocess.run(
            [sys.executable, "-c", code, str(config_path),
             str(project or self.project)],
            capture_output=True, text=True,
            env=env or self.env_with_bin(),
        )

    def inspect_ok(self, module, config, project=None, env=None):
        result = self.run_inspect(module, config, project, env)
        self.assertEqual(
            result.returncode, 0,
            "%s.inspect_runtime must accept the fixture: " % module
            + result.stdout + result.stderr,
        )
        return json.loads(result.stdout)

    def run_doctor(self, config_path, project=None, output=None, env=None):
        report = output or (self.tmp / "report.json")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "pipeline-doctor"),
             "--config", str(config_path),
             "--project", str(project or self.project),
             "--output", str(report)],
            capture_output=True, text=True,
            env=env or self.env_with_bin(),
        )
        return result, report


class TestCapabilityProbes(DoctorBase):
    def test_codex_probes_real_executable_help_and_version(self):
        self.codex_stub()
        report = self.inspect_ok("codex_capabilities", codex_config())
        exe = report["executable"]
        self.assertTrue(exe["available"], "the fake codex must be found")
        self.assertIn("0.156.1", exe["version"])
        self.assertTrue(exe["options_supported"])
        self.assertEqual(report["backend"], "codex")

    def test_opencode_probes_real_executable_help_and_version(self):
        self.opencode_stub()
        report = self.inspect_ok("opencode_capabilities", opencode_config())
        exe = report["executable"]
        self.assertTrue(exe["available"], "the fake opencode must be found")
        self.assertIn("0.1.0", exe["version"])
        self.assertTrue(exe["options_supported"])
        self.assertEqual(report["backend"], "opencode")

    def test_missing_binary_is_reported_unavailable(self):
        report = self.inspect_ok("codex_capabilities", codex_config())
        self.assertFalse(report["executable"]["available"])
        self.assertIsNone(report["executable"]["version"])
        self.assertIsNone(report["executable"]["path"])

    def test_help_without_required_options_is_unsupported(self):
        self.codex_stub(help_text="usage: codex frobnicate")
        report = self.inspect_ok("codex_capabilities", codex_config())
        self.assertTrue(report["executable"]["available"])
        self.assertFalse(report["executable"]["options_supported"])

    def test_native_executable_preferred_over_powershell_wrapper(self):
        (self.bindir / "codex.ps1").write_text(
            "Write-Host codex", encoding="utf-8")
        (self.bindir / "codex.exe").write_text("native", encoding="utf-8")
        report = self.inspect_ok("codex_capabilities", codex_config())
        self.assertEqual(report["executable"]["kind"], "native")
        self.assertTrue(
            report["executable"]["path"].endswith("codex.exe"),
            "the native executable must win: %s"
            % report["executable"]["path"])

    def test_powershell_wrapper_kind_is_distinguished(self):
        (self.bindir / "codex.ps1").write_text(
            "Write-Host codex", encoding="utf-8")
        report = self.inspect_ok("codex_capabilities", codex_config())
        self.assertEqual(report["executable"]["kind"], "powershell-wrapper")

    def test_backend_mismatch_never_falls_back(self):
        result = self.run_inspect("opencode_capabilities", codex_config())
        self.assertNotEqual(
            result.returncode, 0,
            "the opencode adapter must refuse a codex config, never "
            "fall back: " + result.stdout)
        result = self.run_inspect("codex_capabilities", opencode_config())
        self.assertNotEqual(
            result.returncode, 0,
            "the codex adapter must refuse an opencode config: "
            + result.stdout)


class TestSeparateSemantics(DoctorBase):
    def test_codex_and_opencode_event_session_settings_differ(self):
        self.codex_stub()
        self.opencode_stub()
        codex = self.inspect_ok("codex_capabilities", codex_config())
        opencode = self.inspect_ok("opencode_capabilities", opencode_config())
        self.assertIn("thread.started", codex["events"])
        self.assertEqual(codex["session"]["kind"], "codex-thread")
        self.assertEqual(opencode["session"]["kind"], "opencode-session")
        self.assertNotEqual(codex["events"], opencode["events"],
                            "adapters must keep their event semantics separate")
        self.assertNotEqual(codex["session"]["kind"],
                            opencode["session"]["kind"])

    def test_live_support_stays_unverified_with_binary_present(self):
        self.codex_stub()
        report = self.inspect_ok("codex_capabilities", codex_config())
        live = report["live"]
        self.assertEqual(live["model"], "unverified")
        self.assertEqual(live["auth"], "unverified")
        self.assertEqual(live["policy"], "unverified")
        self.assertIn("do not certify", live["note"])

    def test_reports_never_expose_credentials(self):
        self.codex_stub()
        env = self.env_with_bin(extra={
            "CODEX_API_KEY": "super-secret-codex-xyz",
            "OPENCODE_API_KEY": "super-secret-opencode-xyz",
        })
        report = self.inspect_ok("codex_capabilities", codex_config(),
                                 env=env)
        blob = json.dumps(report, sort_keys=True)
        self.assertNotIn("super-secret-codex-xyz", blob)
        self.assertNotIn("super-secret-opencode-xyz", blob)
        self.assertFalse(report["credentials_exposed"])


class TestManifestBindings(DoctorBase):
    def test_manifest_binds_config_bundle_roles_and_identities(self):
        self.codex_stub()
        config = codex_config()
        report = self.inspect_ok("codex_capabilities", config)
        manifest = report["manifest"]
        body = {key: value for key, value in config.items()
                if key != "confirmation"}
        self.assertEqual(manifest["backend"], "codex")
        self.assertEqual(manifest["config_hash"], canonical_hash(body))
        self.assertEqual(
            manifest["role_hashes"]["operator"],
            canonical_hash(config["roles"]["operator"]))
        self.assertEqual(
            manifest["role_hashes"]["reviewer"],
            canonical_hash(config["roles"]["reviewer"]))
        for digest in [manifest["config_hash"], manifest["bundle_hash"],
                       manifest["role_hashes"]["operator"]]:
            self.assertEqual(len(digest), 64, "hashes are sha256 hex")
        self.assertEqual(manifest["executable_version"], "codex-cli 0.156.1")
        self.assertEqual(
            pathlib.Path(manifest["project_path"]).resolve(),
            self.project.resolve())

    def test_manifest_records_git_head_and_run_identity(self):
        self.codex_stub()
        repo = self.tmp / "repo"
        repo.mkdir()
        subprocess.run([GIT, "init", "-q"], cwd=str(repo), check=True)
        subprocess.run([GIT, "config", "user.email", "t@example.com"],
                       cwd=str(repo), check=True)
        subprocess.run([GIT, "config", "user.name", "T"], cwd=str(repo),
                       check=True)
        (repo / "file.txt").write_text("x\n", encoding="utf-8")
        subprocess.run([GIT, "add", "-A"], cwd=str(repo), check=True)
        subprocess.run([GIT, "commit", "-qm", "base"], cwd=str(repo),
                       check=True)
        head = subprocess.run(
            [GIT, "rev-parse", "HEAD"], cwd=str(repo),
            capture_output=True, text=True).stdout.strip()
        config = codex_config()
        config["plan_path"] = "docs/superpowers/plans/demo-plan.json"
        config["run_id"] = "run-001"
        config["confirmation"]["configuration_hash"] = canonical_hash(
            effective_body(config))
        # The hermetic probe PATH hides git; re-expose the system PATH
        # behind the fake bindir (the stub still wins executable
        # discovery by PATH order).
        env = self.env_with_bin()
        env["PATH"] = (str(self.bindir) + os.pathsep
                       + os.environ.get("PATH", ""))
        report = self.inspect_ok("codex_capabilities", config, project=repo,
                                 env=env)
        manifest = report["manifest"]
        self.assertEqual(manifest["project_git_head"], head)
        self.assertEqual(manifest["plan_path"],
                         "docs/superpowers/plans/demo-plan.json")
        self.assertEqual(manifest["run_id"], "run-001")

    def test_unconfirmed_config_exposes_needs_configuration(self):
        self.codex_stub()
        report = self.inspect_ok("codex_capabilities",
                                 codex_config(confirmed=False))
        self.assertTrue(report["needs_configuration"])
        ready = self.inspect_ok("codex_capabilities", codex_config())
        self.assertFalse(ready["needs_configuration"])


class TestPipelineDoctorCli(DoctorBase):
    def test_ready_codex_config_exits_zero(self):
        self.codex_stub()
        config_path = self.write_config(codex_config())
        result, report_path = self.run_doctor(config_path)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["backend"], "codex")
        self.assertFalse(report["needs_configuration"])

    def test_ready_opencode_config_exits_zero(self):
        self.opencode_stub()
        config_path = self.write_config(opencode_config())
        result, report_path = self.run_doctor(config_path)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["backend"], "opencode")

    def test_missing_config_file_exits_two(self):
        result, _ = self.run_doctor(self.tmp / "nope.json")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_invalid_config_exits_two(self):
        config = codex_config()
        config["backend"] = "anthropic"
        result, _ = self.run_doctor(self.write_config(config))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_unconfirmed_config_exits_three(self):
        self.codex_stub()
        config_path = self.write_config(codex_config(confirmed=False))
        result, report_path = self.run_doctor(config_path)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertTrue(report["needs_configuration"])

    def test_missing_binary_exits_three(self):
        config_path = self.write_config(codex_config())
        result, report_path = self.run_doctor(config_path)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertFalse(report["executable"]["available"])

    def test_unsupported_options_exit_three(self):
        self.codex_stub(help_text="usage: codex frobnicate")
        config_path = self.write_config(codex_config())
        result, _ = self.run_doctor(config_path)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)

    def test_doctor_never_edits_config_or_project(self):
        self.codex_stub()
        config_path = self.write_config(codex_config())
        before_config = config_path.read_bytes()
        before_project = sorted(
            str(path.relative_to(self.project))
            for path in self.project.rglob("*"))
        out = self.tmp / "out" / "report.json"
        result, _ = self.run_doctor(config_path, output=out)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(config_path.read_bytes(), before_config)
        after_project = sorted(
            str(path.relative_to(self.project))
            for path in self.project.rglob("*"))
        self.assertEqual(after_project, before_project)
        self.assertTrue(out.is_file())

    def test_doctor_never_launches_a_model(self):
        log = self.tmp / "invocations.log"
        log.write_text("", encoding="utf-8")
        self.codex_stub()
        config_path = self.write_config(codex_config())
        result, _ = self.run_doctor(
            config_path, env=self.env_with_bin(
                extra={"FAKE_LOG": str(log)}))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = log.read_text(encoding="utf-8")
        self.assertNotIn("exec", calls)
        self.assertIn("--version", calls)
        self.assertIn("--help", calls)

    def test_doctor_report_hides_credentials(self):
        self.codex_stub()
        config_path = self.write_config(codex_config())
        result, report_path = self.run_doctor(
            config_path, env=self.env_with_bin(extra={
                "CODEX_API_KEY": "super-secret-codex-xyz",
            }))
        self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
        blob = report_path.read_text(encoding="utf-8")
        self.assertNotIn("super-secret-codex-xyz", blob)
        self.assertNotIn("super-secret-codex-xyz", result.stdout + result.stderr)

    def test_doctor_handles_project_dir_with_spaces(self):
        self.codex_stub()
        spaced = self.tmp / "dir with spaces" / "proj"
        spaced.mkdir(parents=True)
        (spaced / "file.txt").write_text("x\n", encoding="utf-8")
        config_path = self.write_config(codex_config())
        result, _ = self.run_doctor(config_path, project=spaced)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_doctor_usage_error_exits_two(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "pipeline-doctor")],
            capture_output=True, text=True, env=self.env_with_bin(),
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
