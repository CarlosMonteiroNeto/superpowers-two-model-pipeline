"""R4.5 dispatch audit, backend fixtures and documentation acceptance."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"
AUDIT = SCRIPTS / "dispatch-audit"


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, text=True,
                          capture_output=True, check=True).stdout.strip()


class DispatchAuditAcceptanceTests(unittest.TestCase):
    def _repo(self, source):
        temporary = tempfile.TemporaryDirectory()
        root = pathlib.Path(temporary.name)
        git(root, "init", "-q")
        git(root, "config", "user.email", "audit@example.invalid")
        git(root, "config", "user.name", "Audit Fixture")
        (root / "worker.py").write_text("# baseline\n", encoding="utf-8")
        git(root, "add", "worker.py")
        git(root, "commit", "-qm", "base")
        base = git(root, "rev-parse", "HEAD")
        (root / "worker.py").write_text(source, encoding="utf-8")
        git(root, "add", "worker.py")
        git(root, "commit", "-qm", "candidate")
        head = git(root, "rev-parse", "HEAD")
        return temporary, root, base, head

    def _run_audit(self, root, base, head, declared):
        inventory = root / "inventory.json"
        policy = root / "policy.json"
        output = root / "audit.json"
        inventory.write_text(json.dumps({"version": 1, "repo": str(root),
                                         "base": base, "head": head,
                                         "call_sites": declared}), encoding="utf-8")
        policy.write_text(json.dumps({"version": 1, "semantic_justification_required": True}),
                          encoding="utf-8")
        result = subprocess.run([sys.executable, str(AUDIT), "--inventory", str(inventory),
                                 "--policy", str(policy), "--output", str(output)],
                                text=True, capture_output=True)
        return result, json.loads(output.read_text(encoding="utf-8")) if output.exists() else None

    def test_accepts_semantically_justified_codex_and_opencode_calls(self):
        for backend in ("codex", "opencode"):
            with self.subTest(backend=backend):
                temporary, root, base, head = self._repo(
                    "dispatch(role='reviewer', backend='" + backend + "')\n")
                try:
                    declared = [{"file": "worker.py", "line": 1,
                                 "role": "reviewer", "trigger": "independent review",
                                 "frequency": "once per candidate", "budget": 1,
                                 "termination": "review complete", "decision": "keep",
                                 "justification": "semantic review finds contract defects"}]
                    result, report = self._run_audit(root, base, head, declared)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(report["status"], "passed")
                finally:
                    temporary.cleanup()

    def test_rejects_new_model_choice_router_even_when_inventory_claims_semantic(self):
        temporary, root, base, head = self._repo(
            "if severity == 'Important':\n    model = 'gpt-6-sol'\n")
        try:
            declared = [{"file": "worker.py", "line": 1, "role": "director",
                         "trigger": "review", "frequency": "per finding", "budget": 1,
                         "termination": "review complete", "decision": "keep",
                         "justification": "pick model by severity"}]
            result, report = self._run_audit(root, base, head, declared)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(report["status"], "rejected")
            self.assertIn("mechanical_model_routing", [x["code"] for x in report["findings"]])
        finally:
            temporary.cleanup()

    def test_rejects_unbounded_call_loop_and_missing_callsite_inventory(self):
        temporary, root, base, head = self._repo("while True:\n    dispatch()\n")
        try:
            result, report = self._run_audit(root, base, head, [])
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(report["status"], "rejected")
            codes = [x["code"] for x in report["findings"]]
            self.assertIn("unbounded_dispatch_loop", codes)
            self.assertIn("uninventoried_semantic_call", codes)
        finally:
            temporary.cleanup()

    def test_rejects_single_line_unbounded_dispatch_loop(self):
        temporary, root, base, head = self._repo("while True: dispatch()\n")
        try:
            declared = [{"file": "worker.py", "line": 1, "role": "operator",
                         "trigger": "task start", "frequency": "each iteration",
                         "budget": 3, "termination": "bounded by cycle limit",
                         "decision": "keep", "justification": "semantic work"}]
            result, report = self._run_audit(root, base, head, declared)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unbounded_dispatch_loop", [x["code"] for x in report["findings"]])
        finally:
            temporary.cleanup()

    def test_dynamic_call_is_inventoryable_and_explicitly_bounded_loop_passes(self):
        temporary, root, base, head = self._repo(
            "attempt = 0\nmethod = 'dispatch'\nwhile attempt < 3:\n    getattr(worker, method)()\n    attempt += 1\n")
        try:
            declared = [{"file": "worker.py", "line": 4, "role": "reviewer",
                         "trigger": "candidate needs review", "frequency": "up to three",
                         "budget": 3, "termination": "attempt reaches three",
                         "decision": "keep", "justification": "semantic contract review"}]
            result, report = self._run_audit(root, base, head, declared)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["observed_call_sites"], 1)
        finally:
            temporary.cleanup()

    def test_rejects_model_lookup_keyed_by_role_without_an_if_statement(self):
        temporary, root, base, head = self._repo(
            "selected = MODEL_BY_ROLE[role]\ndispatch(model=selected)\n")
        try:
            declared = [{"file": "worker.py", "line": 2, "role": "operator",
                         "trigger": "task start", "frequency": "once", "budget": 1,
                         "termination": "worker result", "decision": "keep",
                         "justification": "role selects a model"}]
            result, report = self._run_audit(root, base, head, declared)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("mechanical_model_routing", [x["code"] for x in report["findings"]])
        finally:
            temporary.cleanup()

    def test_prose_about_scripts_is_not_scanned_as_a_call_site(self):
        temporary, root, base, head = self._repo("# Example: dispatch(role='reviewer')\n")
        try:
            result, report = self._run_audit(root, base, head, [])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(report["observed_call_sites"], 0)
        finally:
            temporary.cleanup()

    def test_test_fixtures_are_not_treated_as_production_dispatch_sites(self):
        temporary, root, base, _ = self._repo("value = 1\n")
        try:
            test_file = root / "tests" / "test_worker.py"
            test_file.parent.mkdir()
            test_file.write_text("dispatch()\n", encoding="utf-8")
            git(root, "add", "tests/test_worker.py")
            git(root, "commit", "-qm", "add fixture")
            head = git(root, "rev-parse", "HEAD")
            result, report = self._run_audit(root, base, head, [])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(report["observed_call_sites"], 0)
        finally:
            temporary.cleanup()

    def test_pattern_definitions_do_not_look_like_model_routing(self):
        source = AUDIT.read_text(encoding="utf-8")
        temporary, root, base, head = self._repo(source)
        try:
            result, report = self._run_audit(root, base, head, [])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(report["findings"], [])
        finally:
            temporary.cleanup()

    def test_rejects_call_loop_over_unbounded_iterator(self):
        temporary, root, base, head = self._repo(
            "for item in itertools.count():\n    dispatch(item)\n")
        try:
            declared = [{"file": "worker.py", "line": 2, "role": "operator",
                         "trigger": "each item", "frequency": "each item",
                         "budget": 3, "termination": "all items consumed", "decision": "keep",
                         "justification": "dispatch items"}]
            result, report = self._run_audit(root, base, head, declared)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unbounded_dispatch_loop", [x["code"] for x in report["findings"]])
        finally:
            temporary.cleanup()

    def test_rejects_while_comparison_without_progress(self):
        temporary, root, base, head = self._repo(
            "attempt = 0\nwhile attempt < 3:\n    dispatch()\n")
        try:
            declared = [{"file": "worker.py", "line": 3, "role": "operator",
                         "trigger": "task start", "frequency": "up to three",
                         "budget": 3, "termination": "attempt reaches three",
                         "decision": "keep", "justification": "semantic work"}]
            result, report = self._run_audit(root, base, head, declared)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unbounded_dispatch_loop", [x["code"] for x in report["findings"]])
        finally:
            temporary.cleanup()

    def test_rejects_counter_mutation_inside_branch_despite_later_increment(self):
        temporary, root, base, head = self._repo(
            "attempt = 0\nwhile attempt < 3:\n    if should_retry:\n        attempt -= 1\n    dispatch()\n    attempt += 1\n")
        try:
            declared = [{"file": "worker.py", "line": 5, "role": "operator",
                         "trigger": "task start", "frequency": "up to three",
                         "budget": 3, "termination": "attempt reaches three",
                         "decision": "keep", "justification": "semantic work"}]
            result, report = self._run_audit(root, base, head, declared)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unbounded_dispatch_loop", [x["code"] for x in report["findings"]])
        finally:
            temporary.cleanup()

    def test_rejects_while_counters_initialized_to_infinity(self):
        examples = (
            "attempt = float('inf')\nwhile attempt > 3:\n    dispatch()\n    attempt -= 1\n",
            "attempt = float('-inf')\nwhile attempt < 3:\n    dispatch()\n    attempt += 1\n",
        )
        for source in examples:
            with self.subTest(source=source):
                temporary, root, base, head = self._repo(source)
                try:
                    declared = [{"file": "worker.py", "line": 3, "role": "operator",
                                 "trigger": "task start", "frequency": "bounded attempts",
                                 "budget": 3, "termination": "counter reaches bound",
                                 "decision": "keep", "justification": "semantic work"}]
                    result, report = self._run_audit(root, base, head, declared)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("unbounded_dispatch_loop",
                                  [x["code"] for x in report["findings"]])
                finally:
                    temporary.cleanup()

    def test_nested_break_does_not_bound_outer_dispatch_loop(self):
        temporary, root, base, head = self._repo(
            "while True:\n    for item in items:\n        break\n    dispatch(item)\n")
        try:
            declared = [{"file": "worker.py", "line": 4, "role": "operator",
                         "trigger": "task start", "frequency": "once per task",
                         "budget": 1, "termination": "outer loop completes",
                         "decision": "keep", "justification": "semantic work"}]
            result, report = self._run_audit(root, base, head, declared)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unbounded_dispatch_loop", [x["code"] for x in report["findings"]])
        finally:
            temporary.cleanup()

    def test_rejects_unknown_inventory_frequency_budget_and_termination(self):
        temporary, root, base, head = self._repo("dispatch()\n")
        try:
            base_site = {"file": "worker.py", "line": 1, "role": "operator",
                         "trigger": "task start", "frequency": "once",
                         "budget": 1, "termination": "worker returns",
                         "decision": "keep", "justification": "semantic work"}
            for field, value in (("frequency", "unknown"), ("budget", "unbounded"),
                                 ("termination", "none")):
                with self.subTest(field=field):
                    declared = [{**base_site, field: value}]
                    result, report = self._run_audit(root, base, head, declared)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(report["findings"][0]["code"], "invalid_input")
        finally:
            temporary.cleanup()

    def test_rejects_call_added_inside_preexisting_unbounded_loop(self):
        temporary = tempfile.TemporaryDirectory()
        root = pathlib.Path(temporary.name)
        git(root, "init", "-q")
        git(root, "config", "user.email", "audit@example.invalid")
        git(root, "config", "user.name", "Audit Fixture")
        (root / "worker.py").write_text("while True:\n    pass\n", encoding="utf-8")
        git(root, "add", "worker.py")
        git(root, "commit", "-qm", "base")
        base = git(root, "rev-parse", "HEAD")
        (root / "worker.py").write_text("while True:\n    dispatch()\n", encoding="utf-8")
        git(root, "add", "worker.py")
        git(root, "commit", "-qm", "candidate")
        head = git(root, "rev-parse", "HEAD")
        try:
            declared = [{"file": "worker.py", "line": 2, "role": "operator",
                         "trigger": "loop iteration", "frequency": "each iteration", "budget": 3,
                         "termination": "bounded by configured cycle", "decision": "keep",
                         "justification": "dispatch each item"}]
            result, report = self._run_audit(root, base, head, declared)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unbounded_dispatch_loop", [x["code"] for x in report["findings"]])
        finally:
            temporary.cleanup()

    def test_rejects_path_traversal_in_callsite_inventory(self):
        temporary, root, base, head = self._repo("dispatch()\n")
        try:
            declared = [{"file": "../worker.py", "line": 1, "role": "operator",
                         "trigger": "task start", "frequency": "once", "budget": 1,
                         "termination": "worker return", "decision": "keep",
                         "justification": "semantic task execution"}]
            result, report = self._run_audit(root, base, head, declared)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(report["findings"][0]["code"], "invalid_input")
        finally:
            temporary.cleanup()

    def test_skill_guidance_and_policy_supersession_are_explicit(self):
        scripter = (ROOT / "skills/skill-scripter/SKILL.md").read_text(encoding="utf-8")
        writer = (ROOT / "skills/write-script/SKILL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        adr = ROOT / "docs/superpowers/adr/2026-09-25-affected-verification-and-bounded-dispatch.md"
        self.assertTrue(adr.is_file())
        self.assertIn("termination", scripter.lower())
        self.assertIn("delegat", scripter.lower())
        for value in ("role", "trigger", "frequency", "budget", "keep", "remove", "merge"):
            self.assertIn(value, scripter.lower())
        self.assertIn("dispatch-audit", writer)
        self.assertIn("ADR-0012", adr.read_text(encoding="utf-8"))
        self.assertIn("unbounded retry", adr.read_text(encoding="utf-8").lower())
        self.assertIn("cost", readme.lower())


if __name__ == "__main__":
    unittest.main()
