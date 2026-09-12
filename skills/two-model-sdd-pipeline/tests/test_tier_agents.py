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


if __name__ == "__main__":
    unittest.main()
