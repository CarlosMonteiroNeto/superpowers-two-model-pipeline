"""Task 1 RED: adapted instruction cores carry investigation, debugging,
destination-mapped provenance, and no unbounded-retry promises."""

import json
import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
SKILL = ROOT / "skills" / "two-model-sdd-pipeline"
PROMPTS = SKILL / "prompts"

ACTIVE_TEMPLATES = [
    SKILL / "coder-prompt.md",
    SKILL / "reviewer-prompt.md",
    SKILL / "controller-brief-prompt.md",
    SKILL / "codex" / "operator.md",
    SKILL / "codex" / "reviewer.md",
    SKILL / "codex" / "director.md",
]

FORBIDDEN_RETRY = [
    re.compile(r"no budget, no counting", re.IGNORECASE),
    re.compile(r"retries until the gate passes", re.IGNORECASE),
    re.compile(r"never hands back", re.IGNORECASE),
    re.compile(r"unlimited retr", re.IGNORECASE),
    re.compile(r"infinite retr", re.IGNORECASE),
    re.compile(r"retry forever", re.IGNORECASE),
]


class PromptAdaptationContractTests(unittest.TestCase):
    def test_operator_has_investigation_and_debugging_contract(self):
        path = PROMPTS / "core-operator.md"
        self.assertTrue(path.is_file(), "operator core must exist")
        text = path.read_text(encoding="utf-8")
        folded = text.casefold()
        headings = [
            line.strip("# ").strip().casefold()
            for line in text.splitlines()
            if line.startswith("#")
        ]
        self.assertTrue(
            any("investigat" in h or "debug" in h for h in headings),
            "operator core needs a dedicated investigation/debugging section",
        )
        for marker in (
            "investigat",
            "root cause",
            "reproduc",
            "working path",
            "evidence-backed",
            "review finding",
        ):
            self.assertIn(
                marker, folded,
                "operator core must cover %r explicitly" % marker,
            )

    def test_reviewer_covers_diff_inspection_and_director_covers_arbitration(self):
        for core, markers in (
                ("core-reviewer.md",
                 ("complete diff", "test-quality", "evidence-backed")),
                ("core-director.md",
                 ("scope arbitration", "requirement", "bounded"))):
            with self.subTest(core=core):
                path = PROMPTS / core
                self.assertTrue(path.is_file(), "role core must exist")
                folded = path.read_text(encoding="utf-8").casefold()
                for marker in markers:
                    self.assertIn(
                        marker, folded,
                        "%s must cover %r explicitly" % (core, marker),
                    )

    def test_all_adaptations_have_source_and_destination(self):
        path = PROMPTS / "adaptation-map.json"
        self.assertTrue(path.is_file(), "adaptation map must exist")
        records = json.loads(path.read_text(encoding="utf-8"))["sections"]
        self.assertGreater(len(records), 0, "adaptation map must not be empty")
        for record in records:
            with self.subTest(section=record.get("section")):
                for field in ("role", "source_path", "section",
                              "decision", "reason"):
                    self.assertTrue(
                        record.get(field),
                        "adaptation record keeps source identity field %r"
                        % field,
                    )
                self.assertTrue(
                    record.get("destination"),
                    "adaptation record %r needs a destination section "
                    "in the role core" % (record.get("section"),),
                )

    def test_active_templates_do_not_promise_unlimited_retries(self):
        for template in ACTIVE_TEMPLATES:
            with self.subTest(template=template.name):
                self.assertTrue(
                    template.is_file(),
                    "active template must exist: %s" % template,
                )
                text = template.read_text(encoding="utf-8")
                hits = sorted({
                    pattern.pattern
                    for pattern in FORBIDDEN_RETRY
                    if pattern.search(text)
                })
                self.assertEqual(
                    [], hits,
                    "template %s promises unbounded retries: %s"
                    % (template.name, hits),
                )


if __name__ == "__main__":
    unittest.main()
