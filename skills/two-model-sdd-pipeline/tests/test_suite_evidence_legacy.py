import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import suite_evidence
import toolchain_gate


class LegacySuiteEvidenceTests(unittest.TestCase):
    def test_legacy_gate_descriptor_is_used_for_command_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            gate = {"type": "gate", "lang": "python"}
            (root / "ledger.jsonl").write_text(json.dumps(gate) + "\n")
            (root / "run-gates-test.txt").write_text("test_ok (test.Example.test_ok) ... ok\nRan 1 test in 0.001s\nOK\n")
            (root / "run-gates-test.txt.exit-code").write_text("0")
            descriptor = {"red_adapter": "unittest"}
            with patch.object(toolchain_gate, "gate_for_toolchain", side_effect=toolchain_gate.GateContractError("legacy")), patch.object(toolchain_gate, "_descriptor", return_value=descriptor), patch.object(suite_evidence, "subprocess_check", return_value="tree"), patch.object(suite_evidence, "validate_evidence"):
                evidence = suite_evidence.capture(tmp, ["python"], tmp, str(root / "evidence.json"))
            self.assertEqual(evidence["command_hash"], suite_evidence._hash({"python": descriptor}))


if __name__ == "__main__":
    unittest.main()
