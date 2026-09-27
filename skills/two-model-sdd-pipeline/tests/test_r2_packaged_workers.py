"""Controller-owned Task 6 package extraction and relocatability checks."""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"


def bash_path():
    if os.name == "nt":
        candidate = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
        return str(candidate) if candidate.exists() else shutil.which("bash")
    return shutil.which("bash")


class PackagedWorkersTests(unittest.TestCase):
    def test_delivery_archive_contains_relocatable_worker_runtime_references(self):
        bash = bash_path()
        if not bash:
            self.skipTest("Bash is required for package build")
        with tempfile.TemporaryDirectory(prefix="r26 package ") as temp:
            temp = pathlib.Path(temp)
            metadata = temp / "metadata"
            for skill in (ROOT / "skills").iterdir():
                if skill.is_dir():
                    target = metadata / "skills" / skill.name / "agents" / "openai.yaml"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("display_name: test\n", encoding="utf-8")
            artifact = temp / "workers.zip"
            result = subprocess.run([bash, str(ROOT / "scripts" / "package-codex-plugin.sh"),
                "--allow-dirty", "--metadata-source", str(metadata), "--output", str(artifact)],
                cwd=str(ROOT), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with zipfile.ZipFile(artifact) as archive:
                names = set(archive.namelist())
                required = {
                    "skills/two-model-sdd-pipeline/scripts/dispatch-codex",
                    "skills/two-model-sdd-pipeline/scripts/codex_dispatch.py",
                    "skills/two-model-sdd-pipeline/scripts/codex_policy.py",
                    "skills/two-model-sdd-pipeline/schemas/worker-request.schema.json",
                    "skills/two-model-sdd-pipeline/references/worker-runtime.md",
                    "skills/using-superpowers/references/codex-tools.md",
                }
                self.assertTrue(required.issubset(names), "missing packaged runtime files: " + repr(required - names))
                for name in required:
                    archive.read(name)

    def test_runtime_guide_states_verified_and_unknown_platform_support(self):
        guide = ROOT / "skills" / "two-model-sdd-pipeline" / "references" / "worker-runtime.md"
        self.assertTrue(guide.is_file(), "Task 6 requires the packaged worker runtime compatibility guide")
        text = guide.read_text(encoding="utf-8").casefold()
        for term in ("opencode", "codex", "windows", "linux", "verified", "unknown", "live"):
            self.assertIn(term, text)

