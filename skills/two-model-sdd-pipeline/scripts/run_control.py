"""Durable run state and exact-identity process cancellation."""
import argparse
import json
import os
import pathlib
import tempfile
import sys
import subprocess
import time
import contextlib
import threading

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import codex_process

_LOCKS={}
_LOCKS_GUARD=threading.Lock()


def _read(path):
    p=pathlib.Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"version":1,"processes":[],"status":"active"}


def _write(path,value):
    target=pathlib.Path(path); target.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix="run-control-",dir=str(target.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(value,stream,ensure_ascii=False,sort_keys=True,indent=2); stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        os.replace(name,target)
    finally:
        if os.path.exists(name): os.unlink(name)


@contextlib.contextmanager
def _locked(path):
    lock_path=str(path)+".lock"
    pathlib.Path(lock_path).parent.mkdir(parents=True,exist_ok=True)
    with _LOCKS_GUARD:
        thread_lock=_LOCKS.setdefault(lock_path,threading.RLock())
    thread_lock.acquire()
    stream=open(lock_path,"a+b")
    acquired=False
    try:
        if os.name=="nt":
            import msvcrt
            stream.seek(0)
            if not stream.read(1): stream.write(b"\0"); stream.flush()
            stream.seek(0); msvcrt.locking(stream.fileno(),msvcrt.LK_LOCK,1); acquired=True
        else:
            import fcntl
            fcntl.flock(stream.fileno(),fcntl.LOCK_EX); acquired=True
        yield
    finally:
        try:
            if acquired and os.name=="nt":
                import msvcrt
                stream.seek(0); msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            elif acquired:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
        finally:
            stream.close(); thread_lock.release()


def initialize(path,run_id,bindings=None):
    with _locked(path):
        state=_read(path)
        if state.get("run_id") not in (None,run_id): raise ValueError("run-control manifest belongs to another run")
        if state.get("run_id")==run_id:
            owned=[{k:p[k] for k in ("pid","start_identity")} for p in state["processes"] if p.get("status")=="active"]
            if owned:
                codex_process.stop_owned_processes(owned,1.0)
                for process in state["processes"]:
                    if process.get("status")=="active": process["status"]="interrupted"
        state.update(run_id=run_id,status="active",bindings=bindings or {},cancel_requested=False)
        _write(path,state); return state


def register_process(path,run_id,record):
    if not run_id or not isinstance(record,dict) or not isinstance(record.get("pid"),int) or not record.get("start_identity"):
        raise ValueError("run/process identity is incomplete")
    with _locked(path):
        state=_read(path)
        if state.get("run_id") not in (None,run_id): raise ValueError("run-control manifest belongs to another run")
        if state.get("cancel_requested"): raise ValueError("run cancellation requested")
        state.update(run_id=run_id,status="active")
        key=(record["pid"],record["start_identity"])
        if not any((p.get("pid"),p.get("start_identity"))==key for p in state["processes"]): state["processes"].append(dict(record,status="active"))
        _write(path,state)


def mark_process(path,run_id,record,status):
    if status not in ("completed","failed","interrupted"): raise ValueError("unsupported process terminal status")
    with _locked(path):
        state=_read(path)
        if state.get("run_id")!=run_id: raise ValueError("run-control manifest belongs to another run")
        for process in state.get("processes",[]):
            if (process.get("pid"),process.get("start_identity"))==(record.get("pid"),record.get("start_identity")):
                process["status"]=status
        if state.get("status") not in ("cancelling","interrupted"): state["status"]="active"
        _write(path,state)


def request_cancel(path,run_id,grace_seconds=1.0):
    with _locked(path):
        state=_read(path)
        if state.get("run_id")!=run_id: raise ValueError("run-control identity mismatch")
        state["cancel_requested"]=True; state["status"]="cancelling"; _write(path,state)
    active=[{k:p[k] for k in ("pid","start_identity")} for p in state["processes"] if p.get("status")=="active"]
    codex_process.stop_owned_processes(active,grace_seconds)
    with _locked(path):
        state=_read(path)
        if state.get("run_id")!=run_id: raise ValueError("run-control identity mismatch")
        for process in state["processes"]:
            if process.get("status")=="active": process["status"]="interrupted"
        state["status"]="interrupted"; _write(path,state)
        return state


def execute_owned(path,run_id,argv):
    if not argv: raise ValueError("owned command is required")
    child=subprocess.Popen(argv,creationflags=(getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0)|getattr(subprocess,"CREATE_NO_WINDOW",0)) if os.name=="nt" else 0,
        start_new_session=os.name!="nt")
    identity=codex_process._start_identity(child.pid)
    if not identity:
        child.terminate(); child.wait(timeout=3)
        raise RuntimeError("could not verify task-run process identity")
    record={"pid":child.pid,"start_identity":identity,"started":time.time(),"argv":argv}
    try: register_process(path,run_id,record)
    except Exception:
        codex_process.stop_owned_processes([{"pid":child.pid,"start_identity":identity}],1.0)
        raise
    try: result=child.wait()
    except KeyboardInterrupt:
        codex_process.stop_owned_processes([{"pid":child.pid,"start_identity":identity}],1.0)
        mark_process(path,run_id,record,"interrupted")
        return 130
    mark_process(path,run_id,record,"completed" if result==0 else "failed")
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(); subs=parser.add_subparsers(dest="action",required=True)
    cancel=subs.add_parser("cancel"); cancel.add_argument("--manifest",required=True); cancel.add_argument("--run-id",required=True)
    execute=subs.add_parser("exec"); execute.add_argument("--manifest",required=True); execute.add_argument("--run-id",required=True); execute.add_argument("command",nargs=argparse.REMAINDER)
    args=parser.parse_args(argv)
    try:
        if args.action=="cancel": print(json.dumps(request_cancel(args.manifest,args.run_id),sort_keys=True)); return 0
        command=args.command[1:] if args.command and args.command[0]=="--" else args.command
        return execute_owned(args.manifest,args.run_id,command)
    except Exception as exc: print("run-control: "+str(exc),file=sys.stderr); return 1


if __name__=="__main__": raise SystemExit(main())
