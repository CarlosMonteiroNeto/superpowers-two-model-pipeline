"""Black-box tests for the decoupled tier agent definitions and prompts.

Task 5 acceptance (spec §4/§5): the task-generator loses the EXPAND mode and
documents the script-controlled context for corrective/arbitrate/closing; the
coder declares and confirms the reason before implementing and saves the RED in
the runner's machine-readable format; no prompt references the brief's
expected-failure text.

The deliverable is the definitions and prompt templates themselves, so the
consumed artifact is read as plain text and asserted against hand-derived
literals from the spec (same convention as test_skill_content.py).
"""
import pathlib
import unittest

SKILL_DIR = pathlib.Path(__file__).resolve().parent.parent
REPO = SKILL_DIR.parent.parent

TASK_GEN_AGENT = REPO / "agent" / "two-model-task-generator.md"
TASK_GEN_PROMPT = SKILL_DIR / "task-generator-prompt.md"
CODER_AGENT = REPO / "agent" / "two-model-coder.md"
CODER_PROMPT = SKILL_DIR / "coder-prompt.md"


def read(path):
    return path.read_text(encoding="utf-8")


class TestTaskGeneratorLosesExpand(unittest.TestCase):
    """The plan arrives complete from brainstorming: the task-generator must
    not carry an EXPAND mode anywhere in its definition or prompt."""

    def test_definition_has_no_expand_mode(self):
        text = read(TASK_GEN_AGENT).lower()
        self.assertNotIn(
            "expand",
            text,
            "task-generator definition must not contain an EXPAND mode",
        )

    def test_prompt_has_no_expand_mode(self):
        text = read(TASK_GEN_PROMPT).lower()
        self.assertNotIn(
            "expand",
            text,
            "task-generator prompt must not contain an EXPAND mode",
        )


class TestTaskGeneratorControlledContext(unittest.TestCase):
    """Corrective/arbitrate run on script-controlled context (findings + full
    plan.json + target task + cited spec_refs); closing runs on a curated
    package (plan + spec + consolidated diff + full ledger)."""

    def test_definition_documents_script_controlled_context(self):
        text = read(TASK_GEN_AGENT).lower()
        self.assertIn("script-controlled context", text)
        self.assertIn("curated", text)

    def test_definition_names_the_punctual_modes(self):
        text = read(TASK_GEN_AGENT).lower()
        for mode in ("corrective", "arbitrate", "closing"):
            self.assertIn(mode, text)

    def test_prompt_documents_corrective_and_arbitrate_context(self):
        text = read(TASK_GEN_PROMPT).lower()
        for token in ("corrective", "arbitrate", "findings", "full",
                      "plan.json", "target task", "spec_refs"):
            self.assertIn(token, text)

    def test_prompt_documents_closing_curated_package(self):
        text = read(TASK_GEN_PROMPT).lower()
        for token in ("closing", "spec", "consolidated diff", "ledger"):
            self.assertIn(token, text)


class TestCoderMachineReadableRed(unittest.TestCase):
    """The operador saves the RED run in the runner's machine-readable format
    and declares and confirms the expected reason before implementing."""

    def test_definition_requires_machine_readable_red(self):
        text = read(CODER_AGENT).lower()
        self.assertIn("machine-readable", text)

    def test_prompt_requires_machine_readable_red(self):
        text = read(CODER_PROMPT).lower()
        self.assertIn("machine-readable", text)

    def test_definition_declares_and_confirms_reason_before_implementing(self):
        text = read(CODER_AGENT).lower()
        for token in ("declare", "confirm", "reason", "before implementing"):
            self.assertIn(token, text)

    def test_prompt_declares_and_confirms_reason_before_implementing(self):
        text = read(CODER_PROMPT).lower()
        for token in ("declare", "confirm", "reason", "before implementing"):
            self.assertIn(token, text)


class TestNoExpectedFailureTextInPrompts(unittest.TestCase):
    """No prompt may reference the brief's expected-failure text: the RED-form
    check replaced the expected_red grep (spec §4)."""

    def assert_no_expected_failure_text(self, path):
        text = read(path).lower()
        for token in ("expected_red", "expected failure", "expected-failure"):
            self.assertNotIn(
                token,
                text,
                "%s must not reference the brief's expected-failure text"
                % path.name,
            )

    def test_task_generator_prompt_has_no_expected_failure_text(self):
        self.assert_no_expected_failure_text(TASK_GEN_PROMPT)

    def test_coder_prompt_has_no_expected_failure_text(self):
        self.assert_no_expected_failure_text(CODER_PROMPT)


class TestOperationalVariants(unittest.TestCase):
    """C3: each detected ecosystem has an operador variant whose bash
    allowlist can execute that ecosystem's test/analyze/format commands; the
    per-agent session record and the write-only contract are preserved."""

    VARIANTS = {
        "two-model-coder-python.md": "pytest",
        "two-model-coder-node.md": "npm",
        "two-model-coder-rust.md": "cargo",
        "two-model-coder-go.md": "go",
    }

    def test_each_variant_exists_and_is_primary(self):
        for name, token in self.VARIANTS.items():
            path = REPO / "agent" / name
            self.assertTrue(path.exists(), "%s missing" % name)
            text = read(path)
            self.assertIn("mode: all", text)
            self.assertIn(token, text)
            self.assertIn("machine-readable", text.lower())

    def test_variants_keep_the_write_only_contract(self):
        for name in self.VARIANTS:
            text = read(REPO / "agent" / name).lower()
            self.assertIn("never run git", text)
            self.assertIn("never weaken a test", text)


class TestAgentDefinitionsArePortable(unittest.TestCase):
    """A definition ships to any machine that clones the repo: it must not
    hardcode one user's home path, and the scoped runner must be permitted by a
    location-independent pattern rather than an absolute install path.

    Regression: the coder allowlist pinned rtk-run to
    `/c/Users/Carlos_Neto/.config/opencode/vendor/...`, which can never match on
    any other machine (and silently fell back to raw `flutter test`)."""

    HOME_MARKERS = ("/c/Users/", "C:/Users/", "C:\\Users\\", "/home/")

    def test_no_agent_definition_hardcodes_a_user_home_path(self):
        offenders = []
        for path in sorted((REPO / "agent").glob("*.md")):
            text = read(path)
            for marker in self.HOME_MARKERS:
                if marker in text:
                    offenders.append("%s: %s" % (path.name, marker))
        self.assertEqual(
            offenders, [],
            "agent definitions must be machine-independent: %s" % offenders,
        )

    def test_coder_allows_the_scoped_runner_by_a_portable_pattern(self):
        text = read(CODER_AGENT)
        rules = [
            line.strip() for line in text.splitlines()
            if "rtk-run" in line and ": allow" in line
        ]
        self.assertTrue(rules, "the coder must allow the scoped rtk-run runner")
        # Both ends must be wildcards: the operador's shell may wrap the call
        # (`& "<path>"`, `bash "<path>"`, bare) and quotes follow the path, so
        # a pattern anchored to `rtk-run ` (space) never matches. And it must
        # not be an absolute path, which could not ship to another machine.
        self.assertTrue(
            any(r.startswith('"*') and r.rstrip().endswith('*": allow')
                and "flutter-app-pipeline/scripts/rtk-run" in r
                for r in rules),
            "rtk-run must be allowed by a two-sided wildcard, "
            "install-independent pattern, not an absolute path: %s" % rules,
        )


    def test_coder_carries_platform_generic_read_only_allowances(self):
        # Read-only exploration belongs in the mirror (not a per-machine
        # override): it must cover both shells' vocabularies.
        text = read(CODER_AGENT)
        for rule in ('"Get-ChildItem*": allow', '"Get-Content*": allow',
                     '"Test-Path*": allow', '"ls*": allow', '"cat*": allow',
                     '"rg*": allow'):
            self.assertIn(rule, text)

    def test_coder_shell_flexibility_is_deliberate(self):
        # The generic interpreters are allowed on purpose: removing them
        # measurably inflated the operador's step count. If the posture
        # tightens, this test is the place that must change with it.
        text = read(CODER_AGENT)
        for rule in ('"bash*": allow', '"python3*": allow', '"python*": allow'):
            self.assertIn(rule, text)


if __name__ == "__main__":
    unittest.main()
