import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import plan_fusion
import fusion_apply


def task(identifier, *, touches, depends_on=None, **extra):
    value = {
        "id": identifier,
        "title": "Task {}".format(identifier),
        "summary": "A complete task summary.",
        "touches": touches,
        "acceptance": ["Acceptance {}.".format(identifier)],
        "spec_refs": ["docs/spec.md#contract"],
        "depends_on": depends_on or [],
    }
    value.update(extra)
    return value


class FusionPipelineCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="fusion compatibility ")
        self.workspace = pathlib.Path(self.tmp.name) / "workspace with spaces"
        self.workspace.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_propose_with_no_candidates_writes_shadow_report_without_provider_call(self):
        draft = self.workspace / "draft.json"
        report = self.workspace / "report.json"
        draft.write_text(json.dumps({"tasks": [task(1, touches=["scripts/a.py"], corrects=1)]}), encoding="utf-8")
        code = plan_fusion.main(["propose", str(draft), "--workspace", str(self.workspace), "--report", str(report)])
        self.assertEqual(code, 0)
        value = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(value["pairs"], [])
        self.assertEqual(value["mode"], "shadow")

    def test_empty_offline_selection_preserves_draft_bytes_and_runtime_plan(self):
        draft = self.workspace / "draft.json"
        report = self.workspace / "report.json"
        selection = self.workspace / "selection.json"
        output = self.workspace / "output.json"
        source = b'{"tasks":[{"id":1,"title":"Task","summary":"Summary","touches":["scripts/a.py"],"acceptance":["A"],"spec_refs":["docs/spec.md#x"],"depends_on":[]}]}'
        draft.write_bytes(source)
        plan_fusion.main(["propose", str(draft), "--workspace", str(self.workspace), "--report", str(report)])
        report_value = json.loads(report.read_text(encoding="utf-8"))
        selection.write_text(json.dumps({"draft_hash": report_value["draft_hash"], "report_hash": plan_fusion.hash_json(report_value), "pairs": []}), encoding="utf-8")
        code = plan_fusion.main(["apply", str(draft), "--report", str(report), "--selection", str(selection), "--output", str(output)])
        self.assertEqual(code, 0)
        self.assertEqual(output.read_bytes(), source)
        self.assertEqual(draft.read_bytes(), source)

    def test_apply_refuses_source_or_runtime_plan_output_and_returns_domain_exit_one(self):
        draft = self.workspace / "draft.json"
        report = self.workspace / "report.json"
        selection = self.workspace / "selection.json"
        draft.write_text(json.dumps({"tasks": [task(1, touches=["scripts/a.py"], corrects=1)]}), encoding="utf-8")
        self.assertEqual(plan_fusion.main(["propose", str(draft), "--workspace", str(self.workspace), "--report", str(report)]), 0)
        report_value = json.loads(report.read_text(encoding="utf-8"))
        selection.write_text(json.dumps({"draft_hash": report_value["draft_hash"], "report_hash": plan_fusion.hash_json(report_value), "pairs": []}), encoding="utf-8")
        self.assertEqual(plan_fusion.main(["apply", str(draft), "--report", str(report), "--selection", str(selection), "--output", str(draft), "--overwrite"]), 1)
        self.assertEqual(plan_fusion.main(["apply", str(draft), "--report", str(report), "--selection", str(selection), "--output", str(self.workspace / "plan.json"), "--overwrite"]), 1)
        self.assertEqual(plan_fusion.main(["apply", str(draft), "--report", str(report), "--selection", str(selection), "--output", str(self.workspace / "Plan.JSON"), "--overwrite"]), 1)

    def test_invalid_draft_returns_input_exit_two(self):
        draft = self.workspace / "bad.json"
        draft.write_text("[]", encoding="utf-8")
        self.assertEqual(plan_fusion.main(["propose", str(draft), "--workspace", str(self.workspace), "--report", str(self.workspace / "report.json")]), 2)

    def test_missing_source_inputs_return_two_before_destination_write(self):
        self.assertEqual(plan_fusion.main(["propose", str(self.workspace / "missing.json"), "--workspace", str(self.workspace), "--report", str(self.workspace / "report.json")]), 2)
        draft = self.workspace / "draft.json"
        draft.write_text(json.dumps({"tasks": [task(1, touches=["scripts/a.py"], corrects=1)]}), encoding="utf-8")
        self.assertEqual(plan_fusion.main(["apply", str(draft), "--report", str(self.workspace / "missing-report.json"), "--selection", str(self.workspace / "missing-selection.json"), "--output", str(self.workspace / "output.json")]), 2)

    def test_fused_output_routes_serially_and_waves_without_runtime_changes(self):
        plan = {"tasks": [
            task(10, touches=["scripts/a.py"]),
            task(20, touches=["scripts/b.py"]),
            task(30, touches=["scripts/c.py"], depends_on=[10, 20]),
        ]}
        draft_hash = plan_fusion.hash_json(plan)
        report = {"draft_hash": draft_hash, "policy_version": "site5-v1", "source_snapshot": plan, "pairs": [{
            "ids": [10, 20], "candidate_hash": fusion_apply.candidate_hash(plan, [10, 20]),
            "choice": "same_shape_fuse", "confidence": .95,
            "probabilities": {"same_shape_fuse": .95, "keep_separate": .05},
        }]}
        selection = {"draft_hash": draft_hash, "report_hash": plan_fusion.hash_json(report), "pairs": [{
            "ids": [10, 20], "title": "Fused", "summary": "Combined", "rationale": "Same shape.",
        }]}
        output, _ = fusion_apply.apply_selection(plan, report, selection)
        (self.workspace / "plan.json").write_text(json.dumps(output), encoding="utf-8")
        (self.workspace / "ledger-task-1.jsonl").write_text('{"type":"task_complete"}\n', encoding="utf-8")
        (self.workspace / "ledger.jsonl").write_text('{"task":1,"type":"task_complete"}\n', encoding="utf-8")
        route = subprocess.run(["bash", str(SCRIPTS / "route-next"), str(self.workspace), "1", "2"], text=True, capture_output=True)
        self.assertEqual(route.returncode, 0, route.stderr)
        self.assertEqual(route.stdout.strip(), "NEXT 2")
        wave = subprocess.run([sys.executable, str(SCRIPTS / "wave-next"), str(self.workspace), "1"], text=True, capture_output=True)
        self.assertEqual(wave.returncode, 0, wave.stderr)
        self.assertEqual(wave.stdout.strip(), "RUN 2")
