"""Black-box tests for the decoupled-pipeline documentation (design 1-5).

These read the shipped markdown artifacts and assert task 6's acceptance:
brainstorming/writing-plans author a complete plan.json without expected_red;
the two-model and TDD skills describe the deterministic form check and the
revisor as the sole semantic guarantee; ADR-0008 records the decision and
supersedes ADR-0006; README.txt and README-LLM.md reflect the change.

Expectations are hand-derived literals naming the documented behavior, not
values computed by any code under test.
"""
import pathlib
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


class TestBrainstormingAuthorsCompletePlan(unittest.TestCase):
    def test_brainstorming_names_complete_plan_json(self):
        """Brainstorming authors the spec AND every task in full."""
        text = read("skills/brainstorming/SKILL.md")
        self.assertIn("complete `plan.json`", text)

    def test_brainstorming_forbids_expected_red(self):
        text = read("skills/brainstorming/SKILL.md")
        self.assertIn("no `expected_red`", text)

    def test_writing_plans_names_complete_plan_json(self):
        text = read("skills/writing-plans/SKILL.md")
        self.assertIn("complete `plan.json`", text)

    def test_writing_plans_drops_expected_red_requirement(self):
        """The old rule made acceptance + expected_red mandatory; it is gone."""
        text = read("skills/writing-plans/SKILL.md")
        self.assertIn("no `expected_red`", text)
        self.assertNotIn("without acceptance + `expected_red`", text)


class TestDeterministicFormAndSoleGuarantee(unittest.TestCase):
    def test_two_model_documents_form_check(self):
        text = read("skills/two-model-sdd-pipeline/SKILL.md")
        self.assertIn("red-form-check", text)

    def test_two_model_names_revisor_as_sole_guarantee(self):
        text = read("skills/two-model-sdd-pipeline/SKILL.md")
        self.assertIn("sole independent semantic guarantee", text)

    def test_two_model_documents_punctual_ownership(self):
        text = read("skills/two-model-sdd-pipeline/SKILL.md")
        self.assertIn("No EXPAND", text)
        self.assertIn("punctual", text)

    def test_tdd_documents_form_check(self):
        text = read("skills/test-driven-development/SKILL.md")
        self.assertIn("red-form-check", text)

    def test_tdd_names_revisor_as_sole_guarantee(self):
        text = read("skills/test-driven-development/SKILL.md")
        self.assertIn("sole independent semantic guarantee", text)

    def test_tdd_drops_expected_red_from_plan(self):
        text = read("skills/test-driven-development/SKILL.md")
        self.assertIn("no `expected_red`", text)


class TestAdr0008(unittest.TestCase):
    def test_adr_exists_and_supersedes_0006(self):
        text = read("docs/superpowers/adr/0008-brainstorming-pipeline-decoupling.md")
        self.assertIn("ADR-0006", text)
        self.assertIn("Supersedes", text)

    def test_adr_records_form_check_and_sole_guarantee(self):
        text = read("docs/superpowers/adr/0008-brainstorming-pipeline-decoupling.md")
        self.assertIn("red-form-check", text)
        self.assertIn("sole", text.lower())
        self.assertIn("semantic guarantee", text.lower())

    def test_adr_records_complete_plan_without_expected_red(self):
        text = read("docs/superpowers/adr/0008-brainstorming-pipeline-decoupling.md")
        self.assertIn("COMPLETE `plan.json`", text)
        self.assertIn("no `expected_red`", text)


class TestReadmesReflectChange(unittest.TestCase):
    def test_readme_txt_documents_form_check(self):
        text = read("README.txt")
        self.assertIn("red-form-check", text)

    def test_readme_txt_documents_decoupled_plan(self):
        text = read("README.txt")
        self.assertIn("complete `plan.json`", text)
        self.assertIn("punctual", text)
        self.assertNotIn("expands plan tasks", text)

    def test_readme_llm_documents_form_check(self):
        text = read("README-LLM.md")
        self.assertIn("red-form-check", text)

    def test_readme_llm_documents_sole_guarantee(self):
        text = read("README-LLM.md")
        self.assertIn("sole independent semantic guarantee", text)

    def test_readme_llm_documents_punctual_ownership(self):
        text = read("README-LLM.md")
        self.assertIn("complete `plan.json`", text)
        self.assertNotIn("expands plan tasks", text)


if __name__ == "__main__":
    unittest.main()
