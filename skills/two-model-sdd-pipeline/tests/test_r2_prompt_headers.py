"""R2.3 contracts for deterministic, budgeted task prompt composition."""

import hashlib
import importlib.util
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_prompt_headers(testcase):
    path = SCRIPTS / "prompt_headers.py"
    testcase.assertTrue(path.is_file(), "R2.3 requires prompt_headers.py")
    spec = importlib.util.spec_from_file_location("prompt_headers_r2", path)
    testcase.assertIsNotNone(spec)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    testcase.assertTrue(callable(getattr(module, "build", None)))
    return module


def sha256(text):
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def context(**overrides):
    value = {
        "role_protocol": "ROLE-PROTOCOL-7",
        "authority": "AUTHORITY-ORDER-3",
        "task_acceptance": "TASK-ACCEPTANCE-11",
        "output_contract": "OUTPUT-CONTRACT-5",
        "budget_chars": 20000,
    }
    value.update(overrides)
    return value


def skill_bundle(content="DOMAIN-SKILL-CONTENT", revision="sha256:domain-r1"):
    return {"skills": [{
        "id": "domain-test-skill",
        "revision": revision,
        "source_sha256": revision,
        "sections": [{"heading": "Workflow", "content": content}],
        "content": content,
    }]}


class PromptHeaderTests(unittest.TestCase):
    def setUp(self):
        self.module = load_prompt_headers(self)

    def test_prompt_keeps_required_sections_in_contract_order(self):
        result = self.module.build(
            "operator", context(), skill_bundle(), "BACKEND-POLICY-9",
        )
        text = result["text"]
        markers = [
            "ROLE-PROTOCOL-7",
            "AUTHORITY-ORDER-3",
            "BACKEND-POLICY-9",
            "DOMAIN-SKILL-CONTENT",
            "TASK-ACCEPTANCE-11",
            "OUTPUT-CONTRACT-5",
        ]
        positions = [text.index(marker) for marker in markers]

        self.assertEqual(positions, sorted(positions))
        self.assertIn("Write the test first", text)
        self.assertIn("self-review", text.casefold())
        self.assertEqual(result["hash"], sha256(text))

    def test_operator_prompt_carries_investigation_contract(self):
        result = self.module.build(
            "operator", context(), skill_bundle(), "BACKEND-POLICY-9",
        )
        folded = result["text"].casefold()
        for marker in ("investigat", "root cause", "reproduc",
                       "working path", "evidence-backed"):
            self.assertIn(marker, folded)

    def test_prompt_hash_changes_when_dispatch_inputs_change(self):
        first = self.module.build(
            "operator", context(), skill_bundle(), "CODEX-POLICY",
        )
        repeat = self.module.build(
            "operator", context(), skill_bundle(), "CODEX-POLICY",
        )
        changed_policy = self.module.build(
            "operator", context(), skill_bundle(), "OPENCODE-POLICY",
        )
        changed_task = self.module.build(
            "operator", context(task_acceptance="TASK-ACCEPTANCE-12"),
            skill_bundle(), "CODEX-POLICY",
        )
        changed_skill = self.module.build(
            "operator", context(), skill_bundle("CHANGED-DOMAIN-SKILL"),
            "CODEX-POLICY",
        )

        self.assertEqual(first, repeat)
        self.assertNotEqual(first["hash"], changed_policy["hash"])
        self.assertNotEqual(first["hash"], changed_task["hash"])
        self.assertNotEqual(first["hash"], changed_skill["hash"])
        self.assertEqual(first["hash"], sha256(first["text"]))
        self.assertEqual(first["provenance"]["skills"][0]["id"], "domain-test-skill")
        self.assertEqual(first["provenance"]["skills"][0]["revision"], "sha256:domain-r1")

    def test_prompt_hash_changes_when_skill_revision_changes_without_content_change(self):
        first = self.module.build(
            "operator", context(), skill_bundle("UNCHANGED-DOMAIN-SKILL", "sha256:domain-r1"),
            "CODEX-POLICY",
        )
        changed_revision = self.module.build(
            "operator", context(), skill_bundle("UNCHANGED-DOMAIN-SKILL", "sha256:domain-r2"),
            "CODEX-POLICY",
        )

        self.assertIn("UNCHANGED-DOMAIN-SKILL", first["text"])
        self.assertIn("UNCHANGED-DOMAIN-SKILL", changed_revision["text"])
        self.assertIn("sha256:domain-r2", changed_revision["text"])
        self.assertNotEqual(first["hash"], changed_revision["hash"])

    def test_empty_skill_content_still_renders_identity_for_revision_hashing(self):
        first = self.module.build(
            "operator", context(), skill_bundle("", "sha256:domain-r1"),
            "CODEX-POLICY",
        )
        changed_revision = self.module.build(
            "operator", context(), skill_bundle("", "sha256:domain-r2"),
            "CODEX-POLICY",
        )

        self.assertIn("domain-test-skill", first["text"])
        self.assertIn("sha256:domain-r1", first["text"])
        self.assertIn("sha256:domain-r2", changed_revision["text"])
        self.assertNotEqual(first["hash"], changed_revision["hash"])

    def test_required_prompt_context_is_rejected_when_over_budget(self):
        with self.assertRaisesRegex(self.module.PromptHeaderError, "budget"):
            self.module.build(
                "operator", context(budget_chars=8), skill_bundle(), "BACKEND-POLICY",
            )

    def test_conflicting_revisions_for_one_skill_are_surfaced(self):
        skills = skill_bundle()
        skills["skills"].append({
            "id": "domain-test-skill",
            "revision": "sha256:domain-r2",
            "source_sha256": "sha256:domain-r2",
            "sections": [{"heading": "Workflow", "content": "CONFLICTING-CONTENT"}],
            "content": "CONFLICTING-CONTENT",
        })

        with self.assertRaisesRegex(self.module.PromptHeaderError, "conflict"):
            self.module.build("operator", context(), skills, "BACKEND-POLICY")

    def test_shared_role_content_has_the_same_identity_across_backend_policies(self):
        codex = self.module.build(
            "reviewer", context(), skill_bundle(), "CODEX-READ-ONLY-POLICY",
        )
        opencode = self.module.build(
            "reviewer", context(), skill_bundle(), "OPENCODE-READ-ONLY-POLICY",
        )

        self.assertIn("CODEX-READ-ONLY-POLICY", codex["text"])
        self.assertIn("OPENCODE-READ-ONLY-POLICY", opencode["text"])
        self.assertEqual(codex["provenance"]["core_sha256"],
                         opencode["provenance"]["core_sha256"])
        self.assertIn("independent", codex["text"].casefold())

    def test_unknown_roles_and_missing_mandatory_context_fail_before_dispatch(self):
        with self.assertRaises(self.module.PromptHeaderError):
            self.module.build("coder", context(), skill_bundle(), "POLICY")

        incomplete = context()
        del incomplete["task_acceptance"]
        with self.assertRaises(self.module.PromptHeaderError):
            self.module.build("operator", incomplete, skill_bundle(), "POLICY")


if __name__ == "__main__":
    unittest.main()
