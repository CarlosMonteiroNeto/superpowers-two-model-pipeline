"""Per-task toolchain wiring (rec #3).

A mono-repo with two ecosystems (say Flutter + Firebase functions) used to be
unresolvable by resolve-toolchain: two markers meant "ambiguous, ask once" and
the single branch-level gate entry then ruled every task. Now a branch may
preinstall one gate entry per detected marker (resolve-toolchain --all) and the
per-task scripts pick the entry for the WHAT the task actually touches
(scripts/task-lang) or a named language (scripts/gate-entry-for) instead of
whatever happened to be appended last.
"""

import json
import os
import pathlib
import shutil
import subprocess
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


def gate_entry(lang, test_cmd, analyze_cmd):
    return {"ts": "x", "type": "gate", "task": "-",
            "summary": "preinstalled: " + lang,
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
    def test_all_preinstalls_one_gate_entry_per_marker(self):
        (self.repo / "go.mod").write_text("module test\n", encoding="utf-8")
        (self.repo / "package.json").write_text("{}\n", encoding="utf-8")
        r = run_script("resolve-toolchain", ["--all", str(self.ws), str(self.repo)],
                       cwd=self._tmp, env_extra={})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        langs = ledger_langs(self.ledger_path())
        self.assertEqual(sorted(langs), ["go", "node"])
        self.assertEqual(langs, sorted(langs), r.stdout + r.stderr)

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
                {"id": 1, "title": "math", "touches": ["lib/go/math.go"],
                 "depends_on": []},
                {"id": 2, "title": "calc", "touches": ["src/calc.js"],
                 "depends_on": []},
                {"id": 3, "title": "docs", "touches": ["README.md"],
                 "depends_on": []},
                {"id": 4, "title": "no-touch", "touches": [], "depends_on": []},
            ],
        }
        (self.ws / "plan.json").write_text(json.dumps(self.plan), encoding="utf-8")
        self.write_ledger([gate_entry("go", "go test ./...", "go vet ./...")])

    def run_lang(self, task, root):
        return run_script("task-lang", [str(self.ws), task, root],
                          cwd=self._tmp, env_extra={})

    def test_resolves_lang_from_ancestor_marker(self):
        # go.mod at the root governs lib/go/math.go.
        (self.repo / "go.mod").write_text("module test\n", encoding="utf-8")
        r = self.run_lang("1", str(self.repo))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), "go")

    def test_closest_ancestor_marker_wins(self):
        # package.json sits closer to calc.js than the root go.mod.
        (self.repo / "go.mod").write_text("module test\n", encoding="utf-8")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "package.json").write_text("{}\n", encoding="utf-8")
        r = self.run_lang("2", str(self.repo))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), "node")

    def test_falls_back_to_branch_gate_when_no_marker(self):
        r = self.run_lang("3", str(self.repo))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), "go")

    def test_falls_back_to_branch_gate_when_no_touches(self):
        r = self.run_lang("4", str(self.repo))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), "go")

    def test_missing_plan_falls_back_to_branch_gate(self):
        (self.ws / "plan.json").unlink()
        r = self.run_lang("1", str(self.repo))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), "go")


class TestGateEntryFor(ToolchainWiringBase):
    def setUp(self):
        super().setUp()
        self.write_ledger([
            gate_entry("go", "go test ./...", "go vet ./..."),
            gate_entry("node", "npm test", "npx eslint ."),
        ])

    def run_entry(self, *args):
        return run_script("gate-entry-for", [str(self.ws)] + list(args),
                          cwd=self._tmp, env_extra={})

    def test_returns_first_entry_matching_lang(self):
        r = self.run_entry("go")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        entry = json.loads(r.stdout.strip())
        self.assertEqual(entry["lang"], "go")
        self.assertEqual(entry["test_cmd"], "go test ./...")

    def test_returns_last_entry_by_default(self):
        r = self.run_entry()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout.strip())["lang"], "node")

    def test_unknown_lang_falls_back_to_last_entry(self):
        r = self.run_entry("rust")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout.strip())["lang"], "node")


if __name__ == "__main__":
    unittest.main()