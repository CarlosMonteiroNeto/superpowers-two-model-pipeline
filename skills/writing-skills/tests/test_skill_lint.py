import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
LINT = SCRIPTS / "skill-lint"

GOOD = """\
---
name: good-skill
description: Use when testing the lint with a minimal skill
---

# Good Skill

Short on purpose.
"""


def run_lint(skill_dir, *args):
    env = dict(os.environ)
    return subprocess.run(
        [sys.executable, str(LINT), str(skill_dir), *args],
        capture_output=True,
        text=True,
        env=env,
    )


class SkillLintTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="skill-lint-tests-"))

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def skill(self, body):
        d = self._tmp / "skill"
        d.mkdir(exist_ok=True)
        (d / "SKILL.md").write_text(body, encoding="utf-8")
        return d


class TestSkillLint(SkillLintTestBase):
    def test_good_skill_passes(self):
        r = run_lint(self.skill(GOOD))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OK", r.stdout)

    def test_missing_skill_is_violation(self):
        r = run_lint(self._tmp / "nonexistent")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_missing_frontmatter_is_violation(self):
        r = run_lint(self.skill("# No frontmatter here\n"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_bad_name_charset_is_violation(self):
        body = GOOD.replace("name: good-skill", "name: Bad_Skill (v2)")
        r = run_lint(self.skill(body))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_description_must_start_with_use_when(self):
        body = GOOD.replace(
            "description: Use when testing the lint with a minimal skill",
            "description: A skill about testing things",
        )
        r = run_lint(self.skill(body))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_long_description_is_violation(self):
        body = GOOD.replace(
            "description: Use when testing the lint with a minimal skill",
            "description: Use when " + "x" * 500,
        )
        r = run_lint(self.skill(body))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_word_budget_enforced_per_tier(self):
        body = GOOD + "\n" + ("word " * 200) + "\n"
        r = run_lint(self.skill(body), "--tier", "getting-started")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        r = run_lint(self.skill(body))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_unbalanced_dot_block_is_violation(self):
        body = GOOD + "\n```dot\ndigraph x {\n\"a\" -> \"b\";\n```\n"
        r = run_lint(self.skill(body))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_unterminated_dot_block_is_violation(self):
        body = GOOD + "\n```dot\ndigraph x {\n"
        r = run_lint(self.skill(body))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_branch_coverage_warns_without_gate(self):
        body = GOOD + (
            "\n```dot\n"
            'digraph x {\n'
            '    "Classify: spike / bounded" [shape=diamond];\n'
            '    "Do research" [shape=box];\n'
            '    "Classify: spike / bounded" -> "Do research" [label="spike"];\n'
            "}\n```\n"
        )
        r = run_lint(self.skill(body))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("warning", r.stderr.lower())

    def test_branch_coverage_passes_with_human_gate(self):
        body = GOOD + (
            "\n```dot\n"
            'digraph x {\n'
            '    "Classify: spike / bounded" [shape=diamond];\n'
            '    "Human approves?" [shape=diamond];\n'
            '    "Report" [shape=doublecircle];\n'
            '    "Classify: spike / bounded" -> "Human approves?" [label="spike"];\n'
            '    "Human approves?" -> "Report" [label="yes"];\n'
            "}\n```\n"
        )
        r = run_lint(self.skill(body))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("warning", r.stderr.lower())

    def test_bad_args_is_usage(self):
        r = run_lint(self.skill(GOOD), "--tier", "nope")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        r = subprocess.run(
            [sys.executable, str(LINT)],
            capture_output=True, text=True, env=dict(os.environ),
        )
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
