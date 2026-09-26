"""R2.1 caller compatibility for exact toolchain and argv contracts."""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
if os.name == "nt":
    _git_bash = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
    BASH = str(_git_bash) if _git_bash.exists() else "bash"
else:
    BASH = "bash"


def run_script(script, args, cwd, env_extra=None):
    env = dict(os.environ)
    env["BASH_BIN"] = BASH
    env.update(env_extra or {})
    return subprocess.run(
        [BASH, str(SCRIPTS / script), *map(str, args)],
        cwd=str(cwd), env=env, capture_output=True, text=True,
    )


def write_stub(path, body):
    path = pathlib.Path(path)
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    if os.name == "nt":
        subprocess.run([BASH, "-c", "chmod +x '{}'".format(path)], capture_output=True)
    else:
        path.chmod(0o755)
    return path


class Task1PipelineCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = pathlib.Path(tempfile.mkdtemp(prefix="r2-task1-callsites-"))
        self.workspace = self.temp / "workspace"
        self.workspace.mkdir()

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def test_resolved_argv_command_survives_existing_run_gates_boundary(self):
        project = self.temp / "project with space"
        project.mkdir()
        (project / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
        marker = project / "command ran.txt"
        command = [
            sys.executable, "-c",
            "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('ran', encoding='utf-8')",
            str(marker),
        ]
        runtime = {
            "toolchains": {
                "python-unit-v1": {
                    "language": "python",
                    "executable": sys.executable,
                    "red_adapter": "unittest",
                    "commands": {
                        "red": {"argv": [sys.executable, "-m", "unittest"], "cwd": ".", "env": {}},
                        "test": {"argv": command, "cwd": ".", "env": {}},
                        "analyze": {"argv": [sys.executable, "-c", "pass"], "cwd": ".", "env": {}},
                    },
                },
            },
        }
        runtime_path = self.temp / "runtime.json"
        runtime_path.write_text(json.dumps(runtime), encoding="utf-8")
        resolved = run_script(
            "resolve-toolchain", ["--runtime", runtime_path, self.workspace, project], self.temp,
        )
        self.assertEqual(resolved.returncode, 0, resolved.stdout + resolved.stderr)
        entries = [json.loads(line) for line in
                   (self.workspace / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        gate = next(entry for entry in entries if entry.get("type") == "gate")

        result = run_script(
            "run-gates", [self.workspace, "--toolchains", gate["toolchain_id"]], self.temp,
            {"RTK_ENABLED": "0"},
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(marker.read_text(encoding="utf-8"), "ran")

    def test_missing_analyzer_is_reported_without_keyerror_after_red_and_test_resolve(self):
        project = self.temp / "python-project"
        project.mkdir()
        (project / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
        runtime_path = self.temp / "runtime.json"
        runtime_path.write_text(json.dumps({
            "toolchains": {
                "python-unit-v1": {
                    "language": "python",
                    "executable": sys.executable,
                    "red_adapter": "unittest",
                    "commands": {
                        "red": {"argv": [sys.executable, "-m", "unittest"], "cwd": ".", "env": {}},
                        "test": {"argv": [sys.executable, "-m", "unittest"], "cwd": ".", "env": {}},
                    },
                },
            },
        }), encoding="utf-8")

        result = run_script(
            "resolve-toolchain", ["--runtime", runtime_path, self.workspace, project], self.temp,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        gate = next(json.loads(line) for line in
                    (self.workspace / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
                    if json.loads(line).get("type") == "gate")
        descriptor = json.loads(gate["toolchain_descriptor"])
        self.assertNotIn("analyze", descriptor["commands"])
        self.assertFalse(gate["analyze_cmd"])

    def test_red_gate_maps_exact_toolchain_id_to_operator_language(self):
        (self.workspace / "plan.json").write_text(json.dumps({
            "tasks": [{"id": 1, "toolchain_id": "python-unit-v1", "touches": ["tests/test_x.py"]}],
        }), encoding="utf-8")
        (self.workspace / "task-1-brief.md").write_text("# Task 1\n", encoding="utf-8")
        entries = [
            {"type": "gate", "toolchain_id": "go-unit-v1", "lang": "go",
             "test_cmd": "true", "analyze_cmd": "true"},
            {"type": "gate", "toolchain_id": "python-unit-v1", "lang": "python",
             "test_cmd": "true", "analyze_cmd": "true"},
        ]
        (self.workspace / "ledger.jsonl").write_text(
            "\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8",
        )
        dispatched = self.temp / "dispatch.log"
        dispatch_stub = write_stub(
            self.temp / "dispatch-retry",
            'printf "%s\\n" "$*" > "${DISPATCH_LOG:?}"\n',
        )
        coder_stub = write_stub(self.temp / "coder-gate", "exit 0\n")

        result = run_script(
            "red-gate", [self.workspace, "1"], self.temp,
            {"DISPATCH_RETRY_BIN": str(dispatch_stub), "CODER_GATE_BIN": str(coder_stub),
             "DISPATCH_LOG": str(dispatched)},
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("--agent two-model-coder-python", dispatched.read_text(encoding="utf-8"))

    def test_orchestrator_selects_flutter_gate_using_descriptor_language(self):
        (self.workspace / "plan.json").write_text(json.dumps({
            "tasks": [{"id": 1, "toolchain_id": "flutter-stable-v1", "touches": ["lib/app.dart"]}],
        }), encoding="utf-8")
        ledger = [
            {"type": "gate", "toolchain_id": "flutter-stable-v1", "lang": "flutter",
             "test_cmd": "true", "analyze_cmd": "true"},
            {"type": "brief_ready", "task": "1", "summary": "ready"},
        ]
        (self.workspace / "ledger.jsonl").write_text(
            "\n".join(json.dumps(entry) for entry in ledger) + "\n", encoding="utf-8",
        )
        invoked = self.temp / "flutter-gate.log"
        flutter_stub = write_stub(
            self.temp / "flutter-red-gate",
            'echo "flutter gate selected" > "${FLUTTER_GATE_LOG:?}"\nexit 0\n',
        )

        result = run_script(
            "orchestrator", [self.workspace, "1", "1"], self.temp,
            {"FLUTTER_RED_GATE_BIN": str(flutter_stub), "FLUTTER_GATE_LOG": str(invoked)},
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(invoked.exists(), result.stdout + result.stderr)

    def test_final_gate_runs_every_exact_toolchain_used_by_the_plan(self):
        markers = [self.temp / "python gate one.txt", self.temp / "python gate two.txt"]
        tasks = []
        entries = []
        for task_id, marker in enumerate(markers, start=1):
            toolchain_id = "python-unit-%d" % task_id
            argv = [
                sys.executable, "-c",
                "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('ran', encoding='utf-8')",
                str(marker),
            ]
            tasks.append({"id": task_id, "toolchain_id": toolchain_id, "touches": ["tests/test_%d.py" % task_id]})
            entries.append({
                "type": "gate", "task": "-", "toolchain_id": toolchain_id, "lang": "python",
                "test_cmd": "python test placeholder", "analyze_cmd": "python analyze placeholder",
                "toolchain_descriptor": json.dumps({
                    "available": True,
                    "toolchain_id": toolchain_id,
                    "language": "python",
                    "project_root": str(self.temp),
                    "commands": {
                        "test": {"argv": argv, "cwd": str(self.temp), "env": {}},
                        "analyze": {"argv": [sys.executable, "-c", "pass"], "cwd": str(self.temp), "env": {}},
                    },
                }),
            })
        (self.workspace / "plan.json").write_text(json.dumps({"tasks": tasks}), encoding="utf-8")
        entries.extend([
            {"type": "review_outcome", "task": "1", "summary": "APPROVED"},
            {"type": "task_complete", "task": "1", "summary": "ok"},
            {"type": "review_outcome", "task": "2", "summary": "APPROVED"},
            {"type": "task_complete", "task": "2", "summary": "ok"},
        ])
        (self.workspace / "ledger.jsonl").write_text(
            "\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8",
        )

        result = run_script(
            "final-gate", [self.workspace, "2"], self.temp, {"RTK_ENABLED": "0"},
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([marker.read_text(encoding="utf-8") for marker in markers], ["ran", "ran"])


if __name__ == "__main__":
    unittest.main()
