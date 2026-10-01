"""Safe immutable template binding update previews."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts" / "template_repository.py"


def load_module():
    spec = importlib.util.spec_from_file_location("r5_template_repository", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RepositoryDeliverables(unittest.TestCase):
    def test_repository_contract_exists(self):
        self.assertTrue(SCRIPT.is_file(), "template repository contract is missing")


@unittest.skipUnless(SCRIPT.is_file(), "repository not implemented")
class RepositoryPreviewTests(unittest.TestCase):
    def setUp(self):
        self.repository = load_module()
        self.binding = {"asset_id": "asset-a", "version": "1.0", "source_identity": "sha-a", "files": {"README.md": "old", "lib/a.py": "base"}}
        self.candidate = {"version": "2.0", "source_identity": "sha-b", "files": {"README.md": "new", "lib/a.py": "base", "lib/b.py": "added"}}

    def test_preview_preserves_immutable_binding_and_reports_safe_changes(self):
        result = self.repository.preview_update(self.binding, self.candidate)
        self.assertEqual("update_available", result["status"])
        self.assertEqual("1.0", result["binding"]["version"])
        self.assertEqual(["lib/b.py"], result["added"])

    def test_local_edits_conflict_without_overwriting_or_path_traversal(self):
        binding = dict(self.binding, local_changes={"lib/a.py": "local"})
        candidate = dict(self.candidate, files={**self.candidate["files"], "lib/a.py": "upstream"})
        result = self.repository.preview_update(binding, candidate)
        self.assertEqual("conflict", result["status"])
        self.assertEqual("local", result["preserved_local"]["lib/a.py"])
        malicious = dict(self.candidate, files={"../secret": "x"})
        self.assertEqual("SETUP_ERROR", self.repository.preview_update(self.binding, malicious)["status"])
