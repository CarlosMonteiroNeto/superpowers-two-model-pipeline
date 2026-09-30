import importlib.util
import hashlib
import json
import os
import pathlib
import subprocess
import sys
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
            "evidence": {**{field: "1" * 64 for field in
                         ("diff_hash", "graph_hash", "toolchains_hash", "policy_hash")},
                         "graph_provenance": {"complete": False, "diagnostics": ["no graph"]}},
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

    def test_caller_cannot_omit_toolchain_from_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            self._repository(root)
            workspace = self._workspace(root, ["python", "flutter"])
            result = subprocess.run(["bash", str(RUN_GATES), str(workspace), "--toolchains", "python"],
                                    cwd=root, text=True, capture_output=True)
            self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
            self.assertIn("must cover every toolchain", result.stderr)

    def test_candidate_change_during_command_never_records_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            self._repository(root, {"src.py": "before\n"})
            workspace = self._workspace(root, ["python"])
            entry = json.loads((workspace / "ledger.jsonl").read_text(encoding="utf-8"))
            entry["toolchain_descriptor"]["commands"]["test"]["argv"] = [
                "python", "-c", "from pathlib import Path; Path('src.py').write_text('during\\n')"]
            (workspace / "ledger.jsonl").write_text(json.dumps(entry) + "\n", encoding="utf-8")
            result = subprocess.run(["bash", str(RUN_GATES), str(workspace), "--tasks", "1"],
                                    cwd=root, text=True, capture_output=True)
            self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
            records = [json.loads(line) for line in (workspace / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
            evidence = [row for row in records if row.get("type") == "impact_gate_evidence"]
            self.assertEqual(len(evidence), 1)
            self.assertEqual(evidence[0]["gate_status"], "FAIL")

    def test_config_identity_covers_analyze_and_format_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            self._repository(root)
            workspace = self._workspace(root, ["python"])
            manifest = subject().create_workspace_manifest(str(workspace), ["1"], "tasks")
            before = manifest["identity"]["config_hash"]
            rows = [json.loads(line) for line in (workspace / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
            rows[0]["toolchain_descriptor"]["commands"]["analyze"]["argv"][-1] = "print('different')"
            (workspace / "ledger.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            changed = subject().create_workspace_manifest(str(workspace), ["1"], "tasks")
            self.assertNotEqual(before, changed["identity"]["config_hash"])

    def test_pre_task_baseline_hook_captures_machine_inventory_before_code_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            self._repository(root)
            (root / "test_baseline_failure.py").write_text(
                "import unittest\nclass Baseline(unittest.TestCase):\n def test_existing_failure(self): self.fail('known')\n",
                encoding="utf-8")
            workspace = self._workspace(root, ["python"])
            rows = [json.loads(line) for line in (workspace / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
            rows[0]["toolchain_descriptor"]["red_adapter"] = "unittest"
            rows[0]["toolchain_descriptor"]["commands"]["test"] = {
                "argv": [sys.executable, "-m", "unittest", "-v", "test_baseline_failure"],
                "cwd": str(root), "env": {}}
            (workspace / "ledger.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            env = dict(os.environ, PIPELINE_GATE_PHASE="baseline")
            result = subprocess.run(["bash", str(RUN_GATES), str(workspace), "--toolchains", "python"],
                                    cwd=root, env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            evidence_path = workspace / "supervisor/baseline-evidence.json"
            self.assertTrue(evidence_path.is_file(), result.stdout + result.stderr)
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            self.assertEqual(evidence["suites"][0]["raw_result"], {"status":"completed","exit_code":1})
            self.assertEqual(evidence["suites"][0]["failures"][0]["test"], "test_existing_failure (test_baseline_failure.Baseline.test_existing_failure)")
            entries = [json.loads(line) for line in (workspace / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(any(row.get("type")=="suite_evidence" and row.get("phase")=="baseline" for row in entries))

    def _repository(self, root, files=None):
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
        (root / ".gitignore").write_text(".superpowers/\n", encoding="utf-8")
        for name, contents in (files or {}).items():
            (root / name).write_text(contents, encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)

    def _workspace(self, root, toolchains):
        workspace = root / ".superpowers" / "workspace"
        workspace.mkdir(parents=True)
        (workspace / "plan.json").write_text(json.dumps({"tasks": [
            {"id": i + 1, "toolchain_id": item, "touches": ["src.py"]} for i, item in enumerate(toolchains)
        ]}), encoding="utf-8")
        descriptor = {"language": "python", "red_adapter": "unittest", "commands": {
            "test": {"argv": ["python", "-c", "pass"], "cwd": ".", "env": {}},
            "analyze": {"argv": ["python", "-c", "pass"], "cwd": ".", "env": {}},
            "format": {"argv": ["python", "-c", "pass"], "cwd": ".", "env": {}}}}
        rows = [{"type": "gate", "task": "-", "summary": "configured", "toolchain_id": item,
                 "toolchain_descriptor": descriptor} for item in toolchains]
        (workspace / "ledger.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return workspace


if __name__ == "__main__":
    unittest.main()
