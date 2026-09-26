"""Black-box tests for canonical documentation (Round 1 Task 4).

Contract under test: README.md is the single canonical operational and
architectural reference; root CONTEXT.md and README-LLM.md are retired;
every active consumer migrated; brainstorming approval proceeds directly
to spec and plan; startup applies the safe update; Round 1 honesty about
Codex execution is documented.

Acceptance encoded here (plan task 4):
  README.md carries the migrated operational/architectural content;
  orientation, prompts, skills, packaging and doc-check consumers are
  updated before the retired files are deleted; active references to
  retired paths are rejected while historical ADR/spec records are
  preserved; approved brainstorming proceeds directly to spec and plan
  without a second written-spec approval; startup may apply the
  validated safe update while pins and active runs stay unchanged;
  Round 1 honestly documents that no working Codex pipeline ships yet
  and that package smoke checks validate files and contract fixtures,
  not live model behavior; first use enrolls only that project and
  later bundle changes update the pin only on user acceptance.

Expectations are hand-derived literals. These tests read shipped files
and run shipped scripts as real processes against disposable
repositories, so the missing migration fails as assertion errors, not
as collection errors.
"""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent.parent
SKILLS = REPO / "skills"
TWO_MODEL = SKILLS / "two-model-sdd-pipeline"
SCRIPTS = TWO_MODEL / "scripts"

if os.name == "nt":
    git_bash = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
    BASH = str(git_bash) if git_bash.exists() else "bash"
else:
    BASH = "bash"


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


# Every file that actively consumes the harness reference today. The
# brief requires each of them migrated in this same task; historical
# ADR/spec/plan records are explicitly excluded (they are preserved).
# README.md and README.txt document the retirement itself, so they carry
# their own assertions below instead of the strict absence check.
ACTIVE_CONSUMERS = (
    "skills/using-superpowers/SKILL.md",
    "skills/brainstorming/SKILL.md",
    "skills/writing-plans/SKILL.md",
    "skills/two-model-sdd-pipeline/SKILL.md",
    "skills/flutter-app-pipeline/SKILL.md",
    "skills/finishing-a-development-branch/SKILL.md",
    "skills/writing-skills/SKILL.md",
    "skills/skill-scripter/SKILL.md",
    "skills/write-script/SKILL.md",
    "agent/flutter-pipeline.md",
    "skills/brainstorming/scripts/orient-llm",
    "skills/two-model-sdd-pipeline/scripts/doc-check",
    "skills/two-model-sdd-pipeline/scripts/run-pipeline",
    "scripts/install-superpowers",
    ".opencode/INSTALL.md",
)


def run_bash(script, args):
    return subprocess.run(
        [BASH, str(script), *args],
        capture_output=True,
        text=True,
        env=dict(os.environ),
    )


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args],
                   capture_output=True, check=True)


def make_commit(repo, file_rel, content, msg):
    path = pathlib.Path(repo) / file_rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", msg)


def make_commit_files(repo, files, msg):
    for file_rel, content in files.items():
        path = pathlib.Path(repo) / file_rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", msg)


class TestRetiredDocuments(unittest.TestCase):
    def test_context_md_is_retired(self):
        self.assertFalse(
            (REPO / "CONTEXT.md").exists(),
            "root CONTEXT.md must be retired in favor of README.md")

    def test_readme_llm_is_retired(self):
        self.assertFalse(
            (REPO / "README-LLM.md").exists(),
            "root README-LLM.md must be retired in favor of README.md")

    def test_readme_documents_the_retirement(self):
        text = read("README.md")
        self.assertIn("CONTEXT.md", text)
        self.assertIn("README-LLM.md", text)
        self.assertIn("retire", text.lower())

    def test_readme_txt_documents_the_retirement(self):
        text = read("README.txt")
        self.assertIn("CONTEXT.md", text)
        self.assertIn("README-LLM.md", text)
        self.assertIn("retire", text.lower())
        self.assertIn("README.md", text)

    def test_readme_is_declared_single_canonical(self):
        text = read("README.md")
        self.assertIn("single canonical", text)

    def test_readme_drops_live_llm_reference(self):
        text = read("README.md")
        self.assertNotIn("applying the principles from `README-LLM.md`", text)

    def test_historical_records_are_preserved(self):
        adr = REPO / "docs" / "superpowers" / "adr"
        self.assertTrue(adr.is_dir())
        self.assertTrue(
            list(adr.glob("*.md")),
            "historical ADR records must be preserved")
        specs = REPO / "docs" / "superpowers" / "specs"
        self.assertTrue(
            (specs / "2026-09-25-codex-pipeline-design.md").is_file())
        self.assertTrue(
            (specs / "2026-09-25-confirmed-pipeline-decisions.md").is_file())


class TestNoActiveRetiredReferences(unittest.TestCase):
    def test_no_active_consumer_names_readme_llm(self):
        offenders = [rel for rel in ACTIVE_CONSUMERS
                     if "README-LLM.md" in read(rel)]
        self.assertEqual(
            offenders, [],
            "active consumers must not reference the retired path: %r"
            % (offenders,))

    def test_no_active_consumer_names_context_md(self):
        offenders = [rel for rel in ACTIVE_CONSUMERS
                     if "CONTEXT.md" in read(rel)]
        self.assertEqual(
            offenders, [],
            "active consumers must not reference the retired path: %r"
            % (offenders,))

    def test_active_consumers_point_at_readme(self):
        missing = [rel for rel in ACTIVE_CONSUMERS
                   if "README.md" not in read(rel)]
        self.assertEqual(
            missing, [],
            "migrated consumers must point at README.md: %r" % (missing,))


class TestCanonicalContent(unittest.TestCase):
    def test_readme_carries_architecture_glossary(self):
        text = read("README.md")
        for marker in ("Script CEO", "Category Skeleton",
                       "complete `plan.json`", "punctual",
                       "sole independent semantic guarantee",
                       "red-form-check"):
            self.assertIn(marker, text,
                          "README.md must migrate %r" % marker)

    def test_readme_carries_research_and_quality_content(self):
        text = read("README.md")
        for marker in ("template-search", "(points / 160) × 20",
                       "apple-design"):
            self.assertIn(marker, text,
                          "README.md must migrate %r" % marker)

    def test_readme_carries_harness_binding_content(self):
        text = read("README.md")
        for marker in ("harness-project init", "entrypoints",
                       "[5, 3, 3]", "30 days"):
            self.assertIn(marker, text,
                          "README.md must document %r" % marker)

    def test_readme_states_round_1_honesty(self):
        text = read("README.md")
        self.assertIn(
            "Round 1 does not yet supply a working Codex pipeline", text)
        self.assertIn(
            "smoke checks validate files and contract fixtures, "
            "not live model behavior", text)

    def test_readme_states_enrollment_policy(self):
        text = read("README.md")
        self.assertIn("only the project in use", text)
        self.assertIn("only on user acceptance", text)
        self.assertIn("Active runs retain their original version", text)

    def test_readme_names_both_backends(self):
        text = read("README.md")
        self.assertIn("codex", text)
        self.assertIn("opencode", text)


class TestOrientation(unittest.TestCase):
    def test_orient_llm_prints_canonical_readme(self):
        result = run_bash(SKILLS / "brainstorming" / "scripts" / "orient-llm",
                          [str(REPO)])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("single canonical", result.stdout)

    def test_orient_llm_missing_readme_exits_one(self):
        tmp = tempfile.mkdtemp(prefix="orient-llm-doc-tests-")
        try:
            result = run_bash(
                SKILLS / "brainstorming" / "scripts" / "orient-llm", [tmp])
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("README.md", result.stdout + result.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class DocCheckBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="doc-check-doc-tests-")
        self.repo = pathlib.Path(self._tmp) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "t")
        make_commit(self.repo, "lib/app.dart", "void main() {}", "feat: initial")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def run_it(self):
        return run_bash(SCRIPTS / "doc-check", [str(self.repo)])


class TestDocCheckCanonical(DocCheckBase):
    def test_pipeline_change_with_readme_md_passes(self):
        make_commit_files(self.repo, {
            "skills/foo/SKILL.md": "skill",
            "README.md": "canonical",
        }, "feat: skill and canonical readme")
        result = self.run_it()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_pipeline_change_without_readme_fails_on_canonical(self):
        make_commit(self.repo, "skills/bar/SKILL.md", "skill", "feat: skill")
        result = self.run_it()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("README.md", result.stdout + result.stderr)

    def test_pipeline_change_with_only_readme_txt_fails(self):
        make_commit_files(self.repo, {
            "skills/bar/SKILL.md": "skill",
            "README.txt": "secondary",
        }, "feat: skill and text readme")
        result = self.run_it()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("README.md", result.stdout + result.stderr)

    def test_pipeline_change_with_only_alternate_markdown_readme_fails(self):
        make_commit_files(self.repo, {
            "skills/bar/SKILL.md": "skill",
            "README-ALT.md": "secondary",
        }, "feat: skill and alternate readme")
        result = self.run_it()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("README.md", result.stdout + result.stderr)

    def test_doc_check_names_no_retired_path(self):
        text = read("skills/two-model-sdd-pipeline/scripts/doc-check")
        self.assertNotIn("README-LLM.md", text)


class TestBrainstormingApprovalFlow(unittest.TestCase):
    def test_no_second_written_spec_approval(self):
        text = read("skills/brainstorming/SKILL.md")
        self.assertNotIn("User reviews written spec", text)
        self.assertNotIn(
            "ask user to review the spec file before proceeding", text)
        self.assertNotIn('"User reviews spec?"', text)

    def test_design_approval_permits_spec_and_plan(self):
        text = read("skills/brainstorming/SKILL.md")
        self.assertIn("without another written-spec approval", text)
        self.assertIn("writing-plans", text)

    def test_writing_plans_notes_direct_transition(self):
        text = read("skills/writing-plans/SKILL.md")
        self.assertIn("without another written-spec approval", text)


class TestStartupAndPipelineDocs(unittest.TestCase):
    def test_startup_describes_safe_update(self):
        text = read("skills/using-superpowers/SKILL.md")
        self.assertNotIn("fetch + reset", text)
        self.assertIn("diff summary", text)
        self.assertIn("preserves project pins", text)

    def test_startup_validates_candidate(self):
        text = read("skills/using-superpowers/SKILL.md")
        self.assertIn("validates the candidate", text)

    def test_pipeline_skill_states_enrollment(self):
        text = read("skills/two-model-sdd-pipeline/SKILL.md")
        self.assertIn("harness-project init", text)
        self.assertIn("only the project in use", text)

    def test_pipeline_skill_states_codex_honesty(self):
        text = read("skills/two-model-sdd-pipeline/SKILL.md")
        self.assertIn(
            "Round 1 does not yet supply a working Codex pipeline", text)

    def test_flutter_skill_states_codex_honesty(self):
        text = read("skills/flutter-app-pipeline/SKILL.md")
        self.assertIn(
            "Round 1 does not yet supply a working Codex pipeline", text)

    def test_run_pipeline_closing_names_canonical_readme(self):
        text = read("skills/two-model-sdd-pipeline/scripts/run-pipeline")
        self.assertIn("update README.md, then re-run", text)

    def test_install_documents_entry_points(self):
        text = read("scripts/install-superpowers")
        self.assertIn("entrypoints", text)
        self.assertIn("harness_install", text)

    def test_install_names_no_retired_path(self):
        text = read("scripts/install-superpowers")
        self.assertNotIn("README-LLM.md", text)
        self.assertNotIn("CONTEXT.md", text)

    def test_opencode_install_documents_bundle(self):
        text = read(".opencode/INSTALL.md")
        self.assertIn("entrypoints", text)
        self.assertIn("harness-project", text)
        self.assertIn(".config/opencode/vendor/superpowers/.harness/entrypoints/opencode.sh", text)
        self.assertNotIn("\n.harness/entrypoints/opencode.sh", text)

    def test_opencode_install_uses_this_fork(self):
        for rel in (".opencode/INSTALL.md", "docs/README.opencode.md"):
            text = read(rel)
            self.assertIn(
                "git+https://github.com/CarlosMonteiroNeto/"
                "superpowers-two-model-pipeline.git", text)
            self.assertNotIn(
                "git+https://github.com/obra/superpowers.git", text)

    def test_readme_examples_point_to_the_installed_entrypoint(self):
        readme = read("README.md")
        text_readme = read("README.txt")
        expected = (
            "${SUPERPOWERS_DIR:-$HOME/.config/opencode/vendor/superpowers}"
            "/.harness/entrypoints/opencode.sh")
        self.assertIn(expected, readme)
        self.assertIn(expected, text_readme)
        self.assertNotIn("\n.harness/entrypoints/opencode.sh", readme)
        self.assertNotIn("\n.harness/entrypoints/opencode.sh", text_readme)

    def test_readme_txt_describes_fast_forward_sync(self):
        text = read("README.txt").lower()
        self.assertIn("fast-forward", text)
        self.assertNotIn("fetch + reset", text)

    def test_active_workflow_docs_resolve_entrypoint_from_vendor_checkout(self):
        expected = (
            "${SUPERPOWERS_DIR:-$HOME/.config/opencode/vendor/superpowers}"
            "/.harness/entrypoints/opencode.sh")
        consumers = (
            "README.md",
            "README.txt",
            ".opencode/INSTALL.md",
            "agent/flutter-pipeline.md",
            "skills/brainstorming/SKILL.md",
            "skills/writing-plans/SKILL.md",
            "skills/two-model-sdd-pipeline/SKILL.md",
        )
        missing = [rel for rel in consumers if expected not in read(rel)]
        self.assertEqual(
            missing, [],
            "entry point references must include the install root: %r"
            % (missing,))

    def test_package_script_archives_agent_prompts(self):
        text = read("scripts/package-codex-plugin.sh")
        self.assertIn("  agent \\", text)


if __name__ == "__main__":
    unittest.main()
