"""Provider-neutral reusable solution research records."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts" / "solution_research.py"


def load_module():
    spec = importlib.util.spec_from_file_location("r5_solution_research", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ResearchTests(unittest.TestCase):
    def test_shared_collector_requires_evidence_and_does_not_dispatch(self):
        self.assertTrue(SCRIPT.is_file())
        research = load_module()
        calls = []
        def search(request):
            calls.append("search")
            return [{"name": "lib-a", "source": "registry", "evidence": ["https://example.invalid/a"], "compatibility": "compatible", "license": {"status": "known", "value": "mit"}}, {"name": "weak", "source": "registry"}]
        result = research.collect({"requirement": "storage"}, {"search": search})
        self.assertEqual(["search"], calls)
        self.assertEqual(["lib-a"], [item["name"] for item in result["alternatives"]])
        self.assertEqual("storage", result["requirement"])

    def test_mechanical_empty_lookup_does_not_request_extra_dispatch(self):
        research = load_module()
        result = research.collect({"requirement": "cache"}, {"search": lambda _request: []})
        self.assertEqual([], result["alternatives"])
        self.assertFalse(result["questions"])
