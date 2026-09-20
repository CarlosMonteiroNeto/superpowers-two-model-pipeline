import json
import os
import pathlib
import sys
import tempfile
import unittest
import subprocess
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import jev_classify


def schema():
    return {"model": "jev-test", "questions": {"q1": {"type": "choice", "instructions": "Choose the applicable outcome.", "criteria": {"yes": None, "no": None}}}}


def provider(choice="yes", confidence=0.95):
    return {"model": "jev-test", "usage": {"input_tokens": 3}, "answers": {
        "q1": {"type": "choice", "choice": choice, "probabilities": {"yes": 0.95, "no": 0.05}, "confidence": confidence}
    }}


class ClassifierContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jev classifier ")
        self.workspace = self.tmp.name
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def transport(self, payload, timeout, api_key):
        self.calls.append((payload, timeout, api_key))
        return 200, provider()

    def test_valid_answer_is_cached_and_threshold_is_local(self):
        code, first = jev_classify.classify(schema(), {"state": 1}, workspace=self.workspace, site="site5", transport=self.transport)
        self.assertEqual(code, 0)
        self.assertFalse(first["cache_hit"])
        code, second = jev_classify.classify(schema(), {"state": 1}, workspace=self.workspace, site="site5", threshold=0.99, transport=self.transport)
        self.assertEqual(code, 1)
        self.assertTrue(second["cache_hit"])
        self.assertEqual(len(self.calls), 1)

    def test_changed_state_is_not_a_cache_hit(self):
        jev_classify.classify(schema(), {"state": 1}, workspace=self.workspace, site="site5", transport=self.transport)
        jev_classify.classify(schema(), {"state": 2}, workspace=self.workspace, site="site5", transport=self.transport)
        self.assertEqual(len(self.calls), 2)

    def test_rejects_malformed_batch_without_caching_it(self):
        def bad(*_args):
            return 200, {"model": "jev-test", "answers": {"q1": {"choice": "yes", "probabilities": {"yes": 0.8, "no": 0.8}, "confidence": 0.9}}}
        code, envelope = jev_classify.classify(schema(), {}, workspace=self.workspace, site="site5", transport=bad)
        self.assertEqual(code, 3)
        self.assertEqual(envelope["status"], "unavailable")
        self.assertEqual(envelope["answers"], {})

    def test_third_failure_opens_persisted_circuit_without_network(self):
        def down(*_args):
            raise OSError("offline")
        for _ in range(3):
            code, _ = jev_classify.classify(schema(), {}, workspace=self.workspace, site="site3", transport=down, sleep=lambda _: None)
            self.assertEqual(code, 3)
        calls = []
        code, envelope = jev_classify.classify(schema(), {}, workspace=self.workspace, site="site3", transport=lambda *_: calls.append(1), sleep=lambda _: None)
        self.assertEqual(code, 1)
        self.assertEqual(envelope["status"], "circuit_open")
        self.assertEqual(calls, [])

    def test_sites_three_and_four_have_one_short_attempt(self):
        seen = []
        def down(_payload, timeout, _key):
            seen.append(timeout)
            raise OSError("offline")
        jev_classify.classify(schema(), {}, workspace=self.workspace, site="site3", transport=down, sleep=lambda _: None)
        self.assertEqual(seen, [10])

    def test_empty_questions_does_not_call_network(self):
        code, envelope = jev_classify.classify({"model": "jev-test", "questions": {}}, {}, workspace=self.workspace, site="site5", transport=self.transport)
        self.assertEqual(code, 0)
        self.assertEqual(envelope["answers"], {})
        self.assertEqual(self.calls, [])

    def test_payload_is_choice_only_with_semantics(self):
        code, _ = jev_classify.classify(schema(), {"state": 1}, workspace=self.workspace, site="site5", transport=self.transport)
        self.assertEqual(code, 0)
        question = self.calls[0][0]["questions"]["q1"]
        self.assertEqual(question["type"], "choice")
        self.assertIn("instructions", question)
        self.assertEqual(question, {"type": "choice", "instructions": "Choose the applicable outcome.", "criteria": {"yes": None, "no": None}})

    def test_response_requires_choice_type_and_usage(self):
        invalid = provider()
        invalid["answers"]["q1"]["type"] = "text"
        code, envelope = jev_classify.classify(schema(), {}, workspace=self.workspace, site="site5", transport=lambda *_: (200, invalid))
        self.assertEqual(code, 3)
        self.assertIsNone(envelope["usage"])

    def test_unknown_site_is_local_input_error(self):
        code, envelope = jev_classify.classify(schema(), {}, workspace=self.workspace, site="unknown", transport=self.transport)
        self.assertEqual(code, 2)
        self.assertEqual(envelope["status"], "unavailable")
        self.assertEqual(envelope["error_kind"], "setup_error")

    def test_malformed_question_is_a_setup_error(self):
        code, envelope = jev_classify.classify(
            {"model": "jev-test", "questions": {"q1": "not an object"}},
            {}, workspace=self.workspace, site="site3", transport=self.transport,
        )
        self.assertEqual(code, 2)
        self.assertEqual(envelope["error_kind"], "setup_error")

    def test_cache_read_failure_is_explicit_and_does_not_call_provider(self):
        with mock.patch.object(jev_classify.jev_store, "read_cache", side_effect=OSError("cache unreadable")):
            code, envelope = jev_classify.classify(
                schema(), {}, workspace=self.workspace, site="site3", transport=self.transport,
            )
        self.assertEqual(code, 3)
        self.assertEqual(envelope["status"], "cache_unavailable")
        self.assertEqual(envelope["error_kind"], "cache_error")
        self.assertEqual(self.calls, [])

    def test_cache_write_failure_is_explicit_after_valid_response(self):
        with mock.patch.object(jev_classify.jev_store, "write_cache", side_effect=OSError("cache full")):
            code, envelope = jev_classify.classify(
                schema(), {}, workspace=self.workspace, site="site3", transport=self.transport,
            )
        self.assertEqual(code, 3)
        self.assertEqual(envelope["status"], "cache_unavailable")
        self.assertEqual(envelope["error_kind"], "cache_error")

    def test_envelope_includes_schema_hash(self):
        _, envelope = jev_classify.classify(schema(), {}, workspace=self.workspace, site="site5", transport=self.transport)
        self.assertRegex(envelope["schema_hash"], r"^[0-9a-f]{64}$")

    def test_real_cli_exits_two_for_unknown_site_without_network(self):
        schema_file = pathlib.Path(self.workspace) / "schema.json"
        state_file = pathlib.Path(self.workspace) / "state.json"
        schema_file.write_text(json.dumps(schema()), encoding="utf-8")
        state_file.write_text("{}", encoding="utf-8")
        result = subprocess.run([sys.executable, str(SCRIPTS / "jev_classify.py"), str(schema_file), str(state_file), "--workspace", self.workspace, "--site", "unknown"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
