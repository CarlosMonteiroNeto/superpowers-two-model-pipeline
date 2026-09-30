import importlib.util
import hashlib
import json
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills/two-model-sdd-pipeline/scripts/gate_evidence.py"
RUN_GATES = ROOT / "skills/two-model-sdd-pipeline/scripts/run-gates"


def subject():
    spec = importlib.util.spec_from_file_location("gate_evidence", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ImpactGateEvidenceTests(unittest.TestCase):
    def test_evidence_matches_only_same_candidate_and_verified_impact_manifest(self):
        manifest = {
            "schema_version": 1, "mode": "full_suite", "scope_paths": [], "tests": [],
            "commands": [], "reasons": [], "reasons_detail": [], "gaps": [],
            "identity": {"head_commit": "b" * 40, "tree_hash": "c" * 64,
                         "base_commit": "a" * 40, "base_tree_hash": "f" * 64,
                         "config_hash": "d" * 64, "environment_hash": "e" * 64,
                         "policy_version": "r4-impact-1"},
            "evidence": {field: "1" * 64 for field in
                         ("diff_hash", "graph_hash", "toolchains_hash", "policy_hash")},
        }
        manifest["selection_hash"] = hashlib.sha256(json.dumps(
            manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        candidate = {"commit": "b" * 40, "tree_hash": "c" * 64,
                    "config_hash": "d" * 64, "environment_hash": "e" * 64,
                    "impact_manifest": manifest}
        record = {"candidate_commit": "b" * 40, "tree_hash": "c" * 64,
                  "config_hash": "d" * 64, "environment_hash": "e" * 64,
                  "impact_selection_hash": manifest["selection_hash"]}
        self.assertTrue(subject().matches(record, candidate))
        for field, value in (("candidate_commit", "f" * 40), ("tree_hash", "f" * 64),
                             ("config_hash", "f" * 64), ("environment_hash", "f" * 64),
                             ("impact_selection_hash", "f" * 64)):
            changed = dict(record)
            changed[field] = value
            with self.subTest(field=field):
                self.assertFalse(subject().matches(changed, candidate))

    def test_manifest_hash_tampering_is_rejected(self):
        manifest = {"selection_hash": "0" * 64, "schema_version": 1}
        with self.assertRaises(ValueError):
            subject().validate_manifest(manifest)

    def test_task_gate_generates_script_owned_full_suite_manifest_when_graph_unknown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            (root / ".gitignore").write_text(".superpowers/\n", encoding="utf-8")
            subprocess.run(["git", "add", ".gitignore"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
            workspace = root / ".superpowers" / "workspace"
            workspace.mkdir(parents=True)
            descriptor = {"language": "python", "red_adapter": "unittest", "commands": {
                "test": {"argv": ["python", "-c", "pass"], "cwd": ".", "env": {}}}}
            (workspace / "plan.json").write_text(json.dumps({"tasks": [
                {"id": 1, "toolchain_id": "python", "touches": ["src.py"]}]}), encoding="utf-8")
            (workspace / "ledger.jsonl").write_text(json.dumps({"type": "gate", "task": "-",
                "summary": "configured", "toolchain_id": "python", "toolchain_descriptor": descriptor}) + "\n", encoding="utf-8")
            result = subprocess.run(["bash", str(RUN_GATES), str(workspace), "--toolchains", "python"],
                                    cwd=root, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            manifest = json.loads((workspace / "impact-manifest.json").read_text(encoding="utf-8"))
            subject().validate_manifest(manifest)
            records = [json.loads(line) for line in (workspace / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
            impact_records = [item for item in records if item.get("type") == "impact_gate_evidence"]
            self.assertEqual(len(impact_records), 1)
            self.assertEqual(impact_records[0]["selection_hash"], manifest["selection_hash"])
            self.assertEqual(impact_records[0]["phase"], "task")
            self.assertEqual(manifest["mode"], "full_suite")
            self.assertEqual(manifest["commands"][0]["argv"], ["python", "-c", "pass"])
            self.assertEqual(manifest["commands"][0]["tests"], [])
            self.assertEqual(manifest["scope_paths"], ["src.py"])


if __name__ == "__main__":
    unittest.main()
