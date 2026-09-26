"""Black-box tests for project harness binding (Round 1 Task 4).

Contract under test:
  skills/two-model-sdd-pipeline/scripts/harness-project
    harness-project init --project DIR --bundle ID --backend NAME
  skills/two-model-sdd-pipeline/scripts/harness_install.py
    harness_install.resolve_bundle(project: str) -> dict

Acceptance encoded here (plan task 4):
  init writes a versioned .superpowers/harness.json and idempotently
  merges a marked AGENTS.md section while preserving existing user
  instructions; it touches only the given project and never scans or
  alters unrelated projects; the binding records the bundle hash, the
  backend configuration and policy references through relocatable
  identities; a missing pin is diagnosed without falling back to the
  newest installation; two pinned projects keep their own bundles while
  the installation selection advances; enrollment is idempotent;
  directory names with spaces are covered.

Expectations are hand-derived literals. The project script runs as a
real process and the module is exercised in a fresh interpreter per
case (real behavior, no in-process imports), so missing files fail as
assertions on the subprocess outcome, not as collection errors.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent.parent
SKILL = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
HARNESS_PROJECT = SCRIPTS / "harness-project"

if os.name == "nt":
    git_bash = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
    BASH = str(git_bash) if git_bash.exists() else "bash"
else:
    BASH = "bash"

STAGE_SNIPPET = (
    "import sys, json; "
    "sys.path.insert(0, %r); " % str(SCRIPTS) +
    "import harness_install; "
    "manifest = harness_install.stage_bundle(sys.argv[1], sys.argv[2], sys.argv[3]); "
    "print(json.dumps(manifest, sort_keys=True))"
)

SELECT_SNIPPET = (
    "import sys, json; "
    "sys.path.insert(0, %r); " % str(SCRIPTS) +
    "import harness_install; "
    "manifest = harness_install.select_bundle(sys.argv[1], sys.argv[2]); "
    "print(json.dumps(manifest, sort_keys=True))"
)

RESOLVE_SNIPPET = (
    "import sys, json; "
    "sys.path.insert(0, %r); " % str(SCRIPTS) +
    "import harness_install; "
    "binding = harness_install.resolve_bundle(sys.argv[1]); "
    "print(json.dumps(binding, sort_keys=True))"
)

REQUIRED_SOURCE_FILES = (
    "skills/two-model-sdd-pipeline/scripts/pipeline_config.py",
    "skills/two-model-sdd-pipeline/scripts/dispatch_contract.py",
    "skills/two-model-sdd-pipeline/schemas/runtime.schema.json",
    "agent/two-model-coder.md",
    "agent/two-model-reviewer.md",
    "agent/two-model-task-generator.md",
    "skills/brainstorming/SKILL.md",
    "skills/two-model-sdd-pipeline/SKILL.md",
    "skills/two-model-sdd-pipeline/scripts/run-pipeline",
    "skills/two-model-sdd-pipeline/scripts/task-run",
    "skills/two-model-sdd-pipeline/scripts/harness_install.py",
    "skills/two-model-sdd-pipeline/scripts/harness-project",
    "skills/using-superpowers/SKILL.md",
    "skills/test-driven-development/SKILL.md",
    "scripts/install-superpowers",
    "scripts/sync-superpowers",
    "hooks/session-start",
    ".codex-plugin/plugin.json",
    ".opencode/INSTALL.md",
    "docs/superpowers/specs/2026-09-25-codex-pipeline-design.md",
    "RELEASE-NOTES.md",
    "README.md",
    "LICENSE",
)

AGENTS_START = "<!-- superpowers-harness:start -->"
AGENTS_END = "<!-- superpowers-harness:end -->"


def run_python_snippet(snippet, args, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-c", snippet, *args],
        capture_output=True,
        text=True,
        env=env,
    )


def run_harness_project(args, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(HARNESS_PROJECT), *args],
        capture_output=True,
        text=True,
        env=env,
    )


class ProjectBindingBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="foundation-project-binding-")
        self.tmp = pathlib.Path(self._tmp)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def make_source(self, name="source"):
        source = self.tmp / name
        for rel in REQUIRED_SOURCE_FILES:
            path = source / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "fixture content for %s from %s\n" % (rel, name),
                encoding="utf-8")
        scripts = source / "skills" / "two-model-sdd-pipeline" / "scripts"
        shutil.copyfile(SCRIPTS / "harness_install.py",
                        scripts / "harness_install.py")
        shutil.copyfile(HARNESS_PROJECT, scripts / "harness-project")
        return source

    def make_store(self, name="store", bundles=("bundle-one",)):
        """Stage and select fixture bundles; return (store, manifests)."""
        store = self.tmp / name
        manifests = {}
        for bundle_id in bundles:
            source = self.make_source(name="source-%s" % bundle_id)
            result = run_python_snippet(
                STAGE_SNIPPET, [str(store), bundle_id, str(source)])
            self.assertEqual(result.returncode, 0, result.stderr)
            result = run_python_snippet(
                SELECT_SNIPPET, [str(store), bundle_id])
            self.assertEqual(result.returncode, 0, result.stderr)
            manifests[bundle_id] = json.loads(result.stdout)
        return store, manifests

    def init_ok(self, project, bundle, backend, store):
        result = run_harness_project(
            ["init", "--project", str(project),
             "--bundle", bundle, "--backend", backend],
            env_extra={"SUPERPOWERS_HARNESS_ROOT": str(store)})
        self.assertEqual(
            result.returncode, 0,
            "init must enroll the project: " + result.stdout + result.stderr)
        return result

    def prepare(self, project, backend, store, *options):
        return run_harness_project(
            ["prepare", "--project", str(project), "--backend", backend,
             "--install-root", str(store), *options])

    def resolve_ok(self, project, store):
        result = run_python_snippet(
            RESOLVE_SNIPPET, [str(project)],
            env_extra={"SUPERPOWERS_HARNESS_ROOT": str(store)})
        self.assertEqual(
            result.returncode, 0,
            "resolve_bundle must accept the pin: " + result.stderr)
        return json.loads(result.stdout)

    def read_pin(self, project):
        return json.loads(
            (project / ".superpowers" / "harness.json").read_text(
                encoding="utf-8"))


class TestHarnessProjectInit(ProjectBindingBase):
    def test_init_writes_versioned_pin(self):
        store, manifests = self.make_store()
        project = self.tmp / "project"
        self.init_ok(project, "bundle-one", "codex", store)
        pin = self.read_pin(project)
        self.assertEqual(pin["version"], 1)
        self.assertEqual(pin["bundle"], "bundle-one")
        self.assertEqual(pin["backend"], "codex")
        self.assertEqual(
            pin["bundle_hash"], manifests["bundle-one"]["bundle_hash"])

    def test_init_records_backend_config_and_policy_refs(self):
        store, _ = self.make_store()
        project = self.tmp / "project"
        self.init_ok(project, "bundle-one", "opencode", store)
        pin = self.read_pin(project)
        self.assertIn("backend_config", pin)
        self.assertTrue(pin["backend_config"])
        self.assertIn("opencode", pin["backend_config"])
        self.assertIn("policy_refs", pin)
        self.assertTrue(pin["policy_refs"])

    def test_pin_uses_relocatable_identities(self):
        store, _ = self.make_store()
        project = self.tmp / "project"
        self.init_ok(project, "bundle-one", "codex", store)
        pin = self.read_pin(project)
        flat = json.dumps(pin)
        self.assertNotIn(str(store), flat)
        self.assertNotIn(str(self.tmp), flat)
        for value in [pin["backend_config"]] + list(pin["policy_refs"]):
            self.assertFalse(
                os.path.isabs(value),
                "binding identity must be relocatable: %r" % value)

    def test_init_merges_marked_agents_section(self):
        store, _ = self.make_store()
        project = self.tmp / "project"
        self.init_ok(project, "bundle-one", "codex", store)
        text = (project / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(AGENTS_START, text)
        self.assertIn(AGENTS_END, text)
        self.assertIn("bundle-one", text)
        self.assertIn("codex", text)

    def test_init_preserves_existing_user_instructions(self):
        store, _ = self.make_store()
        project = self.tmp / "project"
        project.mkdir(parents=True)
        user_text = ("# My project\n\nAlways run the linter first.\n"
                     "Never touch the legacy folder.\n")
        (project / "AGENTS.md").write_text(user_text, encoding="utf-8")
        self.init_ok(project, "bundle-one", "codex", store)
        text = (project / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Always run the linter first.", text)
        self.assertIn("Never touch the legacy folder.", text)
        self.assertIn(AGENTS_START, text)

    def test_torn_managed_section_does_not_create_or_change_project_pin(self):
        store, _ = self.make_store()
        project = self.tmp / "project"
        project.mkdir()
        original = "# Team rules\n\n" + AGENTS_START + "\npartial section\n"
        (project / "AGENTS.md").write_text(original, encoding="utf-8")

        result = run_harness_project(
            ["init", "--project", str(project), "--bundle", "bundle-one",
             "--backend", "opencode", "--install-root", str(store)])

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((project / "AGENTS.md").read_text(encoding="utf-8"),
                         original)
        self.assertFalse((project / ".superpowers" / "harness.json").exists())

    def test_init_is_idempotent(self):
        store, _ = self.make_store()
        project = self.tmp / "project"
        self.init_ok(project, "bundle-one", "codex", store)
        first_pin = (project / ".superpowers" / "harness.json").read_bytes()
        first_agents = (project / "AGENTS.md").read_bytes()
        self.init_ok(project, "bundle-one", "codex", store)
        self.assertEqual(
            (project / ".superpowers" / "harness.json").read_bytes(),
            first_pin)
        self.assertEqual((project / "AGENTS.md").read_bytes(), first_agents)
        text = (project / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(text.count(AGENTS_START), 1)
        self.assertEqual(text.count(AGENTS_END), 1)

    def test_init_cannot_bypass_explicit_upgrade_acceptance(self):
        store, _ = self.make_store(bundles=("bundle-one", "bundle-two"))
        project = self.tmp / "project"
        self.init_ok(project, "bundle-one", "opencode", store)
        old_pin = (project / ".superpowers" / "harness.json").read_bytes()
        old_agents = (project / "AGENTS.md").read_bytes()

        result = run_harness_project(
            ["init", "--project", str(project), "--bundle", "bundle-two",
             "--backend", "opencode", "--install-root", str(store)])

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("prepare", result.stderr.lower())
        self.assertEqual(
            (project / ".superpowers" / "harness.json").read_bytes(), old_pin)
        self.assertEqual((project / "AGENTS.md").read_bytes(), old_agents)

    def test_init_touches_only_the_given_project(self):
        store, _ = self.make_store()
        project = self.tmp / "project"
        sibling = self.tmp / "sibling"
        sibling.mkdir()
        (sibling / "AGENTS.md").write_text("sibling notes\n", encoding="utf-8")
        self.init_ok(project, "bundle-one", "codex", store)
        self.assertFalse((sibling / ".superpowers").exists())
        self.assertEqual(
            (sibling / "AGENTS.md").read_text(encoding="utf-8"),
            "sibling notes\n")

    def test_init_rejects_unknown_backend(self):
        store, _ = self.make_store()
        project = self.tmp / "project"
        result = run_harness_project(
            ["init", "--project", str(project),
             "--bundle", "bundle-one", "--backend", "mystery"],
            env_extra={"SUPERPOWERS_HARNESS_ROOT": str(store)})
        self.assertEqual(result.returncode, 2)
        self.assertFalse((project / ".superpowers").exists())

    def test_init_rejects_unstaged_bundle(self):
        store, _ = self.make_store()
        project = self.tmp / "project"
        result = run_harness_project(
            ["init", "--project", str(project),
             "--bundle", "bundle-never-staged", "--backend", "codex"],
            env_extra={"SUPERPOWERS_HARNESS_ROOT": str(store)})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((project / ".superpowers").exists())

    def test_init_under_path_with_spaces(self):
        store = self.tmp / "store with spaces"
        store.mkdir()
        source = self.make_source()
        result = run_python_snippet(
            STAGE_SNIPPET, [str(store), "bundle-one", str(source)])
        self.assertEqual(result.returncode, 0, result.stderr)
        project = self.tmp / "my project"
        self.init_ok(project, "bundle-one", "codex", store)
        pin = self.read_pin(project)
        self.assertEqual(pin["bundle"], "bundle-one")


class TestResolveBundle(ProjectBindingBase):
    def test_resolve_returns_pinned_bundle(self):
        store, manifests = self.make_store()
        project = self.tmp / "project"
        self.init_ok(project, "bundle-one", "codex", store)
        binding = self.resolve_ok(project, store)
        self.assertEqual(binding["bundle_id"], "bundle-one")
        self.assertEqual(
            binding["bundle_hash"], manifests["bundle-one"]["bundle_hash"])
        self.assertEqual(binding["backend"], "codex")
        self.assertTrue(
            pathlib.Path(binding["bundle_dir"]).is_dir())

    def test_missing_pin_is_diagnosed_without_fallback(self):
        store, _ = self.make_store()
        project = self.tmp / "project"
        project.mkdir(parents=True)
        result = run_python_snippet(
            RESOLVE_SNIPPET, [str(project)],
            env_extra={"SUPERPOWERS_HARNESS_ROOT": str(store)})
        self.assertNotEqual(result.returncode, 0)
        combined = (result.stdout + result.stderr).lower()
        self.assertIn("missing pin", combined)
        self.assertNotIn("bundle-one", combined)

    def test_removed_bundle_is_diagnosed(self):
        store, _ = self.make_store()
        project = self.tmp / "project"
        self.init_ok(project, "bundle-one", "codex", store)
        shutil.rmtree(store / ".harness" / "bundles" / "bundle-one")
        result = run_python_snippet(
            RESOLVE_SNIPPET, [str(project)],
            env_extra={"SUPERPOWERS_HARNESS_ROOT": str(store)})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bundle-one", result.stdout + result.stderr)

    def test_tampered_bundle_fails_resolution(self):
        store, _ = self.make_store()
        project = self.tmp / "project"
        self.init_ok(project, "bundle-one", "codex", store)
        bundle_dir = store / ".harness" / "bundles" / "bundle-one"
        (bundle_dir / "README.md").write_text("tampered\n", encoding="utf-8")
        result = run_python_snippet(
            RESOLVE_SNIPPET, [str(project)],
            env_extra={"SUPERPOWERS_HARNESS_ROOT": str(store)})
        self.assertNotEqual(result.returncode, 0)


class TestTwoPinnedProjects(ProjectBindingBase):
    def test_two_projects_keep_their_own_bundles(self):
        store, manifests = self.make_store(
            bundles=("bundle-one", "bundle-two"))
        first = self.tmp / "first project"
        second = self.tmp / "second-project"
        self.init_ok(first, "bundle-one", "codex", store)
        self.init_ok(second, "bundle-two", "opencode", store)
        first_binding = self.resolve_ok(first, store)
        second_binding = self.resolve_ok(second, store)
        self.assertEqual(first_binding["bundle_id"], "bundle-one")
        self.assertEqual(first_binding["backend"], "codex")
        self.assertEqual(second_binding["bundle_id"], "bundle-two")
        self.assertEqual(second_binding["backend"], "opencode")
        self.assertEqual(
            first_binding["bundle_hash"],
            manifests["bundle-one"]["bundle_hash"])
        self.assertEqual(
            second_binding["bundle_hash"],
            manifests["bundle-two"]["bundle_hash"])

    def test_advancing_selection_keeps_existing_pins(self):
        store, _ = self.make_store(bundles=("bundle-one",))
        project = self.tmp / "project"
        self.init_ok(project, "bundle-one", "codex", store)
        before = self.read_pin(project)
        source = self.make_source(name="source-new")
        result = run_python_snippet(
            STAGE_SNIPPET, [str(store), "bundle-new", str(source)])
        self.assertEqual(result.returncode, 0, result.stderr)
        result = run_python_snippet(SELECT_SNIPPET, [str(store), "bundle-new"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read_pin(project), before)
        binding = self.resolve_ok(project, store)
        self.assertEqual(binding["bundle_id"], "bundle-one")

    def test_user_agents_content_survives_reenrollment(self):
        store, _ = self.make_store()
        project = self.tmp / "my project"
        project.mkdir(parents=True)
        (project / "AGENTS.md").write_text(
            "Team rule: review before merging.\n", encoding="utf-8")
        self.init_ok(project, "bundle-one", "codex", store)
        self.init_ok(project, "bundle-one", "codex", store)
        text = (project / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Team rule: review before merging.", text)
        self.assertEqual(text.count(AGENTS_START), 1)


class TestProjectPrepare(ProjectBindingBase):
    def test_first_prepare_auto_enrolls_only_current_project(self):
        store, _ = self.make_store(bundles=("bundle-one",))
        project = self.tmp / "current project"
        sibling = self.tmp / "sibling"
        sibling.mkdir()

        result = self.prepare(project, "opencode", store)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            pathlib.Path(result.stdout.strip()),
            store / ".harness" / "bundles" / "bundle-one")
        self.assertEqual(self.read_pin(project)["bundle"], "bundle-one")
        self.assertFalse((sibling / ".superpowers").exists())

    def test_prepare_offers_changed_paths_without_changing_pin(self):
        store, _ = self.make_store(bundles=("bundle-one",))
        project = self.tmp / "project"
        self.init_ok(project, "bundle-one", "opencode", store)
        original_pin = self.read_pin(project)
        source = self.make_source(name="source-new")
        result = run_python_snippet(
            STAGE_SNIPPET, [str(store), "bundle-two", str(source)])
        self.assertEqual(result.returncode, 0, result.stderr)
        result = run_python_snippet(SELECT_SNIPPET, [str(store), "bundle-two"])
        self.assertEqual(result.returncode, 0, result.stderr)

        result = self.prepare(project, "opencode", store)

        self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
        report = result.stdout + result.stderr
        self.assertIn("bundle-one", report)
        self.assertIn("bundle-two", report)
        self.assertIn("README.md", report)
        self.assertEqual(self.read_pin(project), original_pin)

    def test_prepare_accepts_upgrade_only_when_requested(self):
        store, _ = self.make_store(bundles=("bundle-one",))
        project = self.tmp / "project"
        self.init_ok(project, "bundle-one", "opencode", store)
        source = self.make_source(name="source-new")
        result = run_python_snippet(
            STAGE_SNIPPET, [str(store), "bundle-two", str(source)])
        self.assertEqual(result.returncode, 0, result.stderr)
        result = run_python_snippet(SELECT_SNIPPET, [str(store), "bundle-two"])
        self.assertEqual(result.returncode, 0, result.stderr)

        result = self.prepare(
            project, "opencode", store, "--accept-upgrade")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            pathlib.Path(result.stdout.strip()),
            store / ".harness" / "bundles" / "bundle-two")
        self.assertEqual(self.read_pin(project)["bundle"], "bundle-two")
        self.assertEqual(
            (project / "AGENTS.md").read_text(encoding="utf-8").count(
                AGENTS_START), 1)

    def test_prepare_keep_pinned_does_not_change_pin(self):
        store, _ = self.make_store(bundles=("bundle-one",))
        project = self.tmp / "project"
        self.init_ok(project, "bundle-one", "opencode", store)
        original_pin = self.read_pin(project)
        source = self.make_source(name="source-new")
        result = run_python_snippet(
            STAGE_SNIPPET, [str(store), "bundle-two", str(source)])
        self.assertEqual(result.returncode, 0, result.stderr)
        result = run_python_snippet(SELECT_SNIPPET, [str(store), "bundle-two"])
        self.assertEqual(result.returncode, 0, result.stderr)

        result = self.prepare(project, "opencode", store, "--keep-pinned")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            pathlib.Path(result.stdout.strip()),
            store / ".harness" / "bundles" / "bundle-one")
        self.assertEqual(self.read_pin(project), original_pin)

    def test_prepare_resume_keeps_active_run_on_original_bundle(self):
        store, _ = self.make_store(bundles=("bundle-one",))
        project = self.tmp / "project"
        self.init_ok(project, "bundle-one", "opencode", store)
        original_pin = self.read_pin(project)
        source = self.make_source(name="source-new")
        result = run_python_snippet(
            STAGE_SNIPPET, [str(store), "bundle-two", str(source)])
        self.assertEqual(result.returncode, 0, result.stderr)
        result = run_python_snippet(SELECT_SNIPPET, [str(store), "bundle-two"])
        self.assertEqual(result.returncode, 0, result.stderr)

        result = self.prepare(project, "opencode", store, "--resume")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            pathlib.Path(result.stdout.strip()),
            store / ".harness" / "bundles" / "bundle-one")
        self.assertEqual(self.read_pin(project), original_pin)
        self.assertNotIn("upgrade available", result.stderr.lower())

    def test_prepare_does_not_fallback_when_an_existing_pin_is_missing(self):
        store, _ = self.make_store(bundles=("bundle-one",))
        project = self.tmp / "existing-project"
        (project / ".superpowers" / "two-model" / "plan").mkdir(
            parents=True)

        result = self.prepare(project, "opencode", store)

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("missing its harness pin", result.stderr)
        self.assertFalse((project / ".superpowers" / "harness.json").exists())

    def test_failed_accepted_upgrade_keeps_old_pin_and_agents_bytes(self):
        store, _ = self.make_store(bundles=("bundle-one",))
        project = self.tmp / "project"
        self.init_ok(project, "bundle-one", "opencode", store)
        old_pin = (project / ".superpowers" / "harness.json").read_bytes()
        torn_agents = "# user text\n" + AGENTS_START + "\npartial\n"
        (project / "AGENTS.md").write_text(torn_agents, encoding="utf-8")
        source = self.make_source(name="source-new")
        result = run_python_snippet(
            STAGE_SNIPPET, [str(store), "bundle-two", str(source)])
        self.assertEqual(result.returncode, 0, result.stderr)
        result = run_python_snippet(SELECT_SNIPPET, [str(store), "bundle-two"])
        self.assertEqual(result.returncode, 0, result.stderr)

        result = self.prepare(
            project, "opencode", store, "--accept-upgrade")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            (project / ".superpowers" / "harness.json").read_bytes(), old_pin)
        self.assertEqual(
            (project / "AGENTS.md").read_text(encoding="utf-8"), torn_agents)


if __name__ == "__main__":
    unittest.main()
