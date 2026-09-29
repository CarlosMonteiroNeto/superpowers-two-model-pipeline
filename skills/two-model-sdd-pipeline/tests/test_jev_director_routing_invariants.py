import pathlib
import unittest


REPO = pathlib.Path(__file__).resolve().parents[3]
TASK_RUN = REPO / "skills" / "two-model-sdd-pipeline" / "scripts" / "task-run"


class DirectorRoutingInvariantTests(unittest.TestCase):
    def setUp(self):
        self.text = TASK_RUN.read_text(encoding="utf-8")

    def test_both_episode_boundaries_prepare_prompt_before_dispatch(self):
        self.assertIn('DIRECTOR_PROMPT_BIN="${DIRECTOR_PROMPT_BIN:-$SCRIPT_DIR/director-prompt}"', self.text)
        self.assertIn('"$DIRECTOR_PROMPT_BIN" --mode "$mode"', self.text)
        self.assertIn('prepare_director_prompt CORRECTIVE', self.text)
        self.assertIn('prepare_director_prompt ARBITRATE', self.text)
        corrective_dispatch = 'dispatch_task_generator correction "$n" "$selected"'
        arbitration_dispatch = 'dispatch_task_generator arbitration "$n" "$selected"'
        self.assertEqual(self.text.count(corrective_dispatch), 1)
        self.assertEqual(self.text.count(arbitration_dispatch), 1)
        self.assertEqual(self.text.count("prepare_director_prompt CORRECTIVE"), 1)
        self.assertEqual(self.text.count("prepare_director_prompt ARBITRATE"), 1)
        for mode, dispatch_marker in (
            ("CORRECTIVE", corrective_dispatch),
            ("ARBITRATE", arbitration_dispatch),
        ):
            hook = self.text.index(f"prepare_director_prompt {mode}")
            dispatch = self.text.index(dispatch_marker, hook)
            self.assertLess(hook, dispatch)
        self.assertLess(
            self.text.index(corrective_dispatch),
            self.text.index('ledger corrective "$m"'),
        )
        self.assertLess(
            self.text.index(arbitration_dispatch),
            self.text.index('ledger arbitrate_resolved "$n"'),
        )

    def test_optional_hook_failure_is_explicit_under_set_e(self):
        self.assertIn("set -euo pipefail", self.text)
        self.assertIn("director prompt preparation failed", self.text)
        self.assertIn("baseline prompt", self.text)

    def test_director_and_ledger_boundaries_are_unchanged(self):
        self.assertIn("--agent two-model-task-generator", self.text)
        self.assertIn('ledger corrective "$m"', self.text)
        self.assertIn('ledger arbitrate_resolved "$n"', self.text)
        self.assertIn("reconcile_parents \"$n\"", self.text)
        self.assertNotIn("ledger jev", self.text.lower())
        self.assertIn('budget_cycle_assessed "$n"', self.text)
        self.assertIn('direct_correction_started "$n"', self.text)


if __name__ == "__main__":
    unittest.main()
