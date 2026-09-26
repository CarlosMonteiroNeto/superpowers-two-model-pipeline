"""Black-box tests for scripts/sync-superpowers and scripts/check-superpowers.

Safe-update contract (Round 1 Task 1): inspected fast-forward-only updates,
explicit divergence reports, structured JSON, and preservation of all local
work. Expectations are hand-derived literals. Scripts run as real processes
against disposable Git repositories; no live inference or real installations.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
REPO_SCRIPTS = REPO_ROOT / "scripts"
SYNC = str(REPO_SCRIPTS / "sync-superpowers")
CHECK = str(REPO_SCRIPTS / "check-superpowers")

if os.name == "nt":
    import pathlib as _pl
    _git_bash = _pl.Path(r"C:\Program Files\Git\bin\bash.exe")
    BASH = str(_git_bash) if _git_bash.exists() else "bash"
else:
    BASH = "bash"

GIT = shutil.which("git") or "git"


def run_git(cwd, *args):
    return subprocess.run(
        [GIT, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=dict(os.environ),
    )


def run_script(script, args, env_extra=None):
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [BASH, script, *args],
        capture_output=True,
        text=True,
        env=env,
    )


def write_stub(directory, name, body):
    p = pathlib.Path(directory) / name
    p.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    subprocess.run([BASH, "-c", "chmod +x '{}'".format(str(p).replace("'", "'\\''"))],
                   capture_output=True)
    return str(p)


class SyncBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="foundation-sync-")
        self.tmp = pathlib.Path(self._tmp)
        self.stub_dir = self.tmp / "stubs"
        self.stub_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def make_pair(self, under=None):
        """Create (origin, vendor) disposable pair on branch main."""
        base = pathlib.Path(under) if under else self.tmp
        base.mkdir(parents=True, exist_ok=True)
        origin = base / "origin"
        origin.mkdir()
        r = run_git(origin, "init", "-q", "-b", "main")
        self.assertEqual(r.returncode, 0, r.stderr)
        run_git(origin, "config", "user.email", "test@example.com")
        run_git(origin, "config", "user.name", "Test")
        (origin / "file.txt").write_text("v1\n", encoding="utf-8")
        run_git(origin, "add", "-A")
        r = run_git(origin, "commit", "-qm", "initial-commit")
        self.assertEqual(r.returncode, 0, r.stderr)
        vendor = base / "vendor"
        r = run_git(base, "clone", "-q", str(origin), str(vendor))
        self.assertEqual(r.returncode, 0, r.stderr)
        run_git(vendor, "config", "user.email", "test@example.com")
        run_git(vendor, "config", "user.name", "Test")
        return origin, vendor

    def commit_on(self, repo, filename, content, message):
        (repo / filename).write_text(content, encoding="utf-8")
        run_git(repo, "add", "-A")
        r = run_git(repo, "commit", "-qm", message)
        self.assertEqual(r.returncode, 0, r.stderr)

    def add_harness_fixture(self, repo):
        """Add a small complete-enough package source to a disposable repo."""
        (repo / ".gitignore").write_text(
            ".harness/\n__pycache__/\n", encoding="utf-8")
        paths = (
            "agent/two-model-coder.md",
            "agent/two-model-reviewer.md",
            "agent/two-model-task-generator.md",
            "skills/brainstorming/SKILL.md",
            "skills/two-model-sdd-pipeline/SKILL.md",
            "skills/two-model-sdd-pipeline/scripts/pipeline_config.py",
            "skills/two-model-sdd-pipeline/scripts/dispatch_contract.py",
            "skills/two-model-sdd-pipeline/scripts/run-pipeline",
            "skills/two-model-sdd-pipeline/scripts/task-run",
            "skills/two-model-sdd-pipeline/scripts/harness_install.py",
            "skills/two-model-sdd-pipeline/scripts/harness-project",
            "skills/two-model-sdd-pipeline/schemas/runtime.schema.json",
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
        for rel in paths:
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture version 1: %s\n" % rel, encoding="utf-8")
        harness_scripts = (
            repo / "skills" / "two-model-sdd-pipeline" / "scripts")
        shutil.copyfile(
            REPO_ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"
            / "harness_install.py",
            harness_scripts / "harness_install.py")
        shutil.copyfile(
            REPO_ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"
            / "harness-project",
            harness_scripts / "harness-project")

    def stage_fixture_bundle(self, vendor, bundle_id):
        harness_install = (
            vendor / "skills" / "two-model-sdd-pipeline" / "scripts"
            / "harness_install.py")
        result = subprocess.run(
            [sys.executable, str(harness_install), "stage",
             "--install-root", str(vendor), "--bundle", bundle_id,
             "--source", str(vendor)],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = subprocess.run(
            [sys.executable, str(harness_install), "select",
             "--install-root", str(vendor), "--bundle", bundle_id],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def head_sha(self, repo):
        r = run_git(repo, "rev-parse", "HEAD")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def parse_json_stdout(self, result):
        self.assertTrue(
            result.stdout.strip().startswith("{"),
            "expected JSON object on stdout, got: "
            + result.stdout[:500] + result.stderr[:500],
        )
        try:
            data = json.loads(result.stdout)
        except ValueError as exc:
            self.fail("stdout is not valid JSON: %s; stdout=%r" % (exc, result.stdout[:1000]))
        for key in ("state", "before_sha", "remote_sha",
                    "changed_paths", "action", "errors"):
            self.assertIn(key, data, "JSON report must carry %s" % key)
        self.assertIsInstance(data["changed_paths"], list)
        self.assertIsInstance(data["errors"], list)
        self.assertIsInstance(data["action"], str)
        return data


class TestSyncJsonContract(SyncBase):
    def test_unchanged_reports_unchanged_json_exit_zero(self):
        origin, vendor = self.make_pair()
        before = self.head_sha(vendor)
        r = run_script(SYNC, [str(vendor), "--json"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = self.parse_json_stdout(r)
        self.assertEqual(data["state"], "unchanged")
        self.assertEqual(data["before_sha"], before)
        self.assertEqual(data["remote_sha"], before)
        self.assertEqual(data["changed_paths"], [])
        self.assertEqual(data["errors"], [])

    def test_behind_clean_fast_forwards_and_reports_updated(self):
        origin, vendor = self.make_pair()
        before = self.head_sha(vendor)
        self.commit_on(origin, "file.txt", "v2\n", "origin-second-commit")
        self.commit_on(origin, "second.txt", "hello\n", "origin-third-commit")
        remote = self.head_sha(origin)
        self.assertNotEqual(before, remote)
        r = run_script(SYNC, [str(vendor), "--json"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = self.parse_json_stdout(r)
        self.assertEqual(data["state"], "updated")
        self.assertEqual(data["before_sha"], before)
        self.assertEqual(data["remote_sha"], remote)
        self.assertIn("file.txt", data["changed_paths"])
        self.assertIn("second.txt", data["changed_paths"])
        self.assertEqual(data["action"], "fast-forward")
        self.assertEqual(data["errors"], [])
        self.assertEqual(self.head_sha(vendor), remote)
        self.assertEqual((vendor / "file.txt").read_text(encoding="utf-8"), "v2\n")
        combined = (r.stdout + r.stderr).lower()
        self.assertNotIn("rollback", combined)

    def test_applies_exact_sha_that_passed_validation_if_origin_main_moves(self):
        origin, vendor = self.make_pair()
        self.commit_on(origin, "file.txt", "v2\n", "validated-commit")
        validated_sha = self.head_sha(origin)
        self.commit_on(origin, "file.txt", "v3\n", "later-commit")
        later_sha = self.head_sha(origin)
        fetched = run_git(vendor, "fetch", "origin")
        self.assertEqual(fetched.returncode, 0, fetched.stderr)
        reset_tracking_ref = run_git(
            vendor, "update-ref", "refs/remotes/origin/main", validated_sha)
        self.assertEqual(reset_tracking_ref.returncode, 0, reset_tracking_ref.stderr)

        # Git calls this hook while checking out the detached candidate
        # worktree, after sync has captured remote_sha but before it applies
        # the update. Move origin/main to simulate another fetch in that gap.
        write_stub(
            vendor / ".git" / "hooks",
            "post-checkout",
            'git update-ref refs/remotes/origin/main "$R1_LATER_SHA"\n',
        )
        env = {"R1_LATER_SHA": later_sha, "CHECK_SKIP_FETCH": "1"}

        result = run_script(SYNC, [str(vendor), "--json"], env_extra=env)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = self.parse_json_stdout(result)
        self.assertEqual(data["state"], "updated")
        self.assertEqual(data["remote_sha"], validated_sha)
        self.assertEqual(self.head_sha(vendor), validated_sha)
        self.assertEqual((vendor / "file.txt").read_text(encoding="utf-8"), "v2\n")

    def test_fast_forward_selects_new_bundle_and_preserves_project_pin(self):
        origin, vendor = self.make_pair()
        self.add_harness_fixture(origin)
        run_git(origin, "add", "-A")
        result = run_git(origin, "commit", "-qm", "add-harness-fixture")
        self.assertEqual(result.returncode, 0, result.stderr)
        run_git(vendor, "pull", "--ff-only", "origin", "main")
        old_head = self.head_sha(vendor)
        old_bundle = "git-" + old_head[:12]
        self.stage_fixture_bundle(vendor, old_bundle)
        status = run_git(vendor, "status", "--porcelain")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(status.stdout, "", "fixture install must remain clean")
        project = self.tmp / "project"
        harness_project = (
            vendor / "skills" / "two-model-sdd-pipeline" / "scripts"
            / "harness-project")
        result = subprocess.run(
            [sys.executable, str(harness_project), "init",
             "--project", str(project), "--bundle", old_bundle,
             "--backend", "opencode", "--install-root", str(vendor)],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        old_pin = (project / ".superpowers" / "harness.json").read_bytes()
        status = run_git(vendor, "status", "--porcelain")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(status.stdout, "", "project enrollment must not dirty install")

        self.commit_on(origin, "README.md", "fixture version 2\n",
                       "origin-harness-update")
        new_head = self.head_sha(origin)
        result = run_script(SYNC, [str(vendor), "--json"])

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = self.parse_json_stdout(result)
        self.assertEqual(data["state"], "updated")
        self.assertEqual(self.head_sha(vendor), new_head)
        selected = (vendor / ".harness" / "selected").read_text(
            encoding="utf-8").strip()
        self.assertEqual(selected, "git-" + new_head[:12])
        self.assertTrue(
            (vendor / ".harness" / "bundles" / old_bundle).is_dir())
        self.assertTrue(
            (vendor / ".harness" / "bundles" / selected
             / "skills" / "two-model-sdd-pipeline" / "scripts"
             / "run-pipeline").is_file())
        self.assertEqual(
            (project / ".superpowers" / "harness.json").read_bytes(),
            old_pin)

    def test_behind_shows_diff_summary_before_update(self):
        origin, vendor = self.make_pair()
        self.commit_on(origin, "file.txt", "v2-diff\n", "origin-diff-subject-xyz")
        r = run_script(SYNC, [str(vendor)])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        combined = r.stdout + r.stderr
        self.assertIn("origin-diff-subject-xyz", combined)
        self.assertIn("file.txt", combined)

    def test_check_only_reports_behind_without_applying(self):
        origin, vendor = self.make_pair()
        before = self.head_sha(vendor)
        self.commit_on(origin, "file.txt", "v2\n", "origin-second-commit")
        remote = self.head_sha(origin)
        r = run_script(SYNC, [str(vendor), "--check-only", "--json"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = self.parse_json_stdout(r)
        self.assertEqual(data["state"], "behind")
        self.assertEqual(data["before_sha"], before)
        self.assertEqual(data["remote_sha"], remote)
        self.assertIn("file.txt", data["changed_paths"])
        self.assertEqual(self.head_sha(vendor), before)
        self.assertEqual((vendor / "file.txt").read_text(encoding="utf-8"), "v1\n")

    def test_ahead_returns_needs_user_merge_and_preserves_commit(self):
        origin, vendor = self.make_pair()
        self.commit_on(vendor, "local.txt", "mine\n", "local-ahead-commit")
        local_head = self.head_sha(vendor)
        r = run_script(SYNC, [str(vendor), "--json"])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        data = self.parse_json_stdout(r)
        self.assertEqual(data["state"], "needs_user_merge")
        self.assertNotEqual(data["errors"], [])
        self.assertEqual(self.head_sha(vendor), local_head)
        self.assertTrue((vendor / "local.txt").exists())
        log = run_git(vendor, "log", "--oneline")
        self.assertIn("local-ahead-commit", log.stdout)

    def test_diverged_returns_needs_user_merge_and_preserves_both(self):
        origin, vendor = self.make_pair()
        self.commit_on(vendor, "local.txt", "mine\n", "local-diverged-commit")
        local_head = self.head_sha(vendor)
        self.commit_on(origin, "file.txt", "v2\n", "origin-diverged-commit")
        r = run_script(SYNC, [str(vendor), "--json"])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        data = self.parse_json_stdout(r)
        self.assertEqual(data["state"], "needs_user_merge")
        self.assertEqual(self.head_sha(vendor), local_head)
        self.assertTrue((vendor / "local.txt").exists())
        log = run_git(vendor, "log", "--oneline")
        self.assertIn("local-diverged-commit", log.stdout)

    def test_dirty_and_untracked_returns_needs_user_merge_preserves_bytes(self):
        origin, vendor = self.make_pair()
        before = self.head_sha(vendor)
        self.commit_on(origin, "file.txt", "v2\n", "origin-second-commit")
        (vendor / "file.txt").write_text("dirty-local-bytes\n", encoding="utf-8")
        (vendor / "untracked-note.txt").write_text("keep-me\n", encoding="utf-8")
        (vendor / "staged.txt").write_text("staged-bytes\n", encoding="utf-8")
        run_git(vendor, "add", "staged.txt")
        r = run_script(SYNC, [str(vendor), "--json"])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        data = self.parse_json_stdout(r)
        self.assertEqual(data["state"], "needs_user_merge")
        self.assertEqual(self.head_sha(vendor), before)
        self.assertEqual((vendor / "file.txt").read_text(encoding="utf-8"),
                         "dirty-local-bytes\n")
        self.assertEqual((vendor / "untracked-note.txt").read_text(encoding="utf-8"),
                         "keep-me\n")
        self.assertEqual((vendor / "staged.txt").read_text(encoding="utf-8"),
                         "staged-bytes\n")

    def test_detached_head_returns_needs_user_merge(self):
        origin, vendor = self.make_pair()
        before = self.head_sha(vendor)
        self.commit_on(origin, "file.txt", "v2\n", "origin-second-commit")
        r = run_git(vendor, "checkout", "--detach", "HEAD")
        self.assertEqual(r.returncode, 0, r.stderr)
        detached = self.head_sha(vendor)
        self.assertEqual(detached, before)
        r = run_script(SYNC, [str(vendor), "--json"])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        data = self.parse_json_stdout(r)
        self.assertEqual(data["state"], "needs_user_merge")
        self.assertEqual(self.head_sha(vendor), detached)

    def test_offline_fetch_reports_error_without_mutation(self):
        origin, vendor = self.make_pair()
        before = self.head_sha(vendor)
        before_bytes = (vendor / "file.txt").read_text(encoding="utf-8")
        run_git(vendor, "remote", "set-url", "origin",
                str(self.tmp / "does-not-exist-xyz"))
        r = run_script(SYNC, [str(vendor), "--json"])
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        data = self.parse_json_stdout(r)
        self.assertEqual(data["state"], "error")
        self.assertNotEqual(data["errors"], [])
        self.assertEqual(self.head_sha(vendor), before)
        self.assertEqual((vendor / "file.txt").read_text(encoding="utf-8"),
                         before_bytes)

    def test_failed_inspection_blocks_mutation(self):
        origin, vendor = self.make_pair()
        before = self.head_sha(vendor)
        before_bytes = (vendor / "file.txt").read_text(encoding="utf-8")
        self.commit_on(origin, "file.txt", "v2\n", "origin-second-commit")
        git_dir = vendor / ".git"
        self.assertTrue(git_dir.is_dir())
        (git_dir / "index").write_bytes(b"corrupt-index-xyz\n")
        probe = run_git(vendor, "status", "--porcelain")
        self.assertNotEqual(probe.returncode, 0)
        r = run_script(SYNC, [str(vendor), "--json"])
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        data = self.parse_json_stdout(r)
        self.assertEqual(data["state"], "error")
        self.assertNotEqual(data["errors"], [])
        self.assertEqual((vendor / "file.txt").read_text(encoding="utf-8"),
                         before_bytes)

    def test_invalid_invocation_returns_exit_two(self):
        origin, vendor = self.make_pair()
        r = run_script(SYNC, [str(vendor), "--bogus-flag-xyz", "--json"])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_remote_mismatch_returns_needs_user_merge(self):
        origin, vendor = self.make_pair()
        before = self.head_sha(vendor)
        other = self.tmp / "other-remote"
        other.mkdir()
        run_git(other, "init", "-q", "-b", "main")
        run_git(other, "config", "user.email", "test@example.com")
        run_git(other, "config", "user.name", "Test")
        (other / "file.txt").write_text("other\n", encoding="utf-8")
        run_git(other, "add", "-A")
        run_git(other, "commit", "-qm", "other-initial")
        env = {"REPO_URL": str(other)}
        r = run_script(SYNC, [str(vendor), "--json"], env_extra=env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        data = self.parse_json_stdout(r)
        self.assertEqual(data["state"], "needs_user_merge")
        self.assertEqual(self.head_sha(vendor), before)

    def test_validation_failure_preserves_checkout_and_no_rollback_claim(self):
        origin, vendor = self.make_pair()
        before = self.head_sha(vendor)
        suite_dir = origin / "skills" / "demo" / "tests"
        suite_dir.mkdir(parents=True)
        runner = suite_dir / "run-tests.sh"
        runner.write_text("#!/usr/bin/env bash\necho 'candidate suite fails'\nexit 1\n",
                          encoding="utf-8")
        subprocess.run([BASH, "-c", "chmod +x '{}'".format(str(runner))],
                       capture_output=True)
        run_git(origin, "add", "-A")
        r = run_git(origin, "commit", "-qm", "origin-bad-candidate")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_script(SYNC, [str(vendor), "--json"])
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        data = self.parse_json_stdout(r)
        self.assertEqual(data["state"], "error")
        self.assertEqual(self.head_sha(vendor), before)
        self.assertEqual((vendor / "file.txt").read_text(encoding="utf-8"), "v1\n")
        combined = (r.stdout + r.stderr).lower()
        self.assertNotIn("rollback", combined)

    def test_explicit_vendor_path_with_spaces(self):
        spaced = self.tmp / "dir with spaces"
        origin, vendor = self.make_pair(under=spaced)
        before = self.head_sha(vendor)
        r = run_script(SYNC, [str(vendor), "--json"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = self.parse_json_stdout(r)
        self.assertEqual(data["state"], "unchanged")
        self.assertEqual(data["before_sha"], before)

    def test_check_accepts_worktree_git_file_and_reports_json(self):
        origin, vendor = self.make_pair()
        wt = self.tmp / "linked-wt"
        r = run_git(vendor, "worktree", "add", str(wt), "-b", "wt-branch")
        self.assertEqual(r.returncode, 0, r.stderr)
        dotgit = wt / ".git"
        self.assertTrue(dotgit.is_file())
        r = run_script(CHECK, [str(wt), "--json"])
        self.assertIn(r.returncode, (0, 1), r.stdout + r.stderr)
        data = self.parse_json_stdout(r)
        self.assertIn(data["state"], ("unchanged", "needs_user_merge", "behind", "error"))

    def test_check_behind_reports_behind_without_mutation(self):
        origin, vendor = self.make_pair()
        before = self.head_sha(vendor)
        self.commit_on(origin, "file.txt", "v2\n", "origin-second-commit")
        remote = self.head_sha(origin)
        r = run_script(CHECK, [str(vendor), "--json"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = self.parse_json_stdout(r)
        self.assertEqual(data["state"], "behind")
        self.assertEqual(data["before_sha"], before)
        self.assertEqual(data["remote_sha"], remote)
        self.assertEqual(self.head_sha(vendor), before)


if __name__ == "__main__":
    unittest.main()
