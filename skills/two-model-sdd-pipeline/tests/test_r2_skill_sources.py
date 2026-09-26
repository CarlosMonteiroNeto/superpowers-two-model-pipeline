"""R2.2 acceptance tests for installed-first skill-source discovery."""

import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"


def load_skill_sources(testcase):
    path = SCRIPTS / "skill_sources.py"
    testcase.assertTrue(
        path.is_file(),
        "R2.2 requires skill_sources.py with discover and refresh APIs",
    )
    spec = importlib.util.spec_from_file_location("skill_sources", path)
    testcase.assertIsNotNone(spec)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    testcase.assertTrue(callable(getattr(module, "discover", None)))
    testcase.assertTrue(callable(getattr(module, "refresh", None)))
    return module


def empty_registry(last_refreshed_at="2026-09-20T12:00:00Z"):
    return {
        "schema_version": 1,
        "last_refreshed_at": last_refreshed_at,
        "status": "fresh",
        "sources": [],
        "queries": [],
    }


def cached_query(query, repositories, collected_at="2026-09-20T12:00:00Z"):
    return {
        "query": query,
        "search_query": "python testing skill in:name,description,readme",
        "collected_at": collected_at,
        "scope": "GitHub repository search for this query; up to 100 matching results sorted by stars, not exhaustive.",
        "status": "fresh",
        "repositories": repositories,
    }


def repo(full_name, stars, topics, description="Python testing skills"):
    return {
        "repository": full_name,
        "url": "https://github.com/" + full_name,
        "category": "github-search",
        "revision": None,
        "last_checked_at": "2026-09-20T12:00:00Z",
        "review_status": "unreviewed",
        "stars": stars,
        "topics": topics,
        "description": description,
        "license": {"spdx_id": "MIT", "name": "MIT License"},
        "skills": [],
    }


class SkillSourceDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = pathlib.Path(tempfile.mkdtemp(prefix="skill-sources-"))
        self.registry = self.temp / "registry.json"
        self.module = load_skill_sources(self)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp, ignore_errors=True)

    def write_registry(self, value):
        self.registry.write_text(json.dumps(value), encoding="utf-8")

    def test_installed_skills_cover_query_without_external_search(self):
        query = {"topics": ["flutter", "testing"]}
        installed = [{
            "id": "flutter-test-workflow",
            "name": "Flutter test workflow",
            "topics": ["flutter", "testing"],
            "revision": "r1-sha",
            "path": "skills/flutter-test-workflow/SKILL.md",
        }]
        with mock.patch.object(
            self.module, "_github_get_json",
            side_effect=AssertionError("installed coverage must be checked first"),
        ):
            result = self.module.discover(query, installed, str(self.registry))

        self.assertEqual([item["id"] for item in result["installed_matches"]],
                         ["flutter-test-workflow"])
        self.assertEqual(result["missing_topics"], [])
        self.assertEqual(result["candidates"], [])
        self.assertFalse(result["installation_performed"])

    def test_fresh_query_cache_is_reused_without_external_search(self):
        query = {"topics": ["python", "testing"]}
        cached = repo("Acme/python-test-skills", 420, ["python", "testing"])
        value = empty_registry()
        value["queries"] = [cached_query(query, [cached])]
        self.write_registry(value)

        with mock.patch.object(
            self.module, "_github_get_json",
            side_effect=AssertionError("fresh query cache must be reused"),
        ):
            result = self.module.discover(query, [], str(self.registry))

        self.assertEqual([item["repository"] for item in result["candidates"]],
                         ["Acme/python-test-skills"])
        self.assertEqual(result["cache_status"], "fresh")
        self.assertIn("query-scoped", result["scope"])
        self.assertTrue(result["external_installation_requires_approval"])
        self.assertFalse(result["installation_performed"])
        self.assertEqual(result["candidates"][0]["review_status"], "unreviewed")

    def test_missing_installed_coverage_searches_github_and_filters_irrelevant_repositories(self):
        query = {"topics": ["python", "testing"]}
        value = empty_registry()
        self.write_registry(value)

        def github_search(url):
            from urllib.parse import parse_qs, urlsplit

            parsed = urlsplit(url)
            self.assertEqual(parsed.path, "/search/repositories")
            params = parse_qs(parsed.query)
            self.assertEqual(params["sort"], ["stars"])
            self.assertEqual(params["order"], ["desc"])
            self.assertEqual(params["per_page"], ["100"])
            self.assertIn("testing", params["q"][0])
            self.assertIn("skill", params["q"][0])
            return {
                "total_count": 2,
                "incomplete_results": False,
                "items": [
                    {"full_name": "Acme/python-testing-skills",
                     "html_url": "https://github.com/Acme/python-testing-skills",
                     "description": "Skills for Python testing",
                     "stargazers_count": 420,
                     "topics": ["python", "testing"],
                     "license": {"spdx_id": "MIT", "name": "MIT License"}},
                    {"full_name": "Acme/game-assets",
                     "html_url": "https://github.com/Acme/game-assets",
                     "description": "Popular game assets",
                     "stargazers_count": 9000,
                     "topics": ["games"],
                     "license": {"spdx_id": "MIT", "name": "MIT License"}},
                ],
            }

        with mock.patch.object(self.module, "_github_get_json", side_effect=github_search):
            result = self.module.discover(query, [], str(self.registry))

        self.assertEqual([item["repository"] for item in result["candidates"]],
                         ["Acme/python-testing-skills"])
        self.assertEqual(result["missing_topics"], ["python", "testing"])
        self.assertIn("python", result["scope"])
        self.assertIn("top 100", result["scope"])
        saved = json.loads(self.registry.read_text(encoding="utf-8"))
        self.assertEqual(len(saved["queries"]), 1)
        self.assertEqual(saved["queries"][0]["query"], query)
        self.assertIn("collected_at", saved["queries"][0])

