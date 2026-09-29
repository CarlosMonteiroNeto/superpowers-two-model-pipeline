"""Serialize validated director proposals into the canonical plan."""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import datetime

SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import director_result
import plan_validation
import state_lock


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=str(root), check=True,
        capture_output=True, text=True).stdout.strip()


def _proposal_id(proposal):
    payload = json.dumps(proposal, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _lock_path(root, manifest):
    if manifest.get("lock_path"):
        return pathlib.Path(manifest["lock_path"])
    common = _git(root, "rev-parse", "--git-common-dir")
    common = pathlib.Path(common)
    if not common.is_absolute():
        common = root / common
    lock_hash = hashlib.sha256(os.path.normcase(str(common.resolve())).encode()).hexdigest()[:20]
    return common / "pipeline-locks" / (lock_hash + ".lock")


def _write_atomic(path, content):
    fd, name = tempfile.mkstemp(prefix="plan-transaction-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _append_ledger(manifest, proposal_id, record):
    ledger = manifest.get("ledger_path") or manifest.get("ledger")
    if not ledger:
        raise ValueError("canonical ledger path is required for plan transactions")
    ledger = pathlib.Path(ledger)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    events = []
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except ValueError as exc:
                raise ValueError("corrupt canonical ledger; refusing plan transaction") from exc
    if any(e.get("proposal_id") == proposal_id and e.get("type") == "plan_transaction" for e in events):
        return
    details=dict(record)
    event_type=details.pop("event","plan_transaction")
    task=details.pop("task",details.pop("target_task",None))
    if task is None:
        assigned=details.get("assigned_ids") or []
        task=assigned[0] if assigned else "-"
    summary=details.pop("summary", "{} committed".format(event_type.replace("_"," ")))
    entry = {"ts":datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z"),
        "type":event_type,"task":str(task),"summary":summary,
        "proposal_id":proposal_id,**details}
    with ledger.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _task(plan, task_id):
    matches = [t for t in plan.get("tasks", []) if t.get("id") == task_id]
    if len(matches) != 1:
        raise ValueError("target task is missing or ambiguous")
    return matches[0]


def _apply(plan, proposal, source_hash, manifest):
    mode = proposal["mode"]
    target_id = proposal["target_task"]
    target = _task(plan, target_id)
    body = proposal["proposal"]
    assigned = []
    if mode == "correction":
        if proposal["decision"] not in ("propose", "amend"):
            raise ValueError("unsupported correction decision")
        allowed_paths = set(manifest.get("scope_paths", [])) | set(target.get("touches", []))
        if not set(body["touches"]).issubset(allowed_paths):
            raise ValueError("corrective proposal touches exceed reviewed affected paths")
        next_id = max(t["id"] for t in plan["tasks"]) + 1
        child = {
            "id": next_id,
            "title": body["title"],
            "summary": body["summary"],
            "spec_refs": list(target["spec_refs"]),
            "touches": list(body["touches"]),
            "depends_on": list(target["depends_on"]),
            "acceptance": list(body["acceptance"]),
            "interfaces": json.loads(json.dumps(target.get("interfaces", {}))),
            "verification": json.loads(json.dumps(target.get("verification", {"new_test_files": []}))),
            "corrects": target_id,
        }
        plan["tasks"].append(child)
        assigned.append(next_id)
    elif mode == "arbitration":
        if proposal["decision"] != "amend":
            raise ValueError("arbitration requires an amend decision")
        changes = body["field_changes"]
        allowed = {"title", "summary", "acceptance", "touches"}
        if not set(changes).issubset(allowed):
            raise ValueError("arbitration contains unsupported task fields")
        target.update(json.loads(json.dumps(changes)))
        assigned.append(target_id)
    else:
        raise ValueError("unsupported proposal mode")
    return assigned


def apply_director_proposal(proposal: dict, manifest: dict) -> dict:
    """Apply one proposal under the repository's canonical plan lock.

    Replaying a proposal whose commit exists but ledger append was interrupted
    reconciles that commit into the ledger exactly once.
    """
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be an object")
    root = pathlib.Path(manifest.get("repository_root") or manifest.get("repo_root") or "").resolve()
    plan_path = pathlib.Path(manifest.get("plan_path") or "").resolve()
    if not root.is_dir() or not plan_path.is_file():
        raise ValueError("repository and canonical plan must exist")
    if os.path.commonpath((str(root), str(plan_path))) != str(root):
        raise ValueError("canonical plan must remain inside repository")
    if not manifest.get("run_id"):
        raise ValueError("run_id is required")
    proposal_id = _proposal_id(proposal)
    owner = {"repository_id": manifest.get("repository_id", str(root)),
        "branch": _git(root, "branch", "--show-current"), "run_id": manifest["run_id"]}
    lock = _lock_path(root, manifest)
    with state_lock.acquire_lock(str(lock), owner):
        dirty = subprocess.run(["git", "status", "--porcelain", "--", str(plan_path)],
            cwd=str(root), capture_output=True, text=True, check=True).stdout
        if dirty:
            raise ValueError("canonical plan has user changes; refusing director transaction")
        old_bytes = plan_path.read_bytes()
        old_hash = _sha(old_bytes)
        head_before = _git(root, "rev-parse", "HEAD")
        message = _git(root, "log", "-1", "--format=%B")
        if proposal_id in message and "plan-transaction:" in message:
            new_hash = _sha(old_bytes)
            assigned_match = __import__("re").search(r"assigned=([0-9,]+)", message)
            assigned = [int(value) for value in assigned_match.group(1).split(",")] if assigned_match else []
            _append_ledger(manifest, proposal_id, {"old_plan_hash": proposal.get("source_plan_hash"),
                "new_plan_hash": new_hash, "assigned_ids": assigned, "commit": head_before, "recovered": True})
            return {"assigned_ids": assigned, "old_plan_hash": proposal.get("source_plan_hash"),
                "new_plan_hash": new_hash, "commit": head_before, "recovered": True}
        expected = {key: proposal.get(key) for key in ("mode", "source_plan_hash", "target_task")}
        clean = director_result.validate_proposal(proposal, expected)
        if clean["source_plan_hash"] != old_hash:
            raise ValueError("stale source plan hash; director must re-evaluate current plan")
        plan = json.loads(old_bytes.decode("utf-8"))
        original_plan = json.loads(old_bytes.decode("utf-8"))
        assigned = _apply(plan, clean, old_hash, manifest)
        plan_validation.validate_plan(plan, str(root))
        if plan == original_plan:
            # A director may assess an exhausted cycle and conclude that the
            # approved task is still viable. Record the validated ruling
            # without fabricating a plan edit or an empty Git commit.
            record = {"old_plan_hash": old_hash, "new_plan_hash": old_hash,
                      "assigned_ids": assigned, "commit": head_before,
                      "recovered": False, "noop": True}
            _append_ledger(manifest, proposal_id, record)
            return {**record, "parent_commit": head_before}
        new_bytes = (json.dumps(plan, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        new_hash = _sha(new_bytes)
        _write_atomic(plan_path, new_bytes)
        try:
            _git(root, "add", "--", str(plan_path))
            metadata = "plan-transaction: {} old={} new={} assigned={}".format(
                proposal_id, old_hash, new_hash, ",".join(str(value) for value in assigned))
            commit = subprocess.run(["git", "commit", "-m", metadata, "--", str(plan_path)],
                cwd=str(root), capture_output=True, text=True)
            if commit.returncode:
                raise RuntimeError(commit.stderr.strip() or "plan transaction commit failed")
            head_after = _git(root, "rev-parse", "HEAD")
            record = {"old_plan_hash": old_hash, "new_plan_hash": new_hash,
                "assigned_ids": assigned, "commit": head_after, "recovered": False}
            _append_ledger(manifest, proposal_id, record)
            return {**record, "parent_commit": head_before}
        except Exception:
            current_head = _git(root, "rev-parse", "HEAD")
            if current_head == head_before:
                subprocess.run(["git", "reset", "-q", "HEAD", "--", str(plan_path)], cwd=str(root), check=False)
                plan_path.write_bytes(old_bytes)
            raise


def apply_closing_reopen(closing: dict, source_plan_hash: str, manifest: dict) -> dict:
    """Canonicalize closing follow-up tasks after a validated REOPEN ruling."""
    clean=director_result.dispatch_contract._validate_closing(closing)
    if clean["verdict"]!="REOPEN" or not clean["proposed_tasks"]:
        raise ValueError("REOPEN requires at least one validated proposed task")
    root=pathlib.Path(manifest.get("repository_root") or "").resolve()
    plan_path=pathlib.Path(manifest.get("plan_path") or "").resolve()
    if not root.is_dir() or not plan_path.is_file() or os.path.commonpath((str(root),str(plan_path)))!=str(root):
        raise ValueError("repository and canonical plan must exist inside repository")
    if not manifest.get("run_id"):
        raise ValueError("run_id is required")
    proposal_id=_proposal_id({"mode":"closing_reopen","source_plan_hash":source_plan_hash,"closing":clean})
    owner={"repository_id":manifest.get("repository_id",str(root)),"branch":_git(root,"branch","--show-current"),"run_id":manifest["run_id"]}
    with state_lock.acquire_lock(str(_lock_path(root,manifest)),owner):
        dirty=subprocess.run(["git","status","--porcelain","--",str(plan_path)],cwd=str(root),capture_output=True,text=True,check=True).stdout
        if dirty: raise ValueError("canonical plan has user changes; refusing closing transaction")
        old_bytes=plan_path.read_bytes(); old_hash=_sha(old_bytes); head_before=_git(root,"rev-parse","HEAD")
        message=_git(root,"log","-1","--format=%B")
        if proposal_id in message and "closing-transaction:" in message:
            ids_match=__import__("re").search(r"assigned=([0-9,]+)",message)
            ids=[int(v) for v in ids_match.group(1).split(",")] if ids_match else []
            record={"old_plan_hash":source_plan_hash,"new_plan_hash":old_hash,"assigned_ids":ids,"commit":head_before,"recovered":True}
            _append_ledger(manifest,proposal_id,{"event":"closing_reopen",**record})
            return record
        if old_hash!=source_plan_hash: raise ValueError("stale source plan hash; closing must be repeated")
        plan=json.loads(old_bytes.decode("utf-8")); tasks=plan.get("tasks",[])
        next_id=max(t["id"] for t in tasks)+1; assigned=[]
        spec_refs=sorted({ref for t in tasks for ref in t.get("spec_refs",[])})
        touches=sorted({p for f in clean["findings"] for p in f.get("affected_paths",[])})
        dependencies=[t["id"] for t in tasks]
        for proposed in clean["proposed_tasks"]:
            task={"id":next_id,"title":proposed["title"],"summary":proposed["summary"],
                "spec_refs":list(spec_refs),"touches":list(touches),"depends_on":list(dependencies),
                "acceptance":list(proposed["acceptance"]),"interfaces":{"produces":[],"consumes":[]},
                "verification":{"new_test_files":[]}}
            tasks.append(task); assigned.append(next_id); next_id+=1
        plan_validation.validate_plan(plan,str(root))
        new_bytes=(json.dumps(plan,ensure_ascii=False,indent=2)+"\n").encode("utf-8"); new_hash=_sha(new_bytes)
        _write_atomic(plan_path,new_bytes)
        try:
            _git(root,"add","--",str(plan_path))
            metadata="closing-transaction: {} old={} new={} assigned={}".format(proposal_id,old_hash,new_hash,",".join(map(str,assigned)))
            result=subprocess.run(["git","commit","-m",metadata,"--",str(plan_path)],cwd=str(root),capture_output=True,text=True)
            if result.returncode: raise RuntimeError(result.stderr.strip() or "closing transaction commit failed")
            commit=_git(root,"rev-parse","HEAD")
            record={"old_plan_hash":old_hash,"new_plan_hash":new_hash,"assigned_ids":assigned,"commit":commit,"recovered":False}
            _append_ledger(manifest,proposal_id,{"event":"closing_reopen",**record})
            return {**record,"parent_commit":head_before}
        except Exception:
            if _git(root,"rev-parse","HEAD")==head_before:
                subprocess.run(["git","reset","-q","HEAD","--",str(plan_path)],cwd=str(root),check=False)
                plan_path.write_bytes(old_bytes)
            raise
