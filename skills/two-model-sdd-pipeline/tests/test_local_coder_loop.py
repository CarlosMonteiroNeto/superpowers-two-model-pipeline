"""Task 5 RED: test evolution lineage and single-invocation local loops."""

import hashlib
import json
import os
import pathlib
import sys
import tempfile
import unittest


SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import red_evidence


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def record(task="7", attempt="a1", test="assert x == 1", prior=None,
           rationale="initial RED", acceptance="acc-1", red="red-1",
           snapshot="snap-1", green="green-1"):
    return {"task_id": task, "attempt_id": attempt,
            "test_digest": digest(test),
            "prior_digest": prior,
            "correction_rationale": rationale,
            "acceptance_id": acceptance, "red_evidence_id": red,
            "source_snapshot": snapshot, "green_evidence_id": green}


def identity(snapshot="snap-1"):
    return {"task_id": "7", "attempt_id": "a1",
            "acceptance_id": "acc-1", "source_snapshot": snapshot}


class RevisionChainTests(unittest.TestCase):
    def test_valid_genesis_plus_correction_chain_passes(self):
        first = record()
        second = record(test="assert x == 2", prior=first["test_digest"],
                        rationale="off-by-one in expectation")
        self.assertIsNone(
            red_evidence.validate_revision_chain([first, second], identity()))

    def test_stale_snapshot_missing_genesis_reorder_and_conflicts_rejected(self):
        first = record()
        second = record(test="assert x == 2", prior=first["test_digest"])
        with self.assertRaises(ValueError):
            red_evidence.validate_revision_chain(
                [first, dict(second, source_snapshot="snap-2")], identity())
        orphan = record(prior=digest("nope"))
        with self.assertRaises(ValueError):
            red_evidence.validate_revision_chain([orphan], identity())
        with self.assertRaises(ValueError):
            red_evidence.validate_revision_chain([second, first], identity())
        clash = record(test="assert x == 2", prior=first["test_digest"])
        twin = record(test="assert x == 3", prior=first["test_digest"])
        with self.assertRaises(ValueError):
            red_evidence.validate_revision_chain(
                [first, clash, twin], identity())
        other_task = record(task="8", prior=None)
        with self.assertRaises(ValueError):
            red_evidence.validate_revision_chain(
                [other_task, second], identity())
        other_acceptance = record(prior=None, acceptance="acc-2")
        with self.assertRaises(ValueError):
            red_evidence.validate_revision_chain(
                [other_acceptance, second], identity())
        with self.assertRaises(ValueError):
            red_evidence.validate_revision_chain([], identity())

    def test_append_is_atomic_and_preserves_prior_records(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="revisions-"))
        chain = tmp / "task-7-revisions.jsonl"
        first = record()
        red_evidence.append_revision(str(chain), first)
        before = chain.read_bytes()
        second = record(test="assert x == 2", prior=first["test_digest"])
        red_evidence.append_revision(str(chain), second)
        lines = chain.read_text(encoding="utf-8").splitlines()
        self.assertEqual(2, len(lines))
        self.assertTrue(chain.read_bytes().startswith(before))
        self.assertIsNone(red_evidence.validate_revision_chain(
            [json.loads(line) for line in lines], identity()))

    def test_append_rejects_forks_and_foreign_tasks(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="revisions-"))
        chain = tmp / "task-7-revisions.jsonl"
        first = record()
        red_evidence.append_revision(str(chain), first)
        fork = record(test="assert x == 9", prior=digest("unrelated"))
        with self.assertRaises(ValueError):
            red_evidence.append_revision(str(chain), fork)
        foreign = record(task="8", prior=first["test_digest"])
        with self.assertRaises(ValueError):
            red_evidence.append_revision(str(chain), foreign)
        lines = chain.read_text(encoding="utf-8").splitlines()
        self.assertEqual(1, len(lines))

    def test_loader_failures_cannot_pass(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="revisions-"))
        with self.assertRaises(ValueError):
            red_evidence.read_chain(str(tmp / "missing.jsonl"))
        corrupt = tmp / "corrupt.jsonl"
        corrupt.write_text('{"task_id": "7"\n', encoding="utf-8")
        with self.assertRaises(ValueError):
            red_evidence.read_chain(str(corrupt))
        with self.assertRaises(ValueError):
            red_evidence.append_revision(str(tmp / "chain.jsonl"),
                                         {"task_id": "7"})


def _capability_fixture(tmp):
    root = tmp / "proj"
    (root / "tests").mkdir(parents=True)
    case = root / "tests" / "loop_test.py"
    case.write_text(
        "import unittest\n\n\nclass T(unittest.TestCase):\n"
        "    def test_ok(self):\n        self.assertTrue(True)\n",
        encoding="utf-8")
    evdir = tmp / "ev"
    evdir.mkdir()
    policy = {
        "project_root": str(root), "evidence_dir": str(evdir),
        "scope": {"mode": "legacy", "roots": [], "exact_paths": []},
        "protected_paths": [],
        "toolchains": {
            "py": {"adapter": "unittest",
                   "commands": {
                       "test": {"argv": ["python", "-m", "unittest",
                                         "discover"],
                                "cwd": "."}}}},
    }
    return policy


class LocalCoderLoopTests(unittest.TestCase):
    def test_one_invocation_covers_investigation_checks_and_correction(self):
        import scoped_runner
        import dispatch_budget
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="local-loop-"))
        policy = _capability_fixture(tmp)
        budget_state = {}
        dispatches = []

        def fake_dispatch():
            dispatches.append(1)
            return dispatch_budget.reserve(
                {"run_id": "r", "task_family": 1, "task_id": 1,
                 "role": "operator", "dispatch_id": "d1"},
                {"cycle_allowances": [5, 3, 3]}, state=budget_state)

        checks = 0
        chain_path = tmp / "task-1-revisions.jsonl"
        snapshot = "loop-snap-1"
        genesis = {"task_id": "1", "attempt_id": "a1",
                   "test_digest": digest("assert rosa == 1"),
                   "prior_digest": None,
                   "correction_rationale": "initial RED",
                   "acceptance_id": "acc-loop",
                   "red_evidence_id": "red-1", "source_snapshot": snapshot,
                   "green_evidence_id": ""}
        red_evidence.append_revision(str(chain_path), genesis)
        for _ in range(3):
            resolved = scoped_runner.resolve_capability(
                {"mode": "test", "toolchain_id": "py",
                 "paths": ["tests/loop_test.py"]}, policy)
            self.assertIn("loop_test", " ".join(resolved["argv"]))
            checks += 1
        correction = dict(genesis, test_digest=digest("assert rosa == 2"),
                          prior_digest=genesis["test_digest"],
                          correction_rationale="fixture setup was wrong",
                          green_evidence_id="green-1")
        red_evidence.append_revision(str(chain_path), correction)
        chain = red_evidence.read_chain(str(chain_path))
        self.assertIsNone(red_evidence.validate_revision_chain(
            chain, {"task_id": "1", "attempt_id": "a1",
                    "acceptance_id": "acc-loop",
                    "source_snapshot": snapshot}))
        self.assertEqual(budget_state, {}, "local checks reserve no slots")
        self.assertEqual(dispatches, [])
        self.assertGreater(checks, 1)

    def test_external_retries_consume_budget_while_local_checks_do_not(self):
        import dispatch_budget
        self.assertEqual(dispatch_budget.DEFAULT_POLICY["cycle_allowances"],
                         [5, 3, 3])
        state = {}
        for index in range(1, 4):
            result = dispatch_budget.reserve(
                {"run_id": "r", "task_family": 1, "task_id": 1,
                 "role": "operator", "dispatch_id": "ext-%d" % index},
                {"cycle_allowances": [5, 3, 3]}, state=state)
            self.assertEqual(result["coder_invocations"], index)
        status = dispatch_budget.status("r", 1, state=state)
        self.assertEqual(status["coder_invocations"], 3)
        self.assertFalse(status["director_required"])

    def test_timeout_reaps_the_child_before_any_new_attempt(self):
        import codex_process
        started = {}

        def on_start(record):
            started.update(record)

        outcome = codex_process.run_owned(
            [sys.executable, "-c",
             "import time; time.sleep(30)"],
            os.getcwd(), "", 2, None, on_start)
        self.assertTrue(outcome.get("timed_out"), outcome)
        pid = started.get("pid")
        self.assertIsInstance(pid, int)
        self.assertIsNone(codex_process._start_identity(pid))
        followup = codex_process.run_owned(
            [sys.executable, "-c",
             "import time; time.sleep(2); print('clean')"],
            os.getcwd(), "", 30, None, None)
        self.assertEqual(followup.get("returncode"), 0)
        self.assertIn("clean", followup.get("stdout", ""))


if __name__ == "__main__":
    unittest.main()
