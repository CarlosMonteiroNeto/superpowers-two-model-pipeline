"""R4 black box checks for correction routing and single review ownership."""
import importlib.util
import hashlib
import json
import pathlib
import os
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"


def load_module(testcase, name):
    path = SCRIPTS / (name + ".py")
    testcase.assertTrue(path.is_file(), "R4 requires the shared " + name + " API")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CorrectionRoutingTests(unittest.TestCase):
    def finding(self, scope="in_scope", paths=None, contracts=None):
        return {"severity": "Important", "file": "src/a.py", "line": 4,
                "issue": "incorrect result", "fix": "correct result",
                "correction_scope": scope, "affected_paths": paths or ["src/a.py"],
                "affected_contracts": contracts or ["returns the expected value"]}

    def review(self, finding=None):
        return {"verdict": "SEND_BACK", "findings": [finding or self.finding()],
                "minors": [], "summary": "fix the finding"}

    def task(self):
        return {"id": 1, "touches": ["src/a.py"],
                "acceptance": ["returns the expected value"], "scope_grants": []}

    def test_in_scope_send_back_routes_directly_to_coder(self):
        policy = load_module(self, "correction_policy")
        result = policy.decide(self.review(), self.task())
        self.assertEqual(result.get("action"), "coder")

    def test_structural_or_uncertain_finding_requires_director(self):
        policy = load_module(self, "correction_policy")
        for scope in ("structural", "uncertain"):
            with self.subTest(scope=scope):
                result = policy.decide(self.review(self.finding(scope)), self.task())
                self.assertEqual(result.get("action"), "director")

    def test_out_of_scope_path_needs_valid_grant_and_malformed_metadata_blocks(self):
        policy = load_module(self, "correction_policy")
        finding = self.finding(paths=["src/extra.py"])
        result = policy.decide(self.review(finding), self.task())
        self.assertEqual(result.get("action"), "director")
        task = self.task()
        task["scope_grants"] = [{"paths": ["src/extra.py"],
                                  "contracts": ["returns the expected value"]}]
        self.assertEqual(policy.decide(self.review(finding), task).get("action"), "director")
        issued = [{"path": "src/extra.py", "contracts": ["returns the expected value"],
                   "run_id": "run", "family_id": 1, "task_id": 1,
                   "attempt_id": "attempt", "issuer": "supervisor", "grant_id": "g1"}]
        self.assertEqual(policy.decide(self.review(finding), task, issued_grants=issued,
                          identity={"run_id": "run", "family_id": 1, "task_id": 1,
                                    "attempt_id": "attempt"}).get("action"), "coder")
        malformed = self.review(finding)
        del malformed["findings"][0]["affected_paths"]
        self.assertEqual(policy.decide(malformed, task).get("action"), "block")

    def test_any_malformed_finding_blocks_even_when_another_is_structural(self):
        policy = load_module(self, "correction_policy")
        review = self.review(self.finding("structural"))
        malformed = self.finding()
        del malformed["affected_contracts"]
        review["findings"].append(malformed)
        self.assertEqual(policy.decide(review, self.task()).get("action"), "block")

    def test_flutter_gate_delegates_semantic_review_to_shared_owner(self):
        gate = (ROOT / "skills" / "flutter-app-pipeline" / "scripts" / "green-gate").read_text(encoding="utf-8")
        shared = (SCRIPTS / "review-dispatch").read_text(encoding="utf-8")
        self.assertIn("review-dispatch", gate)
        self.assertIn("ensure_review", (SCRIPTS / "review_dispatch.py").read_text(encoding="utf-8"))
        self.assertNotIn('DISPATCH_BIN"', gate)
        self.assertIn("ensure_review", shared)

    def test_reviewer_schema_rejects_missing_structured_scope(self):
        schema = json.loads((ROOT / "skills" / "two-model-sdd-pipeline" / "schemas" / "reviewer-result.schema.json").read_text(encoding="utf-8"))
        finding = schema["$defs"]["finding"]
        self.assertIn("correction_scope", finding["required"])
        self.assertIn("affected_paths", finding["required"])
        self.assertIn("affected_contracts", finding["required"])

    def test_cli_only_accepts_a_matching_supervisor_registry_record(self):
        grants = load_module(self, "scope_grants")
        with tempfile.TemporaryDirectory() as temp:
            ws = pathlib.Path(temp)
            review = ws / "task-1-review.json"
            plan = ws / "plan.json"
            review.write_text(json.dumps(self.review(self.finding(paths=["src/extra.py"]))), encoding="utf-8")
            plan.write_text(json.dumps({"tasks": [self.task()]}), encoding="utf-8")
            (ws / ".pipeline-identity.json").write_text(json.dumps({"run_id": "run"}), encoding="utf-8")
            (ws / "task-1-review-state.json").write_text(json.dumps({"candidate_commit": "candidate"}), encoding="utf-8")
            command = ["python", str(SCRIPTS / "correction_policy.py"), str(review), str(plan), "1", str(ws)]
            self.assertEqual(subprocess.check_output(command, text=True).strip(), "director")
            owner = {"run_id": "run", "family_id": 1, "task_id": 1,
                     "attempt_id": "candidate", "grant_id": "issued-1",
                     "contracts": ["returns the expected value"], "allowed_roots": ["src"],
                     "registry_path": str(ws / "scope-grants.json")}
            self.assertEqual(grants.reserve({"path": "src/extra.py", "kind": "new_file"}, owner)["decision"], "grant")
            self.assertEqual(subprocess.check_output(command, text=True).strip(), "coder")
            owner["attempt_id"] = "old-candidate"
            records = json.loads((ws / "scope-grants.json").read_text(encoding="utf-8"))
            next(iter(records.values()))["attempt_id"] = "old-candidate"
            (ws / "scope-grants.json").write_text(json.dumps(records), encoding="utf-8")
            self.assertEqual(subprocess.check_output(command, text=True).strip(), "director")

    def test_legacy_review_entrypoint_reconciles_ambiguous_launch_without_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
            (root / "source.txt").write_text("source", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "source.txt"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "candidate"], check=True)
            candidate = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
            ws = root / "ws"
            ws.mkdir()
            package = ws / "task-1-review-package.diff"
            package.write_text("candidate package", encoding="utf-8")
            (ws / "task-1-review-state.json").write_text(
                json.dumps({"candidate_commit": candidate}), encoding="utf-8")
            count = root / "review-count.txt"
            stub = root / "review-worker.sh"
            stub.write_text('#!/usr/bin/env bash\necho call >> "{}"\nexit 124\n'.format(
                str(count).replace("\\", "/")), encoding="utf-8")
            os.chmod(stub, 0o755)
            env = dict(os.environ, DISPATCH_BIN=str(stub))
            command = ["bash", str(SCRIPTS / "review-dispatch"), "--legacy", str(ws), "1", str(package)]
            first = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True)
            second = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(first.returncode, 5, first.stderr)
            self.assertEqual(second.returncode, 5, second.stderr)
            self.assertEqual(count.read_text(encoding="utf-8").splitlines(), ["call"])
            claim_path = ws / f"task-1-review-claim-{candidate}.json"
            claim = json.loads(claim_path.read_text(encoding="utf-8"))
            evidence = ws / "recovered-review.json"
            evidence.write_text('{"verdict":"APPROVED"}', encoding="utf-8")
            disposition = dict(claim, issuer="supervisor", decision_id="review-decision-1",
                               outcome="completed", evidence_path=str(evidence),
                               evidence_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest())
            disposition_path = ws / "review-disposition.json"
            disposition_path.write_text(json.dumps(disposition), encoding="utf-8")
            reconcile = ["python", str(SCRIPTS / "legacy_review_claim.py"), "reconcile",
                         str(ws), "1", candidate, str(disposition_path)]
            self.assertEqual(subprocess.run(reconcile, cwd=root).returncode, 0)
            self.assertEqual(subprocess.run(command, cwd=root, env=env).returncode, 0)
            self.assertEqual(count.read_text(encoding="utf-8").splitlines(), ["call"])
            package2 = ws / "task-2-review-package.diff"
            package2.write_text("second candidate package", encoding="utf-8")
            state2 = ws / "task-2-review-state.json"
            state2.write_text(json.dumps({"candidate_commit": candidate}), encoding="utf-8")
            stub.write_text('#!/usr/bin/env bash\necho call >> "{}"\nexit 0\n'.format(
                str(count).replace("\\", "/")), encoding="utf-8")
            success = ["bash", str(SCRIPTS / "review-dispatch"), "--legacy", str(ws), "2", str(package2)]
            self.assertEqual(subprocess.run(success, cwd=root, env=env).returncode, 0)
            self.assertEqual(subprocess.run(success, cwd=root, env=env).returncode, 0)
            self.assertFalse(state2.exists())
            self.assertEqual(count.read_text(encoding="utf-8").splitlines(), ["call", "call"])


if __name__ == "__main__":
    unittest.main()
