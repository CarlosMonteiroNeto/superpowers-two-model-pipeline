"""Durable, candidate-bound claim for legacy OpenCode review dispatch."""
import hashlib
import json
import os
import pathlib
import sys
import tempfile


def claim_path(workspace, task, candidate):
    return pathlib.Path(workspace) / f"task-{task}-review-claim-{candidate}.json"


def _write(path, record):
    fd, tmp = tempfile.mkstemp(prefix="review-claim-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def claim(workspace, task, candidate, package):
    ws = pathlib.Path(workspace)
    package = pathlib.Path(package)
    if not package.is_file() or not package.stat().st_size:
        raise ValueError("review package missing")
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    path = claim_path(ws, task, candidate)
    record = {"task_id": str(task), "candidate_commit": candidate,
              "package_sha256": digest, "dispatch_id": hashlib.sha256(
                  f"{task}\0{candidate}\0{digest}".encode()).hexdigest()[:32],
              "status": "started"}
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        prior = json.loads(path.read_text(encoding="utf-8"))
        if any(prior.get(k) != record[k] for k in ("task_id", "candidate_commit", "package_sha256", "dispatch_id")):
            raise ValueError("review claim identity mismatch")
        return prior["status"]
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(record, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    return "claimed"


def complete(workspace, task, candidate):
    path = claim_path(workspace, task, candidate)
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("candidate_commit") != candidate or record.get("task_id") != str(task):
        raise ValueError("review claim identity mismatch")
    record["status"] = "completed"
    _write(path, record)


def reconcile(workspace, task, candidate, disposition_path):
    path = claim_path(workspace, task, candidate)
    record = json.loads(path.read_text(encoding="utf-8"))
    disposition = json.loads(pathlib.Path(disposition_path).read_text(encoding="utf-8"))
    for key in ("task_id", "candidate_commit", "package_sha256", "dispatch_id"):
        if str(record.get(key)) != str(disposition.get(key)):
            raise ValueError(f"review disposition has mismatched {key}")
    if (disposition.get("issuer") != "supervisor" or not disposition.get("decision_id") or
            disposition.get("outcome") != "completed"):
        raise ValueError("a completed supervisor disposition is required")
    evidence = pathlib.Path(disposition.get("evidence_path", ""))
    if not evidence.is_file() or not evidence.stat().st_size:
        raise ValueError("recovered reviewer evidence is missing")
    if hashlib.sha256(evidence.read_bytes()).hexdigest() != disposition.get("evidence_sha256"):
        raise ValueError("recovered reviewer evidence hash mismatch")
    complete(workspace, task, candidate)


if __name__ == "__main__":
    mode = sys.argv[1]
    try:
        if mode == "claim" and len(sys.argv) == 6:
            state = pathlib.Path(sys.argv[2]) / f"task-{sys.argv[3]}-review-state.json"
            path = claim_path(sys.argv[2], sys.argv[3], sys.argv[4])
            if not path.is_file():
                saved = json.loads(state.read_text(encoding="utf-8"))
                if saved.get("candidate_commit") != sys.argv[4]:
                    raise ValueError("stale candidate")
            result = claim(*sys.argv[2:])
            print(result)
        elif mode == "complete" and len(sys.argv) == 5:
            complete(*sys.argv[2:])
        elif mode == "reconcile" and len(sys.argv) == 6:
            reconcile(*sys.argv[2:])
        else:
            raise ValueError("invalid claim command")
    except (OSError, ValueError, KeyError) as exc:
        print(f"review claim: {exc}", file=sys.stderr)
        raise SystemExit(4)
