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
    terms = list(query.get("topics", [])) + list(query.get("keywords", []))
    search_query = " ".join(terms + ["skill", "in:name,description,readme"])
    return {
        "query": query,
        "search_query": search_query,
        "collected_at": collected_at,
        "scope": "Query-scoped GitHub repository search for this query; up to 100 matching results sorted by stars, not exhaustive.",
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
        guard = mock.patch.object(
            self.module, "_github_get_json",
            side_effect=AssertionError("tests must not make live GitHub requests"),
        )
        guard.start()
        self.addCleanup(guard.stop)

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
        self.assertIn("query-scoped", result["scope"].casefold())
        self.assertTrue(result["external_installation_requires_approval"])
        self.assertFalse(result["installation_performed"])
        self.assertEqual(result["candidates"][0]["review_status"], "unreviewed")

    def test_query_cache_mismatch_in_result_limit_triggers_search(self):
        query = {"topics": ["python"], "limit": 1}
        value = empty_registry()
        value["queries"] = [cached_query({"topics": ["python"]}, [
            repo("Acme/cached-one", 90, ["python"]),
            repo("Acme/cached-two", 80, ["python"]),
        ])]
        self.write_registry(value)

        def github_search(url):
            return {"total_count": 1, "incomplete_results": False, "items": [{
                "full_name": "Acme/fresh-python-skill",
                "html_url": "https://github.com/Acme/fresh-python-skill",
                "description": "Python skill",
                "stargazers_count": 70,
                "topics": ["python"],
                "license": {"spdx_id": "MIT", "name": "MIT License"},
            }]}

        with mock.patch.object(self.module, "_now_iso",
                               return_value="2026-09-26T12:00:00Z"), \
                mock.patch.object(self.module, "_github_get_json",
                                  side_effect=github_search) as external:
            result = self.module.discover(query, [], str(self.registry))

        external.assert_called_once()
        self.assertEqual([item["repository"] for item in result["candidates"]],
                         ["Acme/fresh-python-skill"])

    def test_query_cache_mismatch_in_page_size_triggers_search(self):
        query = {"topics": ["python"], "limit": 2, "per_page": 2}
        cached = cached_query(
            {"topics": ["python"], "limit": 2, "per_page": 1},
            [repo("Acme/cached-one", 90, ["python"])],
        )
        cached.update({"limit": 2, "per_page": 1})
        value = empty_registry()
        value["queries"] = [cached]
        self.write_registry(value)

        def github_search(url):
            from urllib.parse import parse_qs, urlsplit

            self.assertEqual(parse_qs(urlsplit(url).query)["per_page"], ["2"])
            return {"total_count": 2, "incomplete_results": False, "items": [
                {"full_name": "Acme/fresh-one", "html_url": "https://github.com/Acme/fresh-one",
                 "description": "Python skill", "stargazers_count": 70,
                 "topics": ["python"], "license": {"spdx_id": "MIT", "name": "MIT License"}},
                {"full_name": "Acme/fresh-two", "html_url": "https://github.com/Acme/fresh-two",
                 "description": "Python skill", "stargazers_count": 60,
                 "topics": ["python"], "license": {"spdx_id": "MIT", "name": "MIT License"}},
            ]}

        with mock.patch.object(self.module, "_now_iso",
                               return_value="2026-09-26T12:00:00Z"), \
                mock.patch.object(self.module, "_github_get_json",
                                  side_effect=github_search) as external:
            result = self.module.discover(query, [], str(self.registry))

        external.assert_called_once()
        self.assertEqual(len(result["candidates"]), 2)

    def test_cached_results_are_capped_to_the_requested_limit(self):
        query = {"topics": ["python"], "limit": 1, "per_page": 100}
        cached = cached_query(query, [
            repo("Acme/python-one", 90, ["python"]),
            repo("Acme/python-two", 80, ["python"]),
            repo("Acme/python-three", 70, ["python"]),
        ])
        cached.update({"limit": 1, "per_page": 100})
        value = empty_registry()
        value["queries"] = [cached]
        self.write_registry(value)

        with mock.patch.object(self.module, "_now_iso",
                               return_value="2026-09-26T12:00:00Z"), \
                mock.patch.object(self.module, "_github_get_json",
                                  side_effect=AssertionError("fresh matching cache must be reused")):
            result = self.module.discover(query, [], str(self.registry))

        self.assertEqual([item["repository"] for item in result["candidates"]],
                         ["Acme/python-one"])

    def test_installed_topic_matching_requires_whole_tokens(self):
        cases = [
            ("go", "Django lint helper", "Django style checks"),
            ("ai", "Training assistant", "Training workflow"),
        ]
        for topic, name, description in cases:
            with self.subTest(topic=topic):
                self.write_registry(empty_registry())
                with mock.patch.object(self.module, "_now_iso",
                                       return_value="2026-09-26T12:00:00Z"), \
                        mock.patch.object(self.module, "_github_get_json", return_value={
                            "total_count": 0, "incomplete_results": False, "items": [],
                        }) as external:
                    result = self.module.discover(
                        {"topics": [topic]},
                        [{"name": name, "description": description,
                          "topics": ["unrelated"]}],
                        str(self.registry),
                    )

                external.assert_called_once()
                self.assertEqual(result["missing_topics"], [topic])
                self.assertEqual(result["installed_matches"], [])

    def test_registry_topic_matching_does_not_accept_substrings(self):
        query = {"topics": ["go"]}
        value = empty_registry()
        value["sources"] = [{
            "repository": "Acme/Django-skills",
            "source_url": "https://github.com/Acme/Django-skills",
            "category": "publisher",
            "revision": "rev-1",
            "last_checked_at": "2026-09-20T12:00:00Z",
            "review_status": "unreviewed",
            "description": "Django training helpers",
            "stars": 45,
            "topics": ["web"],
            "license": {"spdx_id": "MIT", "name": "MIT License"},
            "skills": [{
                "name": "Django helper",
                "path": "skills/django/SKILL.md",
                "topics": [],
                "compatibility": [],
                "license": {"spdx_id": "MIT", "name": "MIT License"},
                "review_status": "unreviewed",
            }],
        }]
        self.write_registry(value)

        with mock.patch.object(self.module, "_now_iso",
                               return_value="2026-09-26T12:00:00Z"), \
                mock.patch.object(self.module, "_github_get_json", return_value={
                    "total_count": 0, "incomplete_results": False, "items": [],
                }) as external:
            result = self.module.discover(query, [], str(self.registry))

        external.assert_called_once()
        self.assertEqual(result["candidates"], [])

    def test_registered_skill_metadata_is_searched_before_external_sources(self):
        query = {"topics": ["python"], "compatibility": ["codex"]}
        value = empty_registry()
        value["sources"] = [{
            "repository": "Acme/registered-python-skills",
            "source_url": "https://github.com/Acme/registered-python-skills",
            "category": "publisher",
            "revision": "rev-abc",
            "last_checked_at": "2026-09-20T12:00:00Z",
            "review_status": "unreviewed",
            "description": "Reusable Python skills",
            "stars": 77,
            "topics": ["python"],
            "license": {"spdx_id": "MIT", "name": "MIT License"},
            "skills": [{
                "name": "Python test helper",
                "path": "skills/python-test/SKILL.md",
                "topics": ["python"],
                "compatibility": ["codex"],
                "license": {"spdx_id": "MIT", "name": "MIT License"},
                "review_status": "unreviewed",
            }],
        }]
        self.write_registry(value)

        with mock.patch.object(self.module, "_now_iso",
                               return_value="2026-09-26T12:00:00Z"), \
                mock.patch.object(self.module, "_github_get_json", return_value={
                    "total_count": 0, "incomplete_results": False, "items": [],
                }) as external:
            result = self.module.discover(query, [], str(self.registry))

        external.assert_not_called()
        self.assertEqual([item["repository"] for item in result["candidates"]],
                         ["Acme/registered-python-skills"])
        self.assertEqual(result["candidates"][0]["skills"][0]["recommendation_status"],
                         "review_required")

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

    def test_skill_recommendations_expose_relevance_compatibility_source_and_license_checks(self):
        query = {"topics": ["python"], "compatibility": ["codex"]}
        candidate = repo("Acme/python-skills", 99, ["python"])
        candidate["skills"] = [{
            "name": "OpenCode-only helper",
            "path": "skills/opencode-helper/SKILL.md",
            "topics": ["python"],
            "compatibility": ["opencode"],
            "license": None,
            "review_status": "unreviewed",
        }]
        value = empty_registry()
        value["queries"] = [cached_query(query, [candidate])]
        self.write_registry(value)

        result = self.module.discover(query, [], str(self.registry))

        self.assertEqual(len(result["candidates"]), 1)
        skill = result["candidates"][0]["skills"][0]
        self.assertEqual(skill["checks"], {
            "relevance": True,
            "compatibility": False,
            "source": True,
            "license": False,
        })
        self.assertEqual(skill["recommendation_status"], "review_required")
        self.assertTrue(result["external_installation_requires_approval"])
        self.assertFalse(result["installation_performed"])
