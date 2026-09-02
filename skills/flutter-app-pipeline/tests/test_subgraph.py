import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"

if os.name == "nt":
    git_bash = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
    BASH = str(git_bash) if git_bash.exists() else "bash"
else:
    BASH = "bash"


def write_stub(directory, name, body):
    p = pathlib.Path(directory) / name
    p.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    if os.name == "nt":
        subprocess.run([BASH, "-c", "chmod +x '{}'".format(p)], capture_output=True)
    else:
        p.chmod(0o755)
    return str(p)


def run_script(script, args, cwd, env_extra):
    env = dict(os.environ)
    env.update(env_extra)
    return subprocess.run(
        [BASH, str(SCRIPTS / script), *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
    )


class SubgraphTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="subgraph-tests-"))
        self.stub_dir = self._tmp / "stubs"
        self.stub_dir.mkdir()
        self.graphify = write_stub(
            self.stub_dir,
            "graphify",
            """
cmd="$1"; shift
echo "$cmd $*" >> "${STUB_LOG:?}"
case "$cmd" in
  update)
    echo "graphify: updated graph at $1" ;;
  explain)
    echo "graphify: explain -> node=$1 deps=[b,c]" ;;
  path)
    echo "graphify: path $1 -> $2" ;;
esac
exit "${STUB_GRAPHIFY_EXIT:-0}"
""",
        )
        self.env = {
            "GRAPHIFY_BIN": self.graphify,
            "GRAPHIFY_ENABLED": "1",
            "RTK_ENABLED": "0",
        }

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def make_ws(self, plan_tasks):
        ws = self._tmp / "ws"
        ws.mkdir(exist_ok=True)
        plan = {"feature": "test", "global_constraints": [], "tasks": plan_tasks}
        (ws / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        return ws


class TestGraphifyUpdate(SubgraphTestBase):
    def test_invokes_graphify_update_on_root(self):
        log = self._tmp / "g.log"
        r = run_script(
            "graphify-update", [str(self._tmp)],
            cwd=self._tmp, env_extra={**self.env, "STUB_LOG": str(log)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = log.read_text(encoding="utf-8").splitlines()
        self.assertTrue(any(c.strip().startswith("update ") for c in calls), calls)

    def test_disabled_skips_graphify(self):
        log = self._tmp / "g.log"
        r = run_script(
            "graphify-update", [str(self._tmp)],
            cwd=self._tmp,
            env_extra={**self.env, "STUB_LOG": str(log), "GRAPHIFY_ENABLED": "0"},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = log.read_text(encoding="utf-8") if log.exists() else ""
        self.assertEqual(calls, "")


class TestGraphifySubgraph(SubgraphTestBase):
    def test_writes_interfaces_file_from_touches(self):
        ws = self.make_ws([
            {"id": 3, "title": "task 3", "touches": ["lib/foo.dart"], "depends_on": []},
        ])
        log = self._tmp / "g.log"
        r = run_script(
            "graphify-subgraph", [str(ws), "3"],
            cwd=self._tmp, env_extra={**self.env, "STUB_LOG": str(log)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = ws / "task-3-interfaces.md"
        self.assertTrue(out.exists())
        text = out.read_text(encoding="utf-8")
        self.assertIn("foo", text)

    def test_multiple_touches_each_queried(self):
        ws = self.make_ws([
            {"id": 4, "title": "task 4",
             "touches": ["lib/a.dart", "lib/b.dart"], "depends_on": []},
        ])
        log = self._tmp / "g.log"
        r = run_script(
            "graphify-subgraph", [str(ws), "4"],
            cwd=self._tmp, env_extra={**self.env, "STUB_LOG": str(log)},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = log.read_text(encoding="utf-8").splitlines()
        self.assertTrue(any("explain lib/a.dart" in c for c in calls), calls)
        self.assertTrue(any("explain lib/b.dart" in c for c in calls), calls)

    def test_missing_task_is_usage(self):
        ws = self.make_ws([
            {"id": 1, "title": "task 1", "touches": ["lib/a.dart"], "depends_on": []},
        ])
        r = run_script("graphify-subgraph", [str(ws), "9"], cwd=self._tmp, env_extra=self.env)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_missing_plan_is_usage(self):
        ws = self._tmp / "ws2"
        ws.mkdir()
        r = run_script("graphify-subgraph", [str(ws), "1"], cwd=self._tmp, env_extra=self.env)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()