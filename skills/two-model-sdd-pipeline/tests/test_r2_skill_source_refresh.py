"""R2.2 acceptance tests for persistent skill-source refresh."""

import base64
import importlib.util
import json
import pathlib
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"
SEED = ROOT / "skills" / "two-model-sdd-pipeline" / "skills" / "sources.seed.json"


def load_skill_sources(testcase):
    path = SCRIPTS / "skill_sources.py"
    testcase.assertTrue(
        path.is_file(),
        "R2.2 requires skill_sources.py with discover and refresh APIs",
    )
    spec = importlib.util.spec_from_file_location("skill_sources_refresh", path)
    testcase.assertIsNotNone(spec)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    testcase.assertTrue(callable(getattr(module, "discover", None)))
    testcase.assertTrue(callable(getattr(module, "refresh", None)))
    return module


def repo_details(repository):
    return {
        "full_name": repository,
        "html_url": "https://github.com/" + repository,
        "description": "Reusable agent skills",
        "stargazers_count": 123,
        "topics": ["agent-skills", "python"],
        "default_branch": "main",
        "license": {"spdx_id": "MIT", "name": "MIT License"},
    }


class SkillSourceRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = pathlib.Path(tempfile.mkdtemp(prefix="skill-refresh-"))
        self.registry = self.temp / "registry.json"
        self.module = load_skill_sources(self)
        guard = mock.patch.object(
            self.module, "_github_get_json",
            side_effect=AssertionError("tests must not make live GitHub requests"),
        )
        guard.start()
        self.addCleanup(guard.stop)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp, ignore_errors=True)

    def test_seed_sources_are_candidates_not_implicitly_trusted(self):
        self.assertTrue(SEED.is_file(), "R2.2 requires the confirmed source seed")
        seed = json.loads(SEED.read_text(encoding="utf-8"))
        repositories = {item.get("repository"): item for item in seed["sources"]}

        self.assertIn("anthropics/skills", repositories)
        self.assertIn("VoltAgent/awesome-agent-skills", repositories)
        self.assertIn("vercel-labs/skills", repositories)
        self.assertTrue(all(item["review_status"] == "candidate"
                            for item in seed["sources"]))
        self.assertFalse(any(item["review_status"] in ("trusted", "approved")
                             for item in seed["sources"]))

    def test_refresh_persists_revision_metadata_and_the_supplied_clock(self):
        sources = [{
            "repository": "Acme/agent-skills",
            "source_url": "https://github.com/Acme/agent-skills",
            "category": "publisher",
            "review_status": "candidate",
        }]

        def github_get(url):
            parsed = urlsplit(url)
            if parsed.path == "/repos/Acme/agent-skills":
                return repo_details("Acme/agent-skills")
            if parsed.path == "/repos/Acme/agent-skills/commits/main":
                return {"sha": "commit-abc123"}
            if parsed.path == "/repos/Acme/agent-skills/git/trees/commit-abc123":
                return {"tree": [
                    {"path": "skills/review/SKILL.md", "type": "blob"},
                    {"path": "skills/testing/SKILL.md", "type": "blob"},
                ], "truncated": False}
            self.fail("unexpected GitHub request: " + url)

        with mock.patch.object(self.module, "_github_get_json", side_effect=github_get):
            result = self.module.refresh(
                str(self.registry), "2026-09-26T14:30:00Z", sources,
            )

        self.assertEqual(result["last_refreshed_at"], "2026-09-26T14:30:00Z")
        self.assertEqual(result["status"], "fresh")
        self.assertEqual(len(result["sources"]), 1)
        source = result["sources"][0]
        self.assertEqual(source["repository"], "Acme/agent-skills")
        self.assertEqual(source["category"], "publisher")
        self.assertEqual(source["revision"], "commit-abc123")
        self.assertEqual(source["last_checked_at"], "2026-09-26T14:30:00Z")
        self.assertEqual(source["review_status"], "candidate")
        self.assertEqual(source["license"]["spdx_id"], "MIT")
        self.assertEqual([item["path"] for item in source["skills"]], [
            "skills/review/SKILL.md", "skills/testing/SKILL.md",
        ])
        saved = json.loads(self.registry.read_text(encoding="utf-8"))
        self.assertEqual(saved, result)

    def test_refresh_preserves_skill_decisions_and_annotations_by_path(self):
        source = {
            "repository": "Acme/agent-skills",
            "source_url": "https://github.com/Acme/agent-skills",
            "category": "publisher",
            "revision": "old-revision",
            "last_checked_at": "2026-09-20T12:00:00Z",
            "review_status": "candidate",
            "description": "Reusable agent skills",
            "stars": 20,
            "topics": ["agent-skills"],
            "license": {"spdx_id": "MIT", "name": "MIT License"},
            "skills": [{
                "name": "Python helper",
                "path": "skills/python-helper/SKILL.md",
                "topics": ["python", "testing"],
                "compatibility": ["codex"],
                "license": {"spdx_id": "MIT", "name": "MIT License"},
                "review_status": "rejected",
                "annotations": {"reason": "requires unsupported runtime"},
            }],
        }
        self.registry.write_text(json.dumps({
            "schema_version": 1,
            "last_refreshed_at": "2026-09-20T12:00:00Z",
            "status": "fresh",
            "sources": [source],
            "queries": [],
        }), encoding="utf-8")

        def github_get(url):
            parsed = urlsplit(url)
            if parsed.path == "/repos/Acme/agent-skills":
                return repo_details("Acme/agent-skills")
            if parsed.path == "/repos/Acme/agent-skills/commits/main":
                return {"sha": "new-revision"}
            if parsed.path == "/repos/Acme/agent-skills/git/trees/new-revision":
                return {"tree": [
                    {"path": "skills/python-helper/SKILL.md", "type": "blob"},
                    {"path": "skills/new-helper/SKILL.md", "type": "blob"},
                ], "truncated": False}
            self.fail("unexpected GitHub request: " + url)

        with mock.patch.object(self.module, "_github_get_json", side_effect=github_get):
            result = self.module.refresh(
                str(self.registry), "2026-09-26T14:30:00Z", [source],
            )

        refreshed = result["sources"][0]
        skills = {item["path"]: item for item in refreshed["skills"]}
        self.assertEqual(skills["skills/python-helper/SKILL.md"]["review_status"],
                         "rejected")
        self.assertEqual(skills["skills/python-helper/SKILL.md"]["topics"],
                         ["python", "testing"])
        self.assertEqual(skills["skills/python-helper/SKILL.md"]["compatibility"],
                         ["codex"])
        self.assertEqual(skills["skills/python-helper/SKILL.md"]["annotations"],
                         {"reason": "requires unsupported runtime"})
        self.assertEqual(skills["skills/new-helper/SKILL.md"]["review_status"],
                         "unreviewed")

    def test_refresh_keeps_case_distinct_skill_paths_and_their_decisions_separate(self):
        source = {
            "repository": "Acme/agent-skills",
            "source_url": "https://github.com/Acme/agent-skills",
            "category": "publisher",
            "review_status": "candidate",
            "license": {"spdx_id": "MIT", "name": "MIT License"},
            "skills": [
                {"name": "Upper Go", "path": "skills/Go/SKILL.md",
                 "topics": ["upper"], "compatibility": ["codex"],
                 "license": {"spdx_id": "MIT", "name": "MIT License"},
                 "review_status": "reviewed", "annotations": {"origin": "upper"}},
                {"name": "Lower go", "path": "skills/go/SKILL.md",
                 "topics": ["lower"], "compatibility": ["opencode"],
                 "license": {"spdx_id": "MIT", "name": "MIT License"},
                 "review_status": "rejected", "annotations": {"origin": "lower"}},
            ],
        }
        self.registry.write_text(json.dumps({
            "schema_version": 1,
            "last_refreshed_at": "2026-09-20T12:00:00Z",
            "status": "fresh",
            "sources": [source],
            "queries": [],
        }), encoding="utf-8")

        def github_get(url):
            parsed = urlsplit(url)
            if parsed.path == "/repos/Acme/agent-skills":
                return repo_details("Acme/agent-skills")
            if parsed.path == "/repos/Acme/agent-skills/commits/main":
                return {"sha": "case-sensitive-revision"}
            if parsed.path == "/repos/Acme/agent-skills/git/trees/case-sensitive-revision":
                return {"tree": [
                    {"path": "skills/Go/SKILL.md", "type": "blob"},
                    {"path": "skills/go/SKILL.md", "type": "blob"},
                ], "truncated": False}
            self.fail("unexpected GitHub request: " + url)

        with mock.patch.object(self.module, "_github_get_json", side_effect=github_get):
            result = self.module.refresh(
                str(self.registry), "2026-09-26T14:30:00Z", [source],
            )

        skills = {item["path"]: item for item in result["sources"][0]["skills"]}
        self.assertEqual(skills["skills/Go/SKILL.md"]["review_status"], "reviewed")
        self.assertEqual(skills["skills/Go/SKILL.md"]["annotations"], {"origin": "upper"})
        self.assertEqual(skills["skills/Go/SKILL.md"]["topics"], ["upper"])
        self.assertEqual(skills["skills/go/SKILL.md"]["review_status"], "rejected")
        self.assertEqual(skills["skills/go/SKILL.md"]["annotations"], {"origin": "lower"})
        self.assertEqual(skills["skills/go/SKILL.md"]["topics"], ["lower"])

    def test_refresh_preserves_explicit_unknown_and_per_skill_license_overrides(self):
        source = {
            "repository": "Acme/agent-skills",
            "source_url": "https://github.com/Acme/agent-skills",
            "category": "publisher",
            "review_status": "candidate",
            "license": {"spdx_id": "MIT", "name": "MIT License"},
            "skills": [
                {"name": "Unknown license", "path": "skills/unknown/SKILL.md",
                 "topics": ["python"], "compatibility": ["codex"],
                 "license": None, "review_status": "reviewed"},
                {"name": "GPL helper", "path": "skills/gpl-helper/SKILL.md",
                 "topics": ["python"], "compatibility": ["codex"],
                 "license": {"spdx_id": "GPL-3.0-only", "name": "GNU GPL v3"},
                 "review_status": "reviewed"},
            ],
        }
        self.registry.write_text(json.dumps({
            "schema_version": 1,
            "last_refreshed_at": "2026-09-20T12:00:00Z",
            "status": "fresh",
            "sources": [source],
            "queries": [],
        }), encoding="utf-8")

        def github_get(url):
            parsed = urlsplit(url)
            if parsed.path == "/repos/Acme/agent-skills":
                return repo_details("Acme/agent-skills")
            if parsed.path == "/repos/Acme/agent-skills/commits/main":
                return {"sha": "license-revision"}
            if parsed.path == "/repos/Acme/agent-skills/git/trees/license-revision":
                return {"tree": [
                    {"path": "skills/unknown/SKILL.md", "type": "blob"},
                    {"path": "skills/gpl-helper/SKILL.md", "type": "blob"},
                ], "truncated": False}
            self.fail("unexpected GitHub request: " + url)

        with mock.patch.object(self.module, "_github_get_json", side_effect=github_get):
            result = self.module.refresh(
                str(self.registry), "2026-09-26T14:30:00Z", [source],
            )

        refreshed_source = result["sources"][0]
        skills = {item["path"]: item for item in refreshed_source["skills"]}
        self.assertIsNone(skills["skills/unknown/SKILL.md"]["license"])
        self.assertEqual(skills["skills/gpl-helper/SKILL.md"]["license"]["spdx_id"],
                         "GPL-3.0-only")
        checks = self.module._skill_checks(
            skills["skills/unknown/SKILL.md"], refreshed_source,
            {"topics": ["python"]}, ["python"],
        )
        self.assertFalse(checks["license"])

    def test_truncated_tree_preserves_inventory_and_marks_refresh_incomplete(self):
        source = {
            "repository": "Acme/agent-skills",
            "source_url": "https://github.com/Acme/agent-skills",
            "category": "publisher",
            "revision": "old-revision",
            "last_checked_at": "2026-09-20T12:00:00Z",
            "review_status": "candidate",
            "skills": [
                {"name": "Existing one", "path": "skills/existing-one/SKILL.md",
                 "topics": ["python"], "compatibility": ["codex"],
                 "review_status": "reviewed"},
                {"name": "Existing two", "path": "skills/existing-two/SKILL.md",
                 "topics": ["testing"], "compatibility": ["codex"],
                 "review_status": "unreviewed"},
            ],
        }
        previous_refresh = "2026-08-20T12:00:00Z"
        self.registry.write_text(json.dumps({
            "schema_version": 1,
            "last_refreshed_at": previous_refresh,
            "status": "fresh",
            "sources": [source],
            "queries": [],
        }), encoding="utf-8")

        def github_get(url):
            parsed = urlsplit(url)
            if parsed.path == "/repos/Acme/agent-skills":
                return repo_details("Acme/agent-skills")
            if parsed.path == "/repos/Acme/agent-skills/commits/main":
                return {"sha": "new-revision"}
            if parsed.path == "/repos/Acme/agent-skills/git/trees/new-revision":
                return {"tree": [
                    {"path": "skills/new-helper/SKILL.md", "type": "blob"},
                ], "truncated": True}
            self.fail("unexpected GitHub request: " + url)

        with mock.patch.object(self.module, "_github_get_json", side_effect=github_get):
            result = self.module.refresh(
                str(self.registry), "2026-09-26T14:30:00Z", [source],
            )

        refreshed = result["sources"][0]
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["last_refreshed_at"], previous_refresh)
        self.assertTrue(refreshed["skills_incomplete"])
        self.assertEqual({item["path"] for item in refreshed["skills"]}, {
            "skills/existing-one/SKILL.md",
            "skills/existing-two/SKILL.md",
            "skills/new-helper/SKILL.md",
        })

    def test_refresh_deduplicates_repositories_regardless_of_case(self):
        source = {
            "repository": "Acme/Agent-Skills",
            "source_url": "https://github.com/Acme/Agent-Skills",
            "category": "publisher",
            "review_status": "candidate",
        }
        calls = []

        def github_get(url):
            calls.append(url)
            parsed = urlsplit(url)
            if parsed.path.lower() == "/repos/acme/agent-skills":
                return repo_details("Acme/Agent-Skills")
            if parsed.path.lower() == "/repos/acme/agent-skills/commits/main":
                return {"sha": "same-revision"}
            if "/git/trees/" in parsed.path:
                return {"tree": [], "truncated": False}
            self.fail("unexpected GitHub request: " + url)

        with mock.patch.object(self.module, "_github_get_json", side_effect=github_get):
            result = self.module.refresh(
                str(self.registry), "2026-09-26T14:30:00Z",
                [source, dict(source, repository="acme/agent-skills")],
            )

        self.assertEqual(len(result["sources"]), 1)
        self.assertEqual(sum("/repos/" in url for url in calls), 3)

    def test_catalog_links_are_saved_as_unreviewed_targets_without_fetching_them(self):
        catalog = {
            "repository": "VoltAgent/awesome-agent-skills",
            "source_url": "https://github.com/VoltAgent/awesome-agent-skills",
            "category": "catalog",
            "review_status": "candidate",
        }
        readme = (
            "# Catalog\n"
            "[Python tests](https://github.com/Acme/test-skills/tree/main/skills/python-testing)\n"
            "[Same repo](https://github.com/acme/test-skills)\n"
        )
        encoded = base64.b64encode(readme.encode("utf-8")).decode("ascii")
        calls = []

        def github_get(url):
            calls.append(url)
            parsed = urlsplit(url)
            if parsed.path == "/repos/VoltAgent/awesome-agent-skills":
                return repo_details("VoltAgent/awesome-agent-skills")
            if parsed.path == "/repos/VoltAgent/awesome-agent-skills/commits/main":
                return {"sha": "catalog-revision"}
            if parsed.path == "/repos/VoltAgent/awesome-agent-skills/git/trees/catalog-revision":
                return {"tree": [], "truncated": False}
            if parsed.path == "/repos/VoltAgent/awesome-agent-skills/readme":
                return {"content": encoded, "encoding": "base64"}
            self.fail("unexpected GitHub request: " + url)

        with mock.patch.object(self.module, "_github_get_json", side_effect=github_get):
            result = self.module.refresh(
                str(self.registry), "2026-09-26T14:30:00Z", [catalog],
            )

        targets = [item for item in result["sources"]
                   if item["repository"].lower() == "acme/test-skills"]
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["review_status"], "unreviewed")
        self.assertEqual(targets[0]["discovered_from"], "VoltAgent/awesome-agent-skills")
        self.assertEqual(targets[0]["skills"][0]["path"], "skills/python-testing")
        self.assertIsNone(targets[0]["revision"])
        self.assertFalse(any("/repos/Acme/test-skills" in url for url in calls))

    def test_catalog_link_merge_preserves_existing_source_category_and_skill_decisions(self):
        catalog = {
            "repository": "VoltAgent/awesome-agent-skills",
            "source_url": "https://github.com/VoltAgent/awesome-agent-skills",
            "category": "catalog",
            "review_status": "candidate",
        }
        existing_target = {
            "repository": "Acme/test-skills",
            "source_url": "https://github.com/Acme/test-skills",
            "category": "publisher",
            "revision": "target-revision",
            "last_checked_at": "2026-09-20T12:00:00Z",
            "review_status": "reviewed",
            "description": "Reviewed source",
            "stars": 44,
            "topics": ["python"],
            "license": {"spdx_id": "MIT", "name": "MIT License"},
            "refresh_status": "fresh",
            "skills": [
                {"name": "Python tests", "path": "skills/python-testing/SKILL.md",
                 "topics": ["python"], "compatibility": ["codex"],
                 "license": {"spdx_id": "MIT", "name": "MIT License"},
                 "review_status": "reviewed", "annotations": {"decision": "keep"}},
                {"name": "Unsafe tool", "path": "skills/unsafe/SKILL.md",
                 "topics": ["python"], "compatibility": [],
                 "license": {"spdx_id": "MIT", "name": "MIT License"},
                 "review_status": "rejected", "annotations": {"decision": "reject"}},
            ],
        }
        self.registry.write_text(json.dumps({
            "schema_version": 1,
            "last_refreshed_at": "2026-09-20T12:00:00Z",
            "status": "fresh",
            "sources": [existing_target],
            "queries": [],
        }), encoding="utf-8")
        readme = (
            "# Catalog\n"
            "[Special](https://github.com/Acme/test-skills/tree/main/skills/special)\n"
        )
        encoded = base64.b64encode(readme.encode("utf-8")).decode("ascii")

        def github_get(url):
            parsed = urlsplit(url)
            if parsed.path == "/repos/VoltAgent/awesome-agent-skills":
                return repo_details("VoltAgent/awesome-agent-skills")
            if parsed.path == "/repos/VoltAgent/awesome-agent-skills/commits/main":
                return {"sha": "catalog-revision"}
            if parsed.path == "/repos/VoltAgent/awesome-agent-skills/git/trees/catalog-revision":
                return {"tree": [], "truncated": False}
            if parsed.path == "/repos/VoltAgent/awesome-agent-skills/readme":
                return {"content": encoded, "encoding": "base64"}
            self.fail("unexpected GitHub request: " + url)

        with mock.patch.object(self.module, "_github_get_json", side_effect=github_get):
            result = self.module.refresh(
                str(self.registry), "2026-09-26T14:30:00Z", [catalog],
            )

        target = next(item for item in result["sources"]
                      if item["repository"] == "Acme/test-skills")
        self.assertEqual(target["category"], "publisher")
        self.assertEqual(target["review_status"], "reviewed")
        self.assertEqual(target["revision"], "target-revision")
        self.assertEqual({item["path"] for item in target["skills"]}, {
            "skills/python-testing/SKILL.md", "skills/unsafe/SKILL.md", "skills/special",
        })
        skills = {item["path"]: item for item in target["skills"]}
        self.assertEqual(skills["skills/python-testing/SKILL.md"]["review_status"], "reviewed")
        self.assertEqual(skills["skills/python-testing/SKILL.md"]["annotations"],
                         {"decision": "keep"})
        self.assertEqual(skills["skills/unsafe/SKILL.md"]["review_status"], "rejected")
        self.assertEqual(skills["skills/unsafe/SKILL.md"]["annotations"],
                         {"decision": "reject"})
        self.assertEqual(skills["skills/special"]["review_status"], "unreviewed")

    def test_selective_refresh_does_not_mark_unselected_sources_fresh(self):
        source_a = {
            "repository": "Acme/first-skills",
            "source_url": "https://github.com/Acme/first-skills",
            "category": "publisher",
            "revision": "first-old",
            "last_checked_at": "2026-08-01T00:00:00Z",
            "review_status": "candidate",
            "refresh_status": "fresh",
            "skills": [],
        }
        source_b = {
            "repository": "Acme/second-skills",
            "source_url": "https://github.com/Acme/second-skills",
            "category": "publisher",
            "revision": "second-old",
            "last_checked_at": "2026-08-01T00:00:00Z",
            "review_status": "candidate",
            "refresh_status": "fresh",
            "skills": [],
        }
        previous_refresh = "2026-08-01T00:00:00Z"
        self.registry.write_text(json.dumps({
            "schema_version": 1,
            "last_refreshed_at": previous_refresh,
            "status": "fresh",
            "sources": [source_a, source_b],
            "queries": [],
        }), encoding="utf-8")

        def github_get(url):
            parsed = urlsplit(url)
            if parsed.path == "/repos/Acme/first-skills":
                return repo_details("Acme/first-skills")
            if parsed.path == "/repos/Acme/first-skills/commits/main":
                return {"sha": "first-new"}
            if parsed.path == "/repos/Acme/first-skills/git/trees/first-new":
                return {"tree": [], "truncated": False}
            self.fail("unselected source should not be requested: " + url)

        with mock.patch.object(self.module, "_github_get_json", side_effect=github_get):
            result = self.module.refresh(
                str(self.registry), "2026-09-26T14:30:00Z", [source_a],
            )

        sources = {item["repository"]: item for item in result["sources"]}
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["last_refreshed_at"], previous_refresh)
        self.assertEqual(sources["Acme/first-skills"]["last_checked_at"],
                         "2026-09-26T14:30:00Z")
        self.assertEqual(sources["Acme/second-skills"]["last_checked_at"],
                         "2026-08-01T00:00:00Z")

    def test_expired_discovery_keeps_last_usable_results_when_github_is_rate_limited(self):
        query = {"topics": ["python", "testing"]}
        last_search = {
            "query": query,
            "search_query": "python testing skill in:name,description,readme",
            "collected_at": "2026-08-01T00:00:00Z",
            "scope": "GitHub query-scoped top 100",
            "status": "fresh",
            "repositories": [{
                "repository": "Acme/old-python-skills",
                "url": "https://github.com/Acme/old-python-skills",
                "category": "github-search",
                "revision": None,
                "last_checked_at": "2026-08-01T00:00:00Z",
                "review_status": "unreviewed",
                "stars": 17,
                "topics": ["python", "testing"],
                "description": "Cached Python testing skills",
                "license": {"spdx_id": "MIT", "name": "MIT License"},
                "skills": [],
            }],
        }
        self.registry.write_text(json.dumps({
            "schema_version": 1,
            "last_refreshed_at": "2026-08-01T00:00:00Z",
            "status": "fresh",
            "sources": [],
            "queries": [last_search],
        }), encoding="utf-8")

        def rate_limited(url):
            from urllib.error import HTTPError

            raise HTTPError(url, 403, "rate limit", {"Retry-After": "60"}, None)

        with mock.patch.object(self.module, "_github_get_json", side_effect=rate_limited):
            result = self.module.discover(query, [], str(self.registry))

        self.assertEqual([item["repository"] for item in result["candidates"]],
                         ["Acme/old-python-skills"])
        self.assertIn(result["cache_status"], ("stale", "incomplete"))
        saved = json.loads(self.registry.read_text(encoding="utf-8"))
        self.assertEqual(saved["queries"][0]["collected_at"], "2026-08-01T00:00:00Z")
        self.assertEqual(saved["queries"][0]["repositories"][0]["repository"],
                         "Acme/old-python-skills")
        self.assertEqual(saved["queries"][0]["status"], "incomplete")

    def test_search_paginates_deduplicates_and_caps_each_query_at_100_results(self):
        query = {"topics": ["python"], "per_page": 50, "limit": 100}
        now = "2026-09-20T12:00:00Z"
        self.registry.write_text(json.dumps({
            "schema_version": 1,
            "last_refreshed_at": now,
            "status": "fresh",
            "sources": [],
            "queries": [],
        }), encoding="utf-8")
        urls = []

        def make_item(index):
            return {
                "full_name": "Acme/python-skill-%03d" % index,
                "html_url": "https://github.com/Acme/python-skill-%03d" % index,
                "description": "Python testing skills",
                "stargazers_count": 1000 - index,
                "topics": ["python", "testing"],
                "license": {"spdx_id": "MIT", "name": "MIT License"},
            }

        def github_page(url):
            urls.append(url)
            params = parse_qs(urlsplit(url).query)
            page = int(params["page"][0])
            self.assertEqual(params["per_page"], ["50"])
            if page == 1:
                return {"total_count": 150, "incomplete_results": False,
                        "items": [make_item(index) for index in range(50)]}
            if page == 2:
                return {"total_count": 150, "incomplete_results": False,
                        "items": [make_item(49)] +
                                 [make_item(index) for index in range(50, 100)]}
            self.fail("search exceeded the requested top 100 results")

        with mock.patch.object(self.module, "_github_get_json", side_effect=github_page):
            result = self.module.discover(query, [], str(self.registry))

        self.assertEqual(len(urls), 2)
        self.assertEqual(len(result["candidates"]), 100)
        self.assertEqual(len({item["repository"] for item in result["candidates"]}), 100)
        self.assertEqual(result["candidates"][0]["stars"], 1000)
        self.assertEqual(result["candidates"][-1]["stars"], 901)
