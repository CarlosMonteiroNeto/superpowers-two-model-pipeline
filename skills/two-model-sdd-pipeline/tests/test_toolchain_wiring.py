"""Exact, task-selected toolchain wiring for multi-toolchain projects."""

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
    _gb = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
    BASH = str(_gb) if _gb.exists() else "bash"
else:
    BASH = "bash"


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


def gate_entry(lang, test_cmd, analyze_cmd, toolchain_id=None):
    return {"ts": "x", "type": "gate", "task": "-",
            "summary": "preinstalled: " + lang,
            "toolchain_id": toolchain_id or lang,
            "lang": lang, "test_cmd": test_cmd, "analyze_cmd": analyze_cmd}


def ledger_langs(path):
    if not path.exists():
        return []
    return [json.loads(l)["lang"] for l in
            path.read_text(encoding="utf-8").splitlines() if l.strip()]


class ToolchainWiringBase(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="toolchain-wiring-"))
        self.ws = self._tmp / "ws"
        self.ws.mkdir()
        self.repo = self._tmp / "repo"
        self.repo.mkdir()
        (self.repo / "README.md").write_text("x\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def ledger_path(self):
        return self.ws / "ledger.jsonl"

    def write_ledger(self, entries):
        (self.ws / "ledger.jsonl").write_text(
            "\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


class TestResolveToolchainAll(ToolchainWiringBase):
    def test_mixed_task_selection_does_not_fall_back_to_single_legacy_gate(self):
        (self.ws / "plan.json").write_text(json.dumps({
            "tasks": [
                {"id": 1, "touches": ["legacy.py"]},
                {"id": 2, "toolchain_id": "python-structured-v1",
                 "touches": ["structured.py"]},
            ],
        }), encoding="utf-8")
        self.write_ledger([gate_entry(
            "python",
            'python -c "open(\'legacy-gate-ran.txt\', \'w\').write(\'ran\')"',
            'python -c "pass"',
            "python-legacy-v1",
        )])

        result = run_script(
            "run-gates", [str(self.ws), "--tasks", "1", "2"],
            cwd=self._tmp, env_extra={"RTK_ENABLED": "0"},
        )

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.ws / "legacy-gate-ran.txt").exists())

    def test_all_deduplicates_markers_that_share_one_toolchain_id(self):
        (self.repo / "pyproject.toml").write_text("[project]\nname = 'sample'\n", encoding="utf-8")
        (self.repo / "requirements.txt").write_text("", encoding="utf-8")
        runtime_path = self._tmp / "runtime.json"
        runtime_path.write_text(json.dumps({"toolchains": {
            "python-shared-v1": {
                "language": "python",
                "executable": sys.executable,
                "red_adapter": "unittest",
                "commands": {
                    "red": {"argv": [sys.executable, "-c", "pass"], "cwd": ".", "env": {}},
                    "test": {"argv": [sys.executable, "-c", "pass"], "cwd": ".", "env": {}},
                    "analyze": {"argv": [sys.executable, "-c", "pass"], "cwd": ".", "env": {}},
                },
            },
        }}), encoding="utf-8")

        resolved = run_script(
            "resolve-toolchain",
            ["--all", "--runtime", str(runtime_path), str(self.ws), str(self.repo)],
            cwd=self._tmp, env_extra={},
        )

        self.assertEqual(resolved.returncode, 0, resolved.stdout + resolved.stderr)
        entries = [json.loads(line) for line in self.ledger_path().read_text(encoding="utf-8").splitlines()]
        self.assertEqual([entry["toolchain_id"] for entry in entries], ["python-shared-v1"])
        selected = run_script(
            "run-gates", [str(self.ws), "--toolchains", "python-shared-v1"],
            cwd=self._tmp, env_extra={"RTK_ENABLED": "0"},
        )
        self.assertEqual(selected.returncode, 0, selected.stdout + selected.stderr)

    def test_all_keeps_supported_gate_and_rejects_unconfigured_node(self):
        (self.repo / "go.mod").write_text("module test\n", encoding="utf-8")
        (self.repo / "package.json").write_text("{}\n", encoding="utf-8")
        r = run_script("resolve-toolchain", ["--all", str(self.ws), str(self.repo)],
                       cwd=self._tmp, env_extra={})
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        langs = ledger_langs(self.ledger_path())
        self.assertEqual(langs, ["go"])
        self.assertNotIn("npm test", r.stdout + r.stderr)
        self.assertNotIn("npx eslint", r.stdout + r.stderr)

    def test_all_without_any_marker_still_exits_2(self):
        r = run_script("resolve-toolchain", ["--all", str(self.ws), str(self.repo)],
                       cwd=self._tmp, env_extra={})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(ledger_langs(self.ledger_path()), [])

    def test_all_preserves_legacy_single_marker_mode_without_flag(self):
        (self.repo / "go.mod").write_text("module test\n", encoding="utf-8")
        r = run_script("resolve-toolchain", [str(self.ws), str(self.repo)],
                       cwd=self._tmp, env_extra={})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(ledger_langs(self.ledger_path()), ["go"])


class TestTaskLang(ToolchainWiringBase):
    def setUp(self):
        super().setUp()
        self.plan = {
            "feature": "f",
            "tasks": [
                {"id": 1, "title": "math", "toolchain_id": "go-unit-v1",
                 "touches": ["lib/go/math.go"],
                 "depends_on": []},
                {"id": 2, "title": "calc", "toolchain_id": "node-test-v1",
                 "touches": ["src/calc.js"],
                 "depends_on": []},
                {"id": 3, "title": "docs", "touches": ["README.md"],
                 "depends_on": []},
                {"id": 4, "title": "no-touch", "touches": [], "depends_on": []},
            ],
        }
        (self.ws / "plan.json").write_text(json.dumps(self.plan), encoding="utf-8")
        self.write_ledger([
            gate_entry("go", "go test ./...", "go vet ./...", "go-unit-v1"),
            gate_entry("node", "node --test", "eslint .", "node-test-v1"),
        ])

    def run_lang(self, task, root):
        return run_script("task-lang", [str(self.ws), task, root],
                          cwd=self._tmp, env_extra={})

    def run_toolchain(self, task, root):
        return run_script("task-toolchain", [str(self.ws), task, root],
                          cwd=self._tmp, env_extra={})

    def test_resolves_language_through_exact_task_toolchain_identity(self):
        (self.repo / "go.mod").write_text("module test\n", encoding="utf-8")
        r = self.run_lang("1", str(self.repo))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), "go")

    def test_task_toolchain_returns_exact_declared_identity(self):
        (self.repo / "go.mod").write_text("module test\n", encoding="utf-8")
        r = self.run_toolchain("1", str(self.repo))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), "go-unit-v1")

    def test_task_identity_wins_over_nearer_marker(self):
        (self.repo / "go.mod").write_text("module test\n", encoding="utf-8")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "package.json").write_text("{}\n", encoding="utf-8")
        r = self.run_lang("2", str(self.repo))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), "node")

    def test_missing_task_identity_is_not_guessed_from_branch_gate(self):
        r = self.run_lang("3", str(self.repo))
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_task_without_touches_must_still_name_its_toolchain(self):
        r = self.run_lang("4", str(self.repo))
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_missing_plan_fails_closed(self):
        (self.ws / "plan.json").unlink()
        r = self.run_lang("1", str(self.repo))
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)


class TestGateEntryFor(ToolchainWiringBase):
    def setUp(self):
        super().setUp()
        self.write_ledger([
            gate_entry("python", "python -m unittest", "ruff check .", "python-unit-v1"),
            gate_entry("python", "python -m unittest tests.integration", "mypy .", "python-integration-v1"),
            gate_entry("python", "python -m unittest tests.lint", "ruff check tests/lint", "python-lint-v1"),
        ])

    def run_entry(self, *args):
        return run_script("gate-entry-for", [str(self.ws)] + list(args),
                          cwd=self._tmp, env_extra={})

    def test_returns_exact_task_toolchain_identity(self):
        r = self.run_entry("python-unit-v1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        entry = json.loads(r.stdout.strip())
        self.assertEqual(entry["toolchain_id"], "python-unit-v1")
        self.assertEqual(entry["test_cmd"], "python -m unittest")

    def test_two_toolchains_with_same_language_are_not_conflated(self):
        r = self.run_entry("python-integration-v1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        entry = json.loads(r.stdout.strip())
        self.assertEqual(entry["toolchain_id"], "python-integration-v1")
        self.assertEqual(entry["test_cmd"], "python -m unittest tests.integration")

    def test_missing_identity_does_not_default_to_last_record(self):
        r = self.run_entry()
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_unknown_identity_does_not_fall_back_to_last_record(self):
        r = self.run_entry("python-missing-v1")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
