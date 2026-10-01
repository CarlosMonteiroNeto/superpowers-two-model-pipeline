"""Local-only, provenance-checked promotion staging."""
import importlib.util
import json
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts" / "template_promotion.py"


def load_module():
    spec = importlib.util.spec_from_file_location("r5_template_promotion", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PromotionDeliverables(unittest.TestCase):
    def test_promotion_contract_exists(self):
        self.assertTrue(SCRIPT.is_file(), "template promotion contract is missing")


@unittest.skipUnless(SCRIPT.is_file(), "promotion not implemented")
class PromotionStageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.promotion = load_module()
        self.request = {"repository": self.temp.name, "asset_id": "asset-a", "version": "1.0", "source_identity": "sha-a", "files": {"README.md": "reusable", "lib/a.py": "source"}}
        self.catalog = {"asset_id": "asset-a", "source_identity": "sha-a", "license": {"status": "known", "value": "mit"}, "dependencies": [], "verification": {"api": True, "tests": True}}

    def test_stage_checks_provenance_license_dependencies_and_exclusions(self):
        request = dict(self.request, files={**self.request["files"], "private-project-notes.md": "secret"})
        result = self.promotion.stage(request, self.catalog)
        self.assertEqual("staged", result["status"])
        self.assertNotIn("private-project-notes.md", result["files"])

    def test_duplicate_is_idempotent_and_overwrite_is_refused(self):
        first = self.promotion.stage(self.request, self.catalog)
        release = json.loads((Path(first["path"]) / "release.json").read_text(encoding="utf-8"))
        self.assertEqual("staged", release["status"])
        again = self.promotion.stage(self.request, self.catalog)
        self.assertEqual(first["stage_id"], again["stage_id"])
        changed = dict(self.request, files={"README.md": "different"})
        refused = self.promotion.stage(changed, self.catalog)
        self.assertEqual("overwrite_refused", refused["status"])

    def test_mismatched_source_or_unknown_license_is_blocked(self):
        bad = dict(self.catalog, source_identity="other")
        self.assertEqual("blocked", self.promotion.stage(self.request, bad)["status"])
        unknown = dict(self.catalog, license={"status": "unknown", "value": None})
        self.assertEqual("blocked", self.promotion.stage(self.request, unknown)["status"])
        no_destination = dict(self.request, repository="")
        self.assertEqual("blocked", self.promotion.stage(no_destination, self.catalog)["status"])

    def test_release_metadata_collision_is_blocked_before_writes(self):
        for path in ("release.json", "./release.json", "RELEASE.JSON", "release.json/child"):
            with self.subTest(path=path):
                repository = Path(self.temp.name) / str(len(list(Path(self.temp.name).iterdir())))
                repository.mkdir()
                request = dict(self.request, repository=str(repository), files={path: "caller payload"})
                result = self.promotion.stage(request, self.catalog)
                self.assertEqual("blocked", result["status"])
                self.assertFalse((repository / ".staging").exists())

    def test_normalized_aliases_case_collisions_and_file_directory_conflicts_are_blocked(self):
        cases = (
            {"./README.md": "one", "README.md": "two"},
            {"Lib/a.py": "one", "lib/A.py": "two"},
            {"folder": "file", "folder/child.txt": "child"},
        )
        for index, files in enumerate(cases):
            with self.subTest(files=files):
                repository = Path(self.temp.name) / str(index)
                repository.mkdir()
                result = self.promotion.stage(dict(self.request, repository=str(repository), files=files), self.catalog)
                self.assertEqual("blocked", result["status"])
                self.assertFalse((repository / ".staging").exists())

    def test_idempotent_retry_refuses_modified_payload(self):
        first = self.promotion.stage(self.request, self.catalog)
        readme = Path(first["path"]) / "README.md"
        readme.write_text("locally changed", encoding="utf-8")
        repeated = self.promotion.stage(self.request, self.catalog)
        self.assertEqual("overwrite_refused", repeated["status"])
        self.assertEqual("locally changed", readme.read_text(encoding="utf-8"))

    def test_idempotence_checks_inventory_and_symlinks_without_mutation(self):
        for mutation in ("delete", "extra", "symlink"):
            with self.subTest(mutation=mutation):
                repository = Path(self.temp.name) / mutation
                repository.mkdir()
                request = dict(self.request, repository=str(repository))
                first = self.promotion.stage(request, self.catalog)
                target = Path(first["path"])
                if mutation == "delete":
                    (target / "README.md").unlink()
                elif mutation == "extra":
                    (target / "extra.txt").write_text("extra", encoding="utf-8")
                else:
                    (target / "README.md").unlink()
                    try:
                        (target / "README.md").symlink_to(target / "lib" / "a.py")
                    except (OSError, NotImplementedError) as error:
                        if os.name == "nt":
                            self.skipTest("symlink creation unavailable: {}".format(error))
                        raise
                repeated = self.promotion.stage(request, self.catalog)
                self.assertEqual("overwrite_refused", repeated["status"])
                if mutation == "extra":
                    self.assertEqual("extra", (target / "extra.txt").read_text(encoding="utf-8"))

    def test_identical_target_returns_exact_physical_payload(self):
        first = self.promotion.stage(self.request, self.catalog)
        repeated = self.promotion.stage(self.request, self.catalog)
        self.assertEqual("staged", repeated["status"])
        self.assertTrue(repeated["idempotent"])
        for path, content in repeated["files"].items():
            self.assertEqual(content.encode("utf-8"), (Path(repeated["path"]) / path).read_bytes())

    def test_concurrent_winner_is_verified_before_idempotent_success(self):
        def winner_replace(source, destination):
            destination = Path(destination)
            winner = Path(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            winner.rename(destination)
            raise FileExistsError("concurrent winner appeared")

        with mock.patch.object(self.promotion.os, "replace", side_effect=winner_replace):
            result = self.promotion.stage(self.request, self.catalog)
        self.assertEqual("staged", result["status"])
        self.assertTrue(result["idempotent"])

    def test_concurrent_divergent_winner_is_refused_and_preserved(self):
        def divergent_replace(source, destination):
            winner = Path(source)
            (winner / "README.md").write_text("concurrent winner", encoding="utf-8")
            winner.rename(destination)
            raise FileExistsError("concurrent winner appeared")

        with mock.patch.object(self.promotion.os, "replace", side_effect=divergent_replace):
            result = self.promotion.stage(self.request, self.catalog)
        self.assertEqual("overwrite_refused", result["status"])
        stage_dir = Path(self.temp.name) / ".staging" / result["stage_id"]
        self.assertEqual("concurrent winner", (stage_dir / "README.md").read_text(encoding="utf-8"))
