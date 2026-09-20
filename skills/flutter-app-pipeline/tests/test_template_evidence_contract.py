import base64
import hashlib
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from template_evidence import collect_evidence


class TestTemplateEvidenceContract(unittest.TestCase):
    def test_collect_evidence_keeps_missing_text_explicit_and_hashes_full_payload(self):
        """A missing README must remain missing rather than become synthetic text."""
        calls = []

        def fetch(url, token=None):
            calls.append(url)
            if url.endswith("/repos/acme/shop"):
                return {"license": {"spdx_id": "MIT"}, "stargazers_count": 100, "created_at": "2026-01-01T00:00:00Z"}
            if "/commits?per_page=1" in url:
                return [{"commit": {"committer": {"date": "2026-09-01T00:00:00Z"}}}]
            if "/search/issues?" in url:
                return {"total_count": 1 if "state:open" in url else 9}
            if url.endswith("/repos/acme/shop/readme"):
                raise OSError("not found")
            if url.endswith("/repos/acme/shop/contents/pubspec.yaml"):
                return {"content": base64.b64encode(b"name: shop\nenvironment:\n  sdk: '>=3.0.0 <4.0.0'\n").decode("ascii")}
            if url.endswith("/repos/acme/shop/git/trees/HEAD?recursive=1"):
                return {"tree": [{"path": "lib/main.dart"}, {"path": "pubspec.yaml"}]}
            raise AssertionError(url)

        evidence = collect_evidence("acme/shop", fetch_json=fetch)

        self.assertEqual(evidence["owner_repo"], "acme/shop")
        self.assertIsNone(evidence["readme_text"])
        self.assertIn("sdk", evidence["pubspec_text"])
        self.assertEqual(evidence["tree_text"], "lib/main.dart\npubspec.yaml")
        self.assertEqual(evidence["constraints"]["license"], {"status": "known", "value": "mit"})
        self.assertEqual(evidence["constraints"]["sdk"], {"status": "known", "value": ">=3.0.0"})
        self.assertEqual(evidence["score_report"]["verdict"], "AUTO_APPROVE")
        self.assertEqual(evidence["score_report"]["data"]["stars"], 100)
        canonical = dict(evidence)
        evidence_hash = canonical.pop("evidence_hash")
        canonical.pop("fetched_at")
        self.assertEqual(evidence_hash, hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest())
        self.assertTrue(any(url.endswith("/readme") for url in calls))
