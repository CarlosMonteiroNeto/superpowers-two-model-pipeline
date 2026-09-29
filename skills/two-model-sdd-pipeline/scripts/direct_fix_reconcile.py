"""Record direct-fix intent and consume a supervisor's recovered result."""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time


def _intent_path(workspace, task):
    return pathlib.Path(workspace) / f"task-{task}-direct-fix-intent.json"


def start_intent(workspace, task, prompt, candidate):
    ws = pathlib.Path(workspace)
    identity_path = ws / ".pipeline-identity.json"
    run_id = json.loads(identity_path.read_text(encoding="utf-8"))["run_id"] if identity_path.exists() else "legacy"
    prompt_hash = hashlib.sha256(pathlib.Path(prompt).read_bytes()).hexdigest()
    attempt_id = hashlib.sha256(f"{run_id}\0{task}\0{candidate}\0{prompt_hash}\0{time.time_ns()}".encode()).hexdigest()[:32]
    record = {"run_id": run_id, "task_id": str(task), "candidate_commit": candidate,
              "prompt_sha256": prompt_hash, "attempt_id": attempt_id, "status": "intent"}
    path = _intent_path(ws, task)
    fd, tmp = tempfile.mkstemp(prefix="direct-fix-intent-", dir=str(ws))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return attempt_id


def reconcile(workspace, task, disposition_path):
    ws = pathlib.Path(workspace)
    intent = json.loads(_intent_path(ws, task).read_text(encoding="utf-8"))
    prompt = ws / f"task-{task}-direct-fix.md"
    if hashlib.sha256(prompt.read_bytes()).hexdigest() != intent.get("prompt_sha256"):
        raise ValueError("direct correction prompt changed after intent")
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ws), text=True).strip()
    if current != intent.get("candidate_commit"):
        raise ValueError("candidate changed before direct correction reconciliation")
    disposition = json.loads(pathlib.Path(disposition_path).read_text(encoding="utf-8"))
    for key in ("run_id", "task_id", "candidate_commit", "prompt_sha256", "attempt_id"):
        if str(disposition.get(key)) != str(intent.get(key)):
            raise ValueError(f"supervisor disposition has mismatched {key}")
    if (disposition.get("issuer") != "supervisor" or not disposition.get("decision_id") or
            disposition.get("outcome") != "completed"):
        raise ValueError("a completed supervisor disposition is required")
    evidence = pathlib.Path(disposition.get("evidence_path", ""))
    if not evidence.is_file() or not evidence.stat().st_size:
        raise ValueError("recovered operator evidence is missing")
    if hashlib.sha256(evidence.read_bytes()).hexdigest() != disposition.get("evidence_sha256"):
        raise ValueError("recovered operator evidence hash mismatch")
    ledger = ws / "ledger.jsonl"
    events = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    started = any(e.get("type") == "direct_correction_started" and
                  str(e.get("task")) == str(task) and e.get("attempt_id") == intent["attempt_id"] for e in events)
    if not started:
        raise ValueError("no matching direct correction intent in ledger")
    append = pathlib.Path(__file__).with_name("ledger-append")
    def add(kind, summary):
        subprocess.run(["bash", str(append), str(ledger), kind, str(task), summary,
                        "attempt_id=" + intent["attempt_id"],
                        "candidate=" + intent["candidate_commit"],
                        "decision_id=" + disposition["decision_id"]], check=True)
    if not any(e.get("type") == "direct_correction_reconciled" and
               e.get("attempt_id") == intent["attempt_id"] for e in events):
        add("direct_correction_reconciled", "supervisor accepted recovered operator result")
    # Dispatch boundary is last: a crash between events stays in reconciliation.
    if not any(e.get("type") == "direct_correction_dispatched" and
               e.get("attempt_id") == intent["attempt_id"] for e in events):
        add("red_check", "retaining operator-owned RED after recovered correction")
        add("direct_correction_dispatched", "reconciled operator result without redispatch")


if __name__ == "__main__":
    try:
        if len(sys.argv) == 6 and sys.argv[1] == "intent":
            print(start_intent(*sys.argv[2:]))
        elif len(sys.argv) == 5 and sys.argv[1] == "reconcile":
            reconcile(*sys.argv[2:])
        else:
            raise ValueError("usage: direct_fix_reconcile.py intent WORKSPACE TASK PROMPT CANDIDATE | reconcile WORKSPACE TASK DISPOSITION.json")
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"direct fix reconciliation: {exc}", file=sys.stderr)
        raise SystemExit(4)
