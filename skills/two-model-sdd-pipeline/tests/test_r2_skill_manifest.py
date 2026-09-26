"""R2.3 contracts for immutable task skill resolution."""

import hashlib
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_skill_manifest(testcase):
    path = SCRIPTS / "skill_manifest.py"
    testcase.assertTrue(path.is_file(), "R2.3 requires skill_manifest.py")
    spec = importlib.util.spec_from_file_location("skill_manifest_r2", path)
    testcase.assertIsNotNone(spec)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    testcase.assertTrue(callable(getattr(module, "resolve", None)))
    return module


def sha256(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def empty_registry():
    return {
        "schema_version": 1,
        "last_refreshed_at": "2026-09-26T12:00:00Z",
        "status": "fresh",
        "sources": [],
        "queries": [],
    }


def cached_query(query, repositories):
    search_query = " ".join(list(query.get("topics", [])) + [
        "skill", "in:name,description,readme",
    ])
    return {
        "query": query,
        "search_query": search_query,
        "collected_at": "2026-09-26T12:00:00Z",
        "scope": "Query-scoped GitHub skill discovery; up to 100 matching repositories, not exhaustive.",
        "status": "fresh",
        "repositories": repositories,
    }


def cached_repository(repository, topics):
    return {
        "repository": repository,
        "url": "https://github.com/" + repository,
        "category": "github-search",
        "revision": "source-revision-1",
        "last_checked_at": "2026-09-26T12:00:00Z",
        "review_status": "unreviewed",
        "stars": 42,
        "topics": topics,
        "description": "Reusable agent testing skill",
        "license": {"spdx_id": "MIT", "name": "MIT License"},
        "skills": [],
    }


class SkillManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = pathlib.Path(tempfile.mkdtemp(prefix="skill-manifest-r2-"))
        self.bundle = self.temp / "bundle"
        self._module = None

    @property
    def module(self):
        if self._module is None:
            self._module = load_skill_manifest(self)
        return self._module

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp, ignore_errors=True)

    def write_skill(self, skill_id, content):
        path = self.bundle / "skills" / skill_id / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path.read_bytes()

    def test_resolve_extracts_selected_sections_and_binds_the_installed_revision(self):
        raw = self.write_skill("test-driven-development", """# Test-driven development

## The Iron Law
Write the test first and watch the expected failure.

## Red-Green-Refactor
Implement the smallest change that passes the failing test.

## Common Rationalizations
Do not skip the failing-test proof.
""")
        selection = {
            "role": "operator",
            "skills": [{
                "id": "test-driven-development",
                "revision": sha256(raw),
                "required": True,
                "roles": ["operator"],
                "sections": ["The Iron Law", "Red-Green-Refactor"],
                "topics": ["testing"],
            }],
        }

        result = self.module.resolve(selection, str(self.bundle))

        self.assertEqual(len(result["skills"]), 1)
        resolved = result["skills"][0]
        self.assertEqual(resolved["id"], "test-driven-development")
        self.assertEqual(resolved["revision"], sha256(raw))
        self.assertEqual(resolved["source_sha256"], sha256(raw))
        self.assertEqual([part["heading"] for part in resolved["sections"]], [
            "The Iron Law", "Red-Green-Refactor",
        ])
        self.assertIn("watch the expected failure", resolved["content"])
        self.assertNotIn("Common Rationalizations", resolved["content"])

    def test_changed_installed_content_is_rejected_as_a_stale_revision(self):
        self.write_skill("review-skill", "# Review\n\n## Evidence\nUse file and line evidence.\n")
        selection = {
            "role": "reviewer",
            "skills": [{
                "id": "review-skill",
                "revision": "sha256:" + "0" * 64,
                "required": True,
                "roles": ["reviewer"],
                "sections": ["Evidence"],
            }],
        }

        with self.assertRaisesRegex(self.module.SkillManifestError, "revision"):
            self.module.resolve(selection, str(self.bundle))

    def test_missing_required_installed_skill_blocks_resolution(self):
        selection = {
            "role": "operator",
            "skills": [{
                "id": "required-review-skill",
                "revision": "sha256:" + "a" * 64,
                "required": True,
                "roles": ["operator"],
                "sections": ["Evidence"],
            }],
        }

        with self.assertRaisesRegex(
                self.module.SkillManifestError, "required-review-skill"):
            self.module.resolve(selection, str(self.bundle))

    def test_missing_optional_installed_skill_is_recorded_without_blocking(self):
        selection = {
            "role": "operator",
            "skills": [{
                "id": "optional-lint-skill",
                "revision": "sha256:" + "b" * 64,
                "required": False,
                "roles": ["operator"],
                "sections": ["Linting"],
            }],
        }

        result = self.module.resolve(selection, str(self.bundle))

        self.assertEqual(result["skills"], [])
        self.assertEqual(result["omissions"], [{
            "id": "optional-lint-skill",
            "reason": "optional_skill_not_installed",
        }])

    def test_role_specific_selection_does_not_leak_into_another_role(self):
        raw = self.write_skill("review-skill", "# Review\n\n## Evidence\nCite the finding.\n")
        selection = {
            "role": "operator",
            "skills": [{
                "id": "review-skill",
                "revision": sha256(raw),
                "required": True,
                "roles": ["reviewer"],
                "sections": ["Evidence"],
            }],
        }

        result = self.module.resolve(selection, str(self.bundle))

        self.assertEqual(result["skills"], [])
        self.assertEqual(result["omissions"], [{
            "id": "review-skill",
            "reason": "not_applicable_to_role",
        }])

    def test_installed_coverage_short_circuits_external_discovery(self):
        raw = self.write_skill("testing-skill", "# Testing\n\n## Workflow\nRun focused tests.\n")
        selection = {
            "role": "operator",
            "skills": [{
                "id": "testing-skill",
                "revision": sha256(raw),
                "required": True,
                "roles": ["operator"],
                "sections": ["Workflow"],
                "topics": ["testing"],
            }],
            "discovery": {
                "query": {"topics": ["testing"]},
                "registry": str(self.temp / "registry.json"),
            },
        }

        result = self.module.resolve(selection, str(self.bundle))

        self.assertEqual(result["discovery"]["cache_status"], "installed")
        self.assertEqual(result["discovery"]["candidates"], [])
        self.assertFalse(result["discovery"]["installation_performed"])

    def test_cached_external_gap_is_only_a_suggestion_and_never_installs(self):
        query = {"topics": ["testing"]}
        registry = empty_registry()
        registry["queries"] = [cached_query(query, [
            cached_repository("Acme/testing-skills", ["testing"]),
        ])]
        registry_path = self.temp / "registry.json"
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        selection = {
            "role": "operator",
            "skills": [{
                "id": "external-testing-skill",
                "revision": "source-revision-1",
                "required": False,
                "roles": ["operator"],
                "sections": ["Workflow"],
                "topics": ["testing"],
            }],
            "discovery": {"query": query, "registry": str(registry_path)},
        }

        result = self.module.resolve(selection, str(self.bundle))

        self.assertEqual(result["skills"], [])
        self.assertEqual(result["omissions"], [{
            "id": "external-testing-skill",
            "reason": "optional_skill_not_installed",
        }])
        self.assertEqual(
            [item["repository"] for item in result["discovery"]["candidates"]],
            ["Acme/testing-skills"],
        )
        self.assertTrue(result["discovery"]["external_installation_requires_approval"])
        self.assertFalse(result["discovery"]["installation_performed"])

    def test_manifest_records_the_verified_upstream_pin_and_license(self):
        lock_path = ROOT / "skills" / "two-model-sdd-pipeline" / "prompts" / "upstream-lock.json"
        self.assertTrue(lock_path.is_file(), "R2.3 requires a verified upstream lock")
        lock = json.loads(lock_path.read_text(encoding="utf-8"))

        self.assertEqual(lock["repository"], "https://github.com/obra/superpowers")
        self.assertEqual(lock["revision"], "b36e0829c6d0140e93cfef2ca599b1b07d4a7797")
        self.assertEqual(lock["tag"], "v6.3.0")
        self.assertEqual(lock["license"]["spdx_id"], "MIT")
        self.assertEqual(lock["license"]["path"], "LICENSE")
        self.assertEqual(
            lock["license"]["source_url"],
            "https://github.com/obra/superpowers/blob/b36e0829c6d0140e93cfef2ca599b1b07d4a7797/LICENSE",
        )
        self.assertEqual(
            lock["license"]["sha256"],
            "sha256:0da33ed814ee87e72db078f489c4447af72f13d9f25d9e17476f32efd77705fc",
        )
        hashes = {item["path"]: item["sha256"] for item in lock["sources"]}
        self.assertEqual(hashes["skills/test-driven-development/SKILL.md"],
                         "sha256:bf1b8216e523851a411e91d429a7c1c2a173e79d88957bc78e348218d50edd54")
        self.assertEqual(hashes["skills/test-driven-development/writing-good-tests.md"],
                         "sha256:51471c853306ff92ca8bb41dcaea05f31c0e46b03651f8f3c99754b7172f4ae1")
        self.assertEqual(hashes["skills/subagent-driven-development/SKILL.md"],
                         "sha256:8dd1b8e698edec3706c0d89517dbe96febd3bacd3f6ea21c1a3569c62ea104b5")
        self.assertIn("skills/subagent-driven-development/task-reviewer-prompt.md", hashes)

    def test_adaptation_map_records_retained_and_replaced_source_sections(self):
        map_path = ROOT / "skills" / "two-model-sdd-pipeline" / "prompts" / "adaptation-map.json"
        self.assertTrue(map_path.is_file(), "R2.3 requires an upstream adaptation map")
        value = json.loads(map_path.read_text(encoding="utf-8"))
        self.assertEqual(value["upstream_revision"], "b36e0829c6d0140e93cfef2ca599b1b07d4a7797")
        entries = value["sections"]
        self.assertTrue(entries)
        self.assertTrue(all(item.get("source_path") and item.get("section")
                            and item.get("decision") and item.get("reason")
                            for item in entries))
        decisions = {item["decision"] for item in entries}
        self.assertIn("retained", decisions)
        self.assertIn("replaced", decisions)
        self.assertTrue(any(item["source_path"] == "skills/test-driven-development/SKILL.md"
                            for item in entries))
        self.assertTrue(any(item["source_path"] == "skills/subagent-driven-development/implementer-prompt.md"
                            for item in entries))


if __name__ == "__main__":
    unittest.main()
