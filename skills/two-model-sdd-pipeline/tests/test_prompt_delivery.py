"""Task 2 RED: one recorded instruction package through every dispatch path.

Prepare-level matrix covers backends x roles x fresh/policy-change. Dispatch
level proves Codex delivery with fake executables (stdin/argv capture) and
the OpenCode shell path with a stubbed binary, plus failure cases where no
worker process may start.
"""

import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

try:
    import prepare_prompt
except ImportError:
    prepare_prompt = None

ROLES = ("operator", "reviewer", "director")
BACKENDS = ("codex", "opencode")
ROLE_CORE = {
    "operator": "Operator core",
    "reviewer": "Reviewer core",
    "director": "Director core",
}


def context(**overrides):
    value = {
        "role_protocol": "ROLE-PROTOCOL-7",
        "authority": "AUTHORITY-ORDER-3",
        "task_acceptance": "TASK-ACCEPTANCE-11",
        "output_contract": "OUTPUT-CONTRACT-5",
        "budget_chars": 200000,
    }
    value.update(overrides)
    return value


def skill_bundle(role, content="DOMAIN-SKILL-CONTENT-9"):
    return {"role": role, "skills": [{
        "id": "domain-test-skill",
        "revision": "sha256:domain-r1",
        "source_sha256": "sha256:domain-r1",
        "content": content,
    }]}


def policy_for(backend):
    return "BACKEND-POLICY-%s-42" % backend.upper()


def require_prepare(testcase):
    testcase.assertIsNotNone(
        prepare_prompt, "prepare_prompt.py provides the shared boundary")


FAKE_CODEX = """import json, os, sys
raw = sys.stdin.buffer.read()
open(os.environ["CAPTURE_STDIN"], "wb").write(raw)
open(os.environ["CAPTURE_ARGV"], "w", encoding="utf-8").write(
    json.dumps(sys.argv[1:]))
args = sys.argv[1:]
out = args[args.index("--output-last-message") + 1] if "--output-last-message" in args else None
if out:
    data = open(os.environ["FINAL_JSON"], "rb").read()
    open(out, "wb").write(data)
thread = os.environ.get("THREAD_ID", "thread-fake-1")
print(json.dumps({"type": "thread.started", "thread_id": thread}))
print(json.dumps({"type": "turn.completed",
                  "usage": {"input_tokens": 1, "cached_input_tokens": 0,
                            "output_tokens": 1}}))
"""

FAKE_FINALS = {
    "operator": {"status": "DONE", "summary": "fake delivery",
                 "changed_files": [],
                 "red_evidence": {"path": "t.py", "runner": "unittest",
                                  "exit_code": 1},
                 "concerns": []},
    "reviewer": {"verdict": "APPROVED", "findings": [], "minors": [],
                 "summary": "fake delivery"},
    "director": {"mode": "correction", "decision": "propose",
                 "reason": "fake delivery",
                 "source_plan_hash": "a" * 64, "target_task": 1,
                 "proposal": {"summary": "fake"}},
}


class PrepareMatrixTests(unittest.TestCase):
    def test_package_delivers_every_channel_exactly_once(self):
        require_prepare(self)
        for backend in BACKENDS:
            for role in ROLES:
                with self.subTest(backend=backend, role=role):
                    out = pathlib.Path(
                        tempfile.mkdtemp(prefix="prepare-matrix-"))
                    package = prepare_prompt.prepare(
                        role, context(), skill_bundle(role),
                        policy_for(backend), out)
                    self.assertEqual(len(package["prompt_hash"]), 64)
                    int(package["prompt_hash"], 16)
                    self.assertEqual(len(package["instruction_envelope_hash"]), 64)
                    int(package["instruction_envelope_hash"], 16)
                    prompt = pathlib.Path(package["prompt_path"])
                    self.assertEqual(
                        hashlib.sha256(prompt.read_bytes()).hexdigest(),
                        package["prompt_hash"])
                    text = prompt.read_text(encoding="utf-8")
                    for marker in (ROLE_CORE[role], "TASK-ACCEPTANCE-11",
                                   policy_for(backend),
                                   "DOMAIN-SKILL-CONTENT-9",
                                   "OUTPUT-CONTRACT-5"):
                        self.assertEqual(
                            1, text.count(marker),
                            "%r must be delivered exactly once" % marker)
                    envelope = json.loads(pathlib.Path(
                        package["prompt_path"]).parent.joinpath(
                            "envelope.json").read_text(encoding="utf-8"))
                    self.assertEqual(
                        envelope["instruction_envelope_hash"],
                        package["instruction_envelope_hash"])
                    names = [c["name"] for c in envelope["channels"]]
                    for channel in ("adapted_role_core", "backend_policy",
                                    "domain_skills", "task_acceptance",
                                    "output_contract"):
                        self.assertIn(channel, names)

    def test_package_identity_is_stable_and_policy_bound(self):
        require_prepare(self)
        first_dir = pathlib.Path(tempfile.mkdtemp(prefix="prepare-stable-a-"))
        second_dir = pathlib.Path(tempfile.mkdtemp(prefix="prepare-stable-b-"))
        first = prepare_prompt.prepare(
            "operator", context(), skill_bundle("operator"),
            policy_for("codex"), first_dir)
        second = prepare_prompt.prepare(
            "operator", context(), skill_bundle("operator"),
            policy_for("codex"), second_dir)
        self.assertEqual(first["instruction_envelope_hash"],
                         second["instruction_envelope_hash"])
        changed = prepare_prompt.prepare(
            "operator", context(), skill_bundle("operator"),
            policy_for("opencode"), second_dir)
        self.assertNotEqual(first["instruction_envelope_hash"],
                            changed["instruction_envelope_hash"])


class PrepareFailureTests(unittest.TestCase):
    def test_missing_context_conflicts_and_overflow_fail_before_writes(self):
        require_prepare(self)
        bad_context = context()
        del bad_context["task_acceptance"]
        conflict_skills = skill_bundle("operator")
        conflict_skills["skills"].append({
            "id": "domain-test-skill", "revision": "sha256:domain-r2",
            "source_sha256": "sha256:domain-r2", "content": "OTHER"})
        cases = [
            ("operator", bad_context, skill_bundle("operator"),
             policy_for("codex")),
            ("operator", context(), conflict_skills, policy_for("codex")),
            ("operator", context(budget_chars=8), skill_bundle("operator"),
             policy_for("codex")),
        ]
        for role, ctx, skills, policy in cases:
            with self.subTest(policy=policy):
                out = pathlib.Path(tempfile.mkdtemp(prefix="prepare-fail-"))
                with self.assertRaises(ValueError):
                    prepare_prompt.prepare(role, ctx, skills, policy, out)
                self.assertEqual(
                    [], list(out.iterdir()),
                    "invalid preparation must not start any worker artifact")


def _load_module(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git_repo(root):
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "T"],
                   check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@x.invalid"],
                   check=True)
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"],
                   check=True)
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()


def _codex_runtime(manifest_roles, executable, session_dir, tmp,
                   developer_instructions="instructions"):
    capabilities = {k: True for k in (
        "hooks_enabled", "hooks_trusted", "sandbox_enforced",
        "bash_hook_covered", "apply_patch_hook_covered")}
    capabilities.update({k: [] for k in (
        "unhooked_mutating_tools", "managed_policy_conflicts",
        "inherited_instruction_conflicts")})
    return {
        "manifest": {"backend": "codex", "version": "test",
                     "roles": manifest_roles},
        "capabilities": capabilities,
        "developer_instructions": developer_instructions,
        "executable": executable,
        "env": {},
        "session_dir": str(session_dir),
        "attempt_root": str(tmp / "attempts"),
    }


def _codex_request(role, worktree, prompt_path, prompt_hash, tmp, head,
                   plan_revision):
    evidence = tmp / "evidence"
    return {
        "version": 1, "backend": "codex", "run_id": "run-1",
        "dispatch_id": "d1", "task_id": 1, "task_family": 1,
        "episode_id": "e1", "role": role, "repository_id": "repo",
        "worktree": str(worktree), "plan_revision": plan_revision,
        "base_commit": head, "config_hash": "c" * 64,
        "prompt_hash": prompt_hash, "requested_model": "m",
        "requested_effort": "medium",
        "evidence_paths": {
            "request_path": str(evidence / "request.json"),
            "prompt_path": str(prompt_path),
            "events_path": str(evidence / "events.jsonl"),
            "stderr_path": str(evidence / "stderr.log"),
            "final_path": str(evidence / "final.json"),
            "result_path": str(evidence / "result.json"),
        },
    }


def _manifest_roles():
    return {role: {"model": "m",
                   "settings": {"model_reasoning_effort": "medium"},
                   "policy": ("workspace-write" if role == "operator"
                              else "read-only")}
            for role in ROLES}


class CodexDispatchDeliveryTests(unittest.TestCase):
    def _dispatch(self, role, resume_session=None, tamper=False):
        require_prepare(self)
        codex_dispatch = _load_module("codex_dispatch")
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="codex-delivery-"))
        head = _git_repo(tmp / "repo")
        out = tmp / "package"
        out.mkdir()
        package = prepare_prompt.prepare(
            role, context(), skill_bundle(role), policy_for("codex"), out)
        plan_path = out / "plan.json"
        plan_path.write_text(json.dumps(
            {"tasks": [{"id": 1, "touches": [], "verification": {}}]}),
            encoding="utf-8")
        plan_revision = hashlib.sha256(
            plan_path.read_bytes()).hexdigest()
        prompt_path = pathlib.Path(package["prompt_path"])
        if tamper:
            with prompt_path.open("ab") as handle:
                handle.write(b"tampered")
        fake = tmp / "fake-codex.py"
        fake.write_text(FAKE_CODEX, encoding="utf-8")
        marker = tmp / "started.marker"
        starter = tmp / "starter.py"
        starter.write_text(
            "import pathlib, sys\n"
            "pathlib.Path(sys.argv[1]).write_text('started', encoding='utf-8')\n"
            "import runpy\nrunpy.run_path(sys.argv[2], run_name='__main__')\n",
            encoding="utf-8")
        final = tmp / "final.json"
        final.write_text(json.dumps(FAKE_FINALS[role]), encoding="utf-8")
        thread = resume_session or "thread-fake-1"
        env = {"CAPTURE_STDIN": str(tmp / "stdin.bin"),
               "CAPTURE_ARGV": str(tmp / "argv.json"),
               "FINAL_JSON": str(final), "THREAD_ID": thread,
               "START_MARKER": str(marker)}
        executable = [sys.executable, str(starter), str(marker),
                      str(fake)]
        session_dir = tmp / "sessions"
        session_dir.mkdir()
        runtime = _codex_runtime(_manifest_roles(), executable,
                                 session_dir, tmp)
        runtime["env"] = env
        if resume_session:
            sessions = _load_module("codex_sessions")
            identity = {
                "backend": "codex", "run_id": "run-1", "task_id": 1,
                "task_family": 1, "role": role, "worktree": str(tmp / "repo"),
                "requested_model": "m", "requested_effort": "medium",
                "config_hash": "c" * 64,
                "session_dir": str(session_dir),
            }
            sessions.store_session(
                identity, {"session_id": resume_session,
                           "status": "completed"})
            runtime["resume"] = True
            runtime["resume_session_id"] = resume_session
        request = _codex_request(role, tmp / "repo", prompt_path,
                                 package["prompt_hash"], tmp, head,
                                 plan_revision)
        return codex_dispatch, request, runtime, tmp, package

    def test_fresh_operator_delivery_matches_prepared_bytes(self):
        module, request, runtime, tmp, package = self._dispatch("operator")
        result = module.run_dispatch(request, runtime)
        self.assertEqual(result["terminal_status"], "completed")
        prepared = pathlib.Path(package["prompt_path"]).read_bytes()
        role_instruction = (
            SCRIPTS.parent / "codex" / "operator.md").read_text(
                encoding="utf-8").rstrip() + "\n\n"
        captured = (tmp / "stdin.bin").read_bytes()
        self.assertEqual(captured, role_instruction.encode("utf-8") + prepared)
        attempt_dirs = list((tmp / "attempts").iterdir())
        self.assertEqual(1, len(attempt_dirs))
        envelope = json.loads(
            (attempt_dirs[0] / "envelope.json").read_text(encoding="utf-8"))
        by_name = {c["name"]: c for c in envelope["channels"]}
        self.assertEqual(
            by_name["prepared_prompt"]["sha256"], package["prompt_hash"])
        self.assertEqual(
            by_name["role_instruction"]["sha256"],
            hashlib.sha256(role_instruction.encode("utf-8")).hexdigest())
        self.assertIsNone(envelope["resume"])
        self.assertEqual(len(envelope["instruction_envelope_hash"]), 64)

    def test_resume_operator_records_resume_delta(self):
        module, request, runtime, tmp, package = self._dispatch(
            "operator", resume_session="sess-resume-7")
        result = module.run_dispatch(request, runtime)
        self.assertEqual(result["terminal_status"], "completed")
        self.assertEqual(result["resumed_from"], "sess-resume-7")
        attempt_dirs = list((tmp / "attempts").iterdir())
        envelope = json.loads(
            (attempt_dirs[0] / "envelope.json").read_text(encoding="utf-8"))
        self.assertEqual(
            envelope["resume"],
            {"resumed_from": "sess-resume-7",
             "package_sha256": package["prompt_hash"]})

    def test_tampered_prompt_fails_before_worker_start(self):
        module, request, runtime, tmp, package = self._dispatch(
            "operator", tamper=True)
        with self.assertRaises(ValueError):
            module.run_dispatch(request, runtime)
        self.assertFalse((tmp / "started.marker").exists())
        self.assertFalse((tmp / "stdin.bin").exists())


def _bash():
    bash = shutil.which("bash")
    if os.name == "nt":
        git_bash = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
        bash = str(git_bash) if git_bash.exists() else bash
    return bash


OPENCODE_STUB = """echo "$*" >> "${STUB_ARGV:?}"
echo '{"type":"header","sessionID":"sess-stub-9"}'
echo '{"type":"text","part":{"type":"text","text":"stub reply"}}'
exit 0
"""


class OpencodeShellDeliveryTests(unittest.TestCase):
    def _run_shell(self, resume_session=None):
        require_prepare(self)
        bash = _bash()
        if not bash:
            self.skipTest("Bash is required for shell dispatch delivery")
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="opencode-delivery-"))
        out = tmp / "package"
        out.mkdir()
        package = prepare_prompt.prepare(
            "operator", context(), skill_bundle("operator"),
            policy_for("opencode"), out)
        stub = tmp / "opencode"
        stub.write_text("#!/usr/bin/env bash\n" + OPENCODE_STUB,
                        encoding="utf-8")
        argv_log = tmp / "argv.log"
        log = tmp / "task-1-coder.log"
        env = dict(os.environ, OPENCODE_BIN=str(stub),
                   STUB_ARGV=str(argv_log))
        args = [bash, str(SCRIPTS / "dispatch-opencode"),
                "--agent", "two-model-coder", "--task", "1",
                "--prompt-file", package["prompt_path"], "--log", str(log)]
        if resume_session:
            args += ["--continue", resume_session]
        result = subprocess.run(args, cwd=str(tmp), env=env,
                                capture_output=True, text=True)
        return result, tmp, package, argv_log, log

    def test_shell_delivery_uses_prepared_bytes_and_records_prefix(self):
        result, tmp, package, argv_log, log = self._run_shell()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        argv = argv_log.read_text(encoding="utf-8")
        self.assertIn(package["prompt_path"], argv)
        prepared = pathlib.Path(package["prompt_path"]).read_bytes()
        self.assertEqual(hashlib.sha256(prepared).hexdigest(),
                         package["prompt_hash"])
        envelope = json.loads(pathlib.Path(str(log) + ".envelope.json").read_text(encoding="utf-8"))
        by_name = {c["name"]: c for c in envelope["channels"]}
        self.assertEqual(by_name["prompt_file"]["sha256"],
                         package["prompt_hash"])
        self.assertEqual(
            by_name["dispatch_prefix"]["sha256"],
            hashlib.sha256(("You are dispatched by Script CEO. Read the "
                            "attached file and execute per its instructions. "
                            "Report concisely.").encode()).hexdigest())
        self.assertEqual(envelope["session"], "sess-stub-9")

    def test_shell_resume_records_continued_session(self):
        result, tmp, package, argv_log, log = self._run_shell(
            resume_session="sess-prior-3")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        argv = argv_log.read_text(encoding="utf-8")
        self.assertIn("sess-prior-3", argv)
        envelope = json.loads(pathlib.Path(str(log) + ".envelope.json").read_text(encoding="utf-8"))
        self.assertEqual(envelope["continued_from"], "sess-prior-3")
        self.assertEqual(envelope["session"], "sess-stub-9")


if __name__ == "__main__":
    unittest.main()
