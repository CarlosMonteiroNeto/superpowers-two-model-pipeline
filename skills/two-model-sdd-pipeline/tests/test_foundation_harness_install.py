"""Black-box tests for immutable harness installation (Round 1 Task 4).

Contract under test:
  skills/two-model-sdd-pipeline/scripts/harness_install.py
    stage_bundle / select_bundle / selected_bundle / resolve_bundle /
    bundle_hash / export_bundle
  scripts/install-superpowers
    fresh clone stages a validated immutable bundle, selects it atomically,
    and installs backend-specific entry points; a failed validation leaves
    no half-installed selection behind and never touches an unrelated
    installed plugin cache.
  scripts/package-codex-plugin.sh
    both package paths (zip and tar.gz) ship a complete bundle.

Acceptance encoded here (plan task 4):
  a complete immutable bundle carries runtime files, prompts, skills,
  canonical docs and license; a candidate is staged and validated before
  it is atomically selected; failed validation preserves the prior
  selection; pinned projects and active runs retain their old bundle;
  backend-specific entry points resolve the selected bundle through
  relocatable identities; unrelated plugin caches are never patched;
  both package paths and directory names with spaces are covered; no
  remote repository is created.

Expectations are hand-derived literals. The module is exercised in a
fresh interpreter per case (real behavior, no in-process imports), shell
scripts run as real processes against disposable directories and
disposable local Git repositories, so a missing module or script fails
as an assertion on the subprocess outcome, not as a collection error.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

REPO = pathlib.Path(__file__).resolve().parent.parent.parent.parent
SKILL = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
INSTALL_SCRIPT = REPO / "scripts" / "install-superpowers"
PACKAGE_SCRIPT = REPO / "scripts" / "package-codex-plugin.sh"

if os.name == "nt":
    git_bash = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
    BASH = str(git_bash) if git_bash.exists() else "bash"
else:
    BASH = "bash"

GIT = shutil.which("git") or "git"

# Independently selected package sentinels. These cover runtime executables,
# non-pipeline skills, plugin metadata, hooks, and canonical documentation;
# production must discover and package the full supported trees rather than
# use this test list as its own inventory.
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

SELECTED_SNIPPET = (
    "import sys; "
    "sys.path.insert(0, %r); " % str(SCRIPTS) +
    "import harness_install; "
    "print(harness_install.selected_bundle(sys.argv[1]) or '')"
)

EXPORT_SNIPPET = (
    "import sys; "
    "sys.path.insert(0, %r); " % str(SCRIPTS) +
    "import harness_install; "
    "print(harness_install.export_bundle(sys.argv[1], sys.argv[2]))"
)


def run_git(cwd, *args):
    return subprocess.run(
        [GIT, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=dict(os.environ),
    )


def run_bash(script, args, env_extra=None, cwd=None):
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [BASH, str(script), *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        env=env,
    )


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


def assert_same_path(testcase, first, second):
    """Compare paths across shell/Python separator conventions."""
    testcase.assertEqual(
        os.path.normpath(first), os.path.normpath(second))


class HarnessInstallBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="foundation-harness-install-")
        self.tmp = pathlib.Path(self._tmp)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def make_source(self, name="source", missing=()):
        """Build a bundle source tree carrying the required categories."""
        source = self.tmp / name
        for rel in REQUIRED_SOURCE_FILES:
            if rel in missing:
                continue
            path = source / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture content for %s\n" % rel, encoding="utf-8")
        harness_scripts = source / "skills" / "two-model-sdd-pipeline" / "scripts"
        for name in ("harness_install.py", "harness-project"):
            shutil.copyfile(SCRIPTS / name, harness_scripts / name)
        (harness_scripts / "run-pipeline").write_text(
            "#!/usr/bin/env bash\nprintf 'pinned-run\\n'\n",
            encoding="utf-8")
        return source

    def stage_ok(self, install_root, bundle_id, source):
        result = run_python_snippet(
            STAGE_SNIPPET, [str(install_root), bundle_id, str(source)])
        self.assertEqual(
            result.returncode, 0,
            "stage_bundle must accept the complete fixture: " + result.stderr)
        return json.loads(result.stdout)

    def select_ok(self, install_root, bundle_id):
        result = run_python_snippet(
            SELECT_SNIPPET, [str(install_root), bundle_id])
        self.assertEqual(
            result.returncode, 0,
            "select_bundle must accept the staged fixture: " + result.stderr)
        return json.loads(result.stdout)

    def selected_is(self, install_root):
        result = run_python_snippet(SELECTED_SNIPPET, [str(install_root)])
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()


class TestBundleStaging(HarnessInstallBase):
    def test_bundle_inventory_excludes_nested_node_modules(self):
        install_root = self.tmp / "install"
        source = self.make_source()
        expected = source / ".opencode" / "plugins" / "runner.js"
        expected.parent.mkdir(parents=True, exist_ok=True)
        expected.write_text("plugin source\n", encoding="utf-8")
        dependency = source / ".opencode" / "node_modules" / "large" / "index.js"
        dependency.parent.mkdir(parents=True, exist_ok=True)
        dependency.write_text("local dependency\n", encoding="utf-8")

        manifest = self.stage_ok(install_root, "bundle-one", source)

        self.assertIn(".opencode/plugins/runner.js", manifest["files"])
        self.assertNotIn(".opencode/node_modules/large/index.js", manifest["files"])
        staged = install_root / ".harness" / "bundles" / "bundle-one"
        self.assertFalse((staged / ".opencode" / "node_modules").exists())

    def test_stage_complete_bundle_records_manifest(self):
        install_root = self.tmp / "install"
        source = self.make_source()
        manifest = self.stage_ok(install_root, "bundle-one", source)
        self.assertEqual(manifest["id"], "bundle-one")
        self.assertEqual(manifest["version"], 1)
        self.assertIn("bundle_hash", manifest)
        self.assertEqual(len(manifest["bundle_hash"]), 64)
        bundle_dir = install_root / ".harness" / "bundles" / "bundle-one"
        self.assertTrue((bundle_dir / "manifest.json").is_file())
        for rel in REQUIRED_SOURCE_FILES:
            self.assertTrue(
                (bundle_dir / rel).is_file(),
                "staged bundle must carry %s" % rel)

    def test_stage_does_not_select(self):
        install_root = self.tmp / "install"
        source = self.make_source()
        self.stage_ok(install_root, "bundle-one", source)
        self.assertEqual(self.selected_is(install_root), "")

    def test_manifest_and_hash_cover_new_files_in_package_trees(self):
        install_root = self.tmp / "install"
        source = self.make_source()
        added = (source / "skills" / "two-model-sdd-pipeline" / "scripts"
                 / "future-helper")
        added.write_text("future runtime helper\n", encoding="utf-8")
        manifest = self.stage_ok(install_root, "bundle-one", source)
        bundle_dir = install_root / ".harness" / "bundles" / "bundle-one"
        self.assertIn(
            "skills/two-model-sdd-pipeline/scripts/future-helper",
            manifest["files"])
        staged = bundle_dir / "skills" / "two-model-sdd-pipeline" / "scripts" / "future-helper"
        self.assertEqual(staged.read_text(encoding="utf-8"),
                         "future runtime helper\n")
        staged.write_text("tampered\n", encoding="utf-8")
        result = run_python_snippet(
            SELECT_SNIPPET, [str(install_root), "bundle-one"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hash", (result.stdout + result.stderr).lower())

    def test_stage_rejects_missing_license(self):
        install_root = self.tmp / "install"
        source = self.make_source(missing=("LICENSE",))
        result = run_python_snippet(
            STAGE_SNIPPET, [str(install_root), "bundle-bad", str(source)])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("LICENSE", result.stderr)
        self.assertFalse(
            (install_root / ".harness" / "bundles" / "bundle-bad").exists())

    def test_stage_rejects_missing_runtime_file(self):
        install_root = self.tmp / "install"
        source = self.make_source(missing=(
            "skills/two-model-sdd-pipeline/scripts/pipeline_config.py",))
        result = run_python_snippet(
            STAGE_SNIPPET, [str(install_root), "bundle-bad", str(source)])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pipeline_config.py", result.stderr)

    def test_stage_rejects_missing_prompts(self):
        install_root = self.tmp / "install"
        source = self.make_source(missing=("agent/two-model-coder.md",))
        result = run_python_snippet(
            STAGE_SNIPPET, [str(install_root), "bundle-bad", str(source)])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("two-model-coder.md", result.stderr)

    def test_stage_rejects_bad_bundle_id(self):
        install_root = self.tmp / "install"
        source = self.make_source()
        result = run_python_snippet(
            STAGE_SNIPPET, [str(install_root), "../escape", str(source)])
        self.assertNotEqual(result.returncode, 0)

    def test_failed_stage_preserves_prior_selection(self):
        install_root = self.tmp / "install"
        good = self.make_source(name="good")
        self.stage_ok(install_root, "bundle-good", good)
        self.select_ok(install_root, "bundle-good")
        bad = self.make_source(name="bad", missing=("LICENSE",))
        result = run_python_snippet(
            STAGE_SNIPPET, [str(install_root), "bundle-bad", str(bad)])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.selected_is(install_root), "bundle-good")
        bundle_dir = install_root / ".harness" / "bundles" / "bundle-good"
        self.assertTrue((bundle_dir / "README.md").is_file())

    def test_reusing_bundle_id_with_changed_content_preserves_old_bundle(self):
        install_root = self.tmp / "install"
        first = self.make_source(name="first")
        self.stage_ok(install_root, "stable-id", first)
        self.select_ok(install_root, "stable-id")
        bundle_dir = install_root / ".harness" / "bundles" / "stable-id"
        old_manifest = (bundle_dir / "manifest.json").read_bytes()
        old_readme = (bundle_dir / "README.md").read_bytes()

        changed = self.make_source(name="changed")
        (changed / "README.md").write_text("new content\n", encoding="utf-8")
        result = run_python_snippet(
            STAGE_SNIPPET, [str(install_root), "stable-id", str(changed)])

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("immutable", (result.stdout + result.stderr).lower())
        self.assertEqual((bundle_dir / "manifest.json").read_bytes(),
                         old_manifest)
        self.assertEqual((bundle_dir / "README.md").read_bytes(), old_readme)
        self.assertEqual(self.selected_is(install_root), "stable-id")

    def test_select_missing_bundle_preserves_prior(self):
        install_root = self.tmp / "install"
        source = self.make_source()
        self.stage_ok(install_root, "bundle-good", source)
        self.select_ok(install_root, "bundle-good")
        result = run_python_snippet(
            SELECT_SNIPPET, [str(install_root), "bundle-never-staged"])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.selected_is(install_root), "bundle-good")

    def test_select_rejects_tampered_bundle(self):
        install_root = self.tmp / "install"
        source = self.make_source()
        self.stage_ok(install_root, "bundle-one", source)
        bundle_dir = install_root / ".harness" / "bundles" / "bundle-one"
        (bundle_dir / "README.md").write_text("tampered\n", encoding="utf-8")
        result = run_python_snippet(
            SELECT_SNIPPET, [str(install_root), "bundle-one"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hash", (result.stderr + result.stdout).lower())
        self.assertEqual(self.selected_is(install_root), "")

    def test_entry_point_write_failure_preserves_prior_selection(self):
        install_root = self.tmp / "install"
        first = self.make_source(name="first")
        self.stage_ok(install_root, "bundle-one", first)
        self.select_ok(install_root, "bundle-one")
        second = self.make_source(name="second")
        self.stage_ok(install_root, "bundle-two", second)
        snippet = (
            "import sys; sys.path.insert(0, %r); import harness_install; "
            "harness_install._write_entry_points = lambda root: "
            "(_ for _ in ()).throw(OSError('entrypoint write failed')); "
            "harness_install.select_bundle(sys.argv[1], sys.argv[2])"
        ) % str(SCRIPTS)

        result = run_python_snippet(
            snippet, [str(install_root), "bundle-two"])

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.selected_is(install_root), "bundle-one")

    def test_stage_and_select_under_path_with_spaces(self):
        install_root = self.tmp / "dir with spaces" / "install"
        source = self.make_source(name="src with spaces")
        self.stage_ok(install_root, "bundle-spaces", source)
        self.select_ok(install_root, "bundle-spaces")
        self.assertEqual(self.selected_is(install_root), "bundle-spaces")


class TestBackendEntryPoints(HarnessInstallBase):
    def install_selected(self, install_root, bundle_id="bundle-one"):
        source = self.make_source()
        self.stage_ok(install_root, bundle_id, source)
        return self.select_ok(install_root, bundle_id)

    def test_both_backend_entry_points_exist(self):
        install_root = self.tmp / "install"
        self.install_selected(install_root)
        for backend in ("codex", "opencode"):
            entry = (install_root / ".harness" / "entrypoints"
                     / ("%s.sh" % backend))
            self.assertTrue(entry.is_file(), "missing %s entry point" % backend)

    def test_entry_points_resolve_selected_bundle(self):
        install_root = self.tmp / "install"
        self.install_selected(install_root, "bundle-one")
        expected = str(install_root / ".harness" / "bundles" / "bundle-one")
        for backend in ("codex", "opencode"):
            entry = (install_root / ".harness" / "entrypoints"
                     / ("%s.sh" % backend))
            project = self.tmp / ("project-" + backend)
            project.mkdir()
            result = run_bash(
                entry, [str(install_root)], cwd=project)
            self.assertEqual(
                result.returncode, 0,
                "%s entry point must resolve: %s" % (backend, result.stderr))
            assert_same_path(self, result.stdout.strip(), expected)

    def test_entry_points_resolve_existing_project_pin_after_new_selection(self):
        install_root = self.tmp / "install"
        self.install_selected(install_root, "bundle-one")
        second = self.make_source(name="second")
        self.stage_ok(install_root, "bundle-two", second)
        project = self.tmp / "project"
        initialized = subprocess.run(
            [sys.executable, str(SCRIPTS / "harness-project"), "init",
             "--project", str(project), "--bundle", "bundle-one",
             "--backend", "opencode", "--install-root", str(install_root)],
            capture_output=True, text=True)
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        self.select_ok(install_root, "bundle-two")
        expected = str(install_root / ".harness" / "bundles" / "bundle-one")
        entry = install_root / ".harness" / "entrypoints" / "opencode.sh"
        result = run_bash(entry, ["--keep-pinned"], cwd=project)
        self.assertEqual(result.returncode, 0, result.stderr)
        assert_same_path(self, result.stdout.strip(), expected)

    def test_entry_point_resuming_active_run_keeps_its_pinned_bundle(self):
        install_root = self.tmp / "install"
        self.install_selected(install_root, "bundle-one")
        second = self.make_source(name="second")
        self.stage_ok(install_root, "bundle-two", second)
        project = self.tmp / "project"
        project.mkdir()
        initialized = subprocess.run(
            [sys.executable, str(SCRIPTS / "harness-project"), "init",
             "--project", str(project), "--bundle", "bundle-one",
             "--backend", "opencode", "--install-root", str(install_root)],
            capture_output=True, text=True)
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        self.select_ok(install_root, "bundle-two")
        plan = project / "plan.json"
        plan.write_text("{}", encoding="utf-8")
        ledger = project / ".superpowers" / "two-model" / "plan"
        ledger.mkdir(parents=True)
        (ledger / "ledger.jsonl").write_text("{\"event\":\"task_started\"}\n",
                                               encoding="utf-8")
        entry = install_root / ".harness" / "entrypoints" / "opencode.sh"

        result = run_bash(
            entry, ["--accept-upgrade", str(plan)], cwd=project)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "pinned-run")
        self.assertEqual(
            json.loads((project / ".superpowers" / "harness.json").read_text(
                encoding="utf-8"))["bundle"], "bundle-one")

    def test_entry_point_detects_relative_active_plan_from_outside_project(self):
        install_root = self.tmp / "install"
        self.install_selected(install_root, "bundle-one")
        second = self.make_source(name="second")
        self.stage_ok(install_root, "bundle-two", second)
        project = self.tmp / "project"
        project.mkdir()
        initialized = subprocess.run(
            [sys.executable, str(SCRIPTS / "harness-project"), "init",
             "--project", str(project), "--bundle", "bundle-one",
             "--backend", "opencode", "--install-root", str(install_root)],
            capture_output=True, text=True)
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        self.select_ok(install_root, "bundle-two")
        (project / "plans").mkdir()
        (project / "plans" / "active.json").write_text("{}\n",
                                                          encoding="utf-8")
        ledger = project / ".superpowers" / "two-model" / "active"
        ledger.mkdir(parents=True)
        (ledger / "ledger.jsonl").write_text(
            "{\"event\":\"task_started\"}\n", encoding="utf-8")
        entry = install_root / ".harness" / "entrypoints" / "opencode.sh"

        result = run_bash(
            entry, ["--project", str(project), "--accept-upgrade",
                    "plans/active.json"], cwd=self.tmp)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "pinned-run")
        pin = json.loads((project / ".superpowers" / "harness.json").read_text(
            encoding="utf-8"))
        self.assertEqual(pin["bundle"], "bundle-one")

    def test_entry_point_auto_enrolls_only_the_current_project(self):
        install_root = self.tmp / "install"
        self.install_selected(install_root, "bundle-one")
        project = self.tmp / "project"
        sibling = self.tmp / "sibling"
        project.mkdir()
        sibling.mkdir()
        entry = install_root / ".harness" / "entrypoints" / "opencode.sh"

        result = run_bash(entry, [], cwd=project)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        expected = str(install_root / ".harness" / "bundles" / "bundle-one")
        assert_same_path(self, result.stdout.strip(), expected)
        self.assertTrue((project / ".superpowers" / "harness.json").is_file())
        self.assertFalse((sibling / ".superpowers").exists())

    def test_entry_points_are_relocatable(self):
        install_root = self.tmp / "install"
        self.install_selected(install_root)
        for backend in ("codex", "opencode"):
            entry = (install_root / ".harness" / "entrypoints"
                     / ("%s.sh" % backend))
            text = entry.read_text(encoding="utf-8")
            self.assertNotIn(
                str(install_root), text,
                "%s entry point must not hard-code its install root" % backend)

    def test_entry_points_resolve_under_path_with_spaces(self):
        install_root = self.tmp / "dir with spaces" / "install"
        self.install_selected(install_root)
        expected = str(install_root / ".harness" / "bundles" / "bundle-one")
        entry = install_root / ".harness" / "entrypoints" / "opencode.sh"
        project = self.tmp / "project"
        project.mkdir()
        result = run_bash(entry, [str(install_root)], cwd=project)
        self.assertEqual(result.returncode, 0, result.stderr)
        assert_same_path(self, result.stdout.strip(), expected)


class TestBundleExport(HarnessInstallBase):
    def staged_bundle_dir(self, install_root, bundle_id="bundle-one"):
        source = self.make_source()
        self.stage_ok(install_root, bundle_id, source)
        return install_root / ".harness" / "bundles" / bundle_id

    def archive_members(self, archive):
        if str(archive).endswith(".zip"):
            import zipfile
            with zipfile.ZipFile(str(archive)) as handle:
                return sorted(handle.namelist())
        import tarfile
        with tarfile.open(str(archive)) as handle:
            return sorted(handle.getnames())

    def test_export_zip_contains_complete_bundle(self):
        install_root = self.tmp / "install"
        bundle_dir = self.staged_bundle_dir(install_root)
        output = self.tmp / "bundle.zip"
        result = run_python_snippet(
            EXPORT_SNIPPET, [str(bundle_dir), str(output)])
        self.assertEqual(result.returncode, 0, result.stderr)
        members = self.archive_members(output)
        for rel in list(REQUIRED_SOURCE_FILES) + ["manifest.json"]:
            self.assertIn(rel, members, "zip package must carry %s" % rel)

    def test_export_tar_gz_contains_complete_bundle(self):
        install_root = self.tmp / "install"
        bundle_dir = self.staged_bundle_dir(install_root)
        output = self.tmp / "bundle.tar.gz"
        result = run_python_snippet(
            EXPORT_SNIPPET, [str(bundle_dir), str(output)])
        self.assertEqual(result.returncode, 0, result.stderr)
        members = self.archive_members(output)
        for rel in list(REQUIRED_SOURCE_FILES) + ["manifest.json"]:
            self.assertIn(rel, members, "tar.gz package must carry %s" % rel)

    def test_archive_exports_preserve_executable_runtime_modes(self):
        install_root = self.tmp / "install"
        source = self.make_source()
        rel = "skills/two-model-sdd-pipeline/scripts/run-pipeline"
        run_git(source, "init", "-q", "-b", "main")
        run_git(source, "config", "user.email", "test@example.com")
        run_git(source, "config", "user.name", "Test")
        run_git(source, "add", "-A")
        committed = run_git(source, "commit", "-qm", "fixture-source")
        self.assertEqual(committed.returncode, 0, committed.stderr)
        marked = run_git(source, "update-index", "--chmod=+x", rel)
        self.assertEqual(marked.returncode, 0, marked.stderr)
        committed = run_git(source, "commit", "-qm", "mark-runtime-executable")
        self.assertEqual(committed.returncode, 0, committed.stderr)
        self.stage_ok(install_root, "bundle-one", source)
        bundle_dir = install_root / ".harness" / "bundles" / "bundle-one"
        manifest = json.loads(
            (bundle_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["modes"][rel], 0o755)
        zip_out = self.tmp / "bundle.zip"
        tar_out = self.tmp / "bundle.tar.gz"
        for output in (zip_out, tar_out):
            result = run_python_snippet(
                EXPORT_SNIPPET, [str(bundle_dir), str(output)])
            self.assertEqual(result.returncode, 0, result.stderr)
        with zipfile.ZipFile(str(zip_out)) as archive:
            info = archive.getinfo(
                "skills/two-model-sdd-pipeline/scripts/run-pipeline")
            self.assertEqual((info.external_attr >> 16) & 0o777, 0o755)
        with tarfile.open(str(tar_out)) as archive:
            info = archive.getmember(
                "skills/two-model-sdd-pipeline/scripts/run-pipeline")
            self.assertEqual(info.mode & 0o777, 0o755)

    def test_both_package_paths_carry_same_files(self):
        install_root = self.tmp / "install"
        bundle_dir = self.staged_bundle_dir(install_root)
        zip_out = self.tmp / "bundle.zip"
        tar_out = self.tmp / "bundle.tar.gz"
        for output in (zip_out, tar_out):
            result = run_python_snippet(
                EXPORT_SNIPPET, [str(bundle_dir), str(output)])
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.archive_members(zip_out), self.archive_members(tar_out))

    def test_export_under_path_with_spaces(self):
        install_root = self.tmp / "install"
        bundle_dir = self.staged_bundle_dir(install_root)
        output = self.tmp / "dir with spaces" / "bundle with spaces.zip"
        output.parent.mkdir(parents=True, exist_ok=True)
        result = run_python_snippet(
            EXPORT_SNIPPET, [str(bundle_dir), str(output)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.is_file())


class InstallScriptBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="foundation-install-script-")
        self.tmp = pathlib.Path(self._tmp)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def make_origin(self, name="origin", missing=()):
        """Disposable local Git repository acting as the install source."""
        origin = self.tmp / name
        origin.mkdir(parents=True, exist_ok=True)
        result = run_git(origin, "init", "-q", "-b", "main")
        self.assertEqual(result.returncode, 0, result.stderr)
        run_git(origin, "config", "user.email", "test@example.com")
        run_git(origin, "config", "user.name", "Test")
        for rel in REQUIRED_SOURCE_FILES:
            if rel in missing:
                continue
            path = origin / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("origin content for %s\n" % rel, encoding="utf-8")
        harness_scripts = (
            origin / "skills" / "two-model-sdd-pipeline" / "scripts")
        harness_scripts.mkdir(parents=True, exist_ok=True)
        shutil.copy(str(SCRIPTS / "harness_install.py"),
                    str(harness_scripts / "harness_install.py"))
        shutil.copy(str(SCRIPTS / "harness-project"),
                    str(harness_scripts / "harness-project"))
        (origin / ".codex-plugin").mkdir(exist_ok=True)
        (origin / ".codex-plugin" / "plugin.json").write_text(
            json.dumps({"name": "superpowers", "version": "9.9.9-test"}),
            encoding="utf-8")
        run_git(origin, "add", "-A")
        result = run_git(origin, "commit", "-qm", "fixture-origin-commit")
        self.assertEqual(result.returncode, 0, result.stderr)
        return origin


class TestInstallSuperpowers(InstallScriptBase):
    def test_existing_clean_checkout_gets_initial_bundle_selection(self):
        origin = self.make_origin()
        vendor = self.tmp / "vendor"
        cloned = run_git(self.tmp, "clone", "-q", str(origin), str(vendor))
        self.assertEqual(cloned.returncode, 0, cloned.stderr)

        result = run_bash(
            INSTALL_SCRIPT, [str(vendor)],
            env_extra={"REPO_URL": str(origin)})

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        selected = (vendor / ".harness" / "selected").read_text(
            encoding="utf-8").strip()
        self.assertEqual(selected, "git-" + run_git(
            vendor, "rev-parse", "--short=12", "HEAD").stdout.strip())
        bundle = vendor / ".harness" / "bundles" / selected
        self.assertTrue(
            (bundle / "skills" / "two-model-sdd-pipeline" / "scripts"
             / "harness-project").is_file())
        self.assertTrue(
            (vendor / ".harness" / "entrypoints" / "opencode.sh").is_file())

    def test_fresh_install_stages_bundle_and_entry_points(self):
        origin = self.make_origin()
        vendor = self.tmp / "vendor"
        result = run_bash(
            INSTALL_SCRIPT, [str(vendor)],
            env_extra={"REPO_URL": str(origin)})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        harness = vendor / ".harness"
        selected = (harness / "selected").read_text(
            encoding="utf-8").strip()
        self.assertTrue(selected)
        bundle_dir = harness / "bundles" / selected
        for rel in REQUIRED_SOURCE_FILES:
            self.assertTrue(
                (bundle_dir / rel).is_file(),
                "installed bundle must carry %s" % rel)
        for backend in ("codex", "opencode"):
            entry = harness / "entrypoints" / ("%s.sh" % backend)
            self.assertTrue(entry.is_file())
            project = self.tmp / ("entry-project-" + backend)
            project.mkdir()
            resolved = run_bash(entry, [str(vendor)], cwd=project)
            self.assertEqual(resolved.returncode, 0, resolved.stderr)
            assert_same_path(self, resolved.stdout.strip(), str(bundle_dir))

    def test_failed_validation_leaves_no_selection(self):
        origin = self.make_origin(missing=("LICENSE",))
        vendor = self.tmp / "vendor"
        result = run_bash(
            INSTALL_SCRIPT, [str(vendor)],
            env_extra={"REPO_URL": str(origin)})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((vendor / ".harness" / "selected").exists())

    def test_unrelated_plugin_cache_is_never_patched(self):
        origin = self.make_origin()
        cache = self.tmp / "other-vendor"
        cache.mkdir()
        marker = cache / "node_modules" / "superpowers" / "package.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text('{"name": "superpowers"}\n', encoding="utf-8")
        before = marker.read_bytes()
        vendor = self.tmp / "vendor"
        result = run_bash(
            INSTALL_SCRIPT, [str(vendor)],
            env_extra={"REPO_URL": str(origin)})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(marker.read_bytes(), before)
        self.assertFalse((cache / ".harness").exists())

    def test_install_under_path_with_spaces(self):
        origin = self.make_origin()
        vendor = self.tmp / "dir with spaces" / "vendor"
        result = run_bash(
            INSTALL_SCRIPT, [str(vendor)],
            env_extra={"REPO_URL": str(origin)})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        selected = (vendor / ".harness" / "selected").read_text(
            encoding="utf-8").strip()
        self.assertTrue(selected)


class TestPortalPackaging(unittest.TestCase):
    """Both portal package paths (zip and tar.gz) ship the complete bundle.

    The script under test is copied byte-identical into a disposable
    fixture repository, so the test exercises the current script logic
    without mutating the real worktree and without any network access.
    The zip invocation additionally requires a zip binary that reads
    file lists from stdin; that capability is probed (some minimal
    installs ship a zip that only accepts explicit file arguments) and
    the zip-only assertions skip when it is absent. The tar.gz path
    exercises the same shared staging and archive list unconditionally.
    """

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="foundation-portal-package-")
        self.tmp = pathlib.Path(self._tmp)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def zip_list_capable(self):
        """Probe whether zip packages a stdin file list under bash.

        The probe replicates the package script's exact zip step
        (archive bytes to stdout, file list on stdin, invoked as a
        bash script): some minimal zip installs only accept explicit
        file arguments there, even when direct invocation works.
        """
        if not shutil.which("zip"):
            return False
        probe = self.tmp / "zip-probe"
        stage = probe / "stage"
        stage.mkdir(parents=True, exist_ok=True)
        (stage / "probe.txt").write_text("probe\n", encoding="utf-8")
        script = probe / "probe.sh"
        script.write_text(
            "set -e\n"
            'cd "$1"\n'
            'COPYFILE_DISABLE=1 zip -X -q - -@ < "$2" > "$3"\n',
            encoding="utf-8")
        out = probe / "probe.zip"
        listing = probe / "list"
        listing.write_text("probe.txt\n", encoding="utf-8")
        result = subprocess.run(
            [BASH, str(script), str(stage), str(listing), str(out)],
            capture_output=True,
            env=dict(os.environ))
        if result.returncode != 0 or not out.is_file():
            return False
        try:
            import zipfile
            with zipfile.ZipFile(str(out)) as handle:
                return handle.namelist() == ["probe.txt"]
        except Exception:
            return False

    def make_fixture_repo(self, name="fixture"):
        repo = self.tmp / name
        (repo / "scripts").mkdir(parents=True)
        shutil.copy(str(PACKAGE_SCRIPT),
                    str(repo / "scripts" / "package-codex-plugin.sh"))
        (repo / ".codex-plugin").mkdir()
        (repo / ".codex-plugin" / "plugin.json").write_text(
            json.dumps({"name": "superpowers", "version": "9.9.9-test",
                        "skills": "./skills/", "hooks": {}}),
            encoding="utf-8")
        (repo / "codex-plugin-hooks").mkdir()
        (repo / "codex-plugin-hooks" / "hooks.json").write_text(
            '{"hooks": []}\n', encoding="utf-8")
        (repo / "skills" / "demo").mkdir(parents=True)
        (repo / "skills" / "demo" / "SKILL.md").write_text(
            "# demo\n", encoding="utf-8")
        (repo / "agent").mkdir()
        (repo / "agent" / "prompts.md").write_text(
            "# prompts\n", encoding="utf-8")
        (repo / "assets").mkdir()
        (repo / "assets" / "icon.png").write_bytes(b"fixture-icon")
        for name in ("README.md", "LICENSE", "CODE_OF_CONDUCT.md"):
            (repo / name).write_text("fixture %s\n" % name, encoding="utf-8")
        result = run_git(repo, "init", "-q", "-b", "main")
        self.assertEqual(result.returncode, 0, result.stderr)
        run_git(repo, "config", "user.email", "test@example.com")
        run_git(repo, "config", "user.name", "Test")
        run_git(repo, "add", "-A")
        result = run_git(repo, "commit", "-qm", "fixture-commit")
        self.assertEqual(result.returncode, 0, result.stderr)
        metadata = self.tmp / (name + "-metadata")
        skill_meta = metadata / "skills" / "demo" / "agents"
        skill_meta.mkdir(parents=True)
        (skill_meta / "openai.yaml").write_text(
            'interface:\n  display_name: "demo"\n', encoding="utf-8")
        return repo, metadata

    def list_members(self, archive):
        import zipfile
        if str(archive).endswith(".zip"):
            with zipfile.ZipFile(str(archive)) as handle:
                return sorted(handle.namelist())
        import tarfile
        with tarfile.open(str(archive)) as handle:
            return sorted(handle.getnames())

    def package(self, repo, metadata, output, extra=()):
        script = repo / "scripts" / "package-codex-plugin.sh"
        return run_bash(script, ["--allow-dirty", "--metadata-source",
                                 str(metadata), "--output", str(output),
                                 *extra])

    def test_zip_path_ships_complete_bundle(self):
        if not self.zip_list_capable():
            self.skipTest("local zip does not read file lists from stdin")
        repo, metadata = self.make_fixture_repo()
        output = self.tmp / "superpowers.zip"
        result = self.package(repo, metadata, output)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        members = self.list_members(output)
        for expected in (".codex-plugin/plugin.json",
                         "skills/demo/SKILL.md",
                         "skills/demo/agents/openai.yaml",
                         "agent/prompts.md",
                         "assets/icon.png",
                         "README.md",
                         "LICENSE"):
            self.assertIn(expected, members,
                          "zip package must carry %s" % expected)

    def test_tar_gz_path_ships_complete_bundle(self):
        repo, metadata = self.make_fixture_repo()
        output = self.tmp / "superpowers.tar.gz"
        result = self.package(repo, metadata, output,
                              extra=("--format", "tar.gz"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        members = self.list_members(output)
        for expected in (".codex-plugin/plugin.json",
                         "skills/demo/SKILL.md",
                         "skills/demo/agents/openai.yaml",
                         "agent/prompts.md",
                         "assets/icon.png",
                         "README.md",
                         "LICENSE"):
            self.assertIn(expected, members,
                          "tar.gz package must carry %s" % expected)

    def test_both_package_paths_carry_same_files(self):
        if not self.zip_list_capable():
            self.skipTest("local zip does not read file lists from stdin")
        repo, metadata = self.make_fixture_repo()
        zip_out = self.tmp / "superpowers.zip"
        tar_out = self.tmp / "superpowers.tar.gz"
        result = self.package(repo, metadata, zip_out)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = self.package(repo, metadata, tar_out,
                              extra=("--format", "tar.gz"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.list_members(zip_out),
                         self.list_members(tar_out))

    def test_package_output_under_path_with_spaces(self):
        repo, metadata = self.make_fixture_repo()
        output = self.tmp / "dir with spaces" / "super powers.tar.gz"
        output.parent.mkdir(parents=True, exist_ok=True)
        result = self.package(repo, metadata, output,
                              extra=("--format", "tar.gz"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
