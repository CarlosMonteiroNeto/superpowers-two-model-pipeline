import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
PY = sys.executable


class TouchesOverlapTest(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="touches-overlap-"))
        self.ws = self._tmp / "ws"
        self.ws.mkdir()
        self.plan = {"feature": "f", "tasks": [
            {"id": 1, "touches": ["src/a.go", "src/shared.go"]},
            {"id": 2, "touches": ["src/b.go"]},
            {"id": 3, "touches": ["src/shared.go", "src/c.go"]},
        ]}
        (self.ws / "plan.json").write_text(json.dumps(self.plan), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def run_it(self, *ids):
        return subprocess.run(
            [PY, str(SCRIPTS / "touches-overlap"), str(self.ws), *map(str, ids)],
            capture_output=True, text=True)

    def test_disjoint_is_zero(self):
        r = self.run_it(1, 2)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("disjoint", r.stdout)

    def test_overlap_is_one_and_names_files(self):
        r = self.run_it(1, 3)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout, "")
        self.assertIn("1 and 3", r.stderr)
        self.assertIn("src/shared.go", r.stderr)

    def test_single_id_is_disjoint(self):
        self.assertEqual(self.run_it(1).returncode, 0)

    def test_unknown_id_is_usage(self):
        self.assertEqual(self.run_it(1, 99).returncode, 2)

    def test_missing_plan_is_usage(self):
        (self.ws / "plan.json").unlink()
        self.assertEqual(self.run_it(1, 2).returncode, 2)

    def test_malformed_plan_is_usage(self):
        (self.ws / "plan.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(self.run_it(1, 2).returncode, 2)

    def test_no_args_is_usage(self):
        r = subprocess.run([PY, str(SCRIPTS / "touches-overlap")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
