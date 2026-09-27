"""Explicit, idempotent branch publication without force push or auto-merge."""
import argparse
import json
import pathlib
import subprocess
import sys


def publish(repository, branch, target, policy, gh="gh"):
    if policy not in ("local", "pull_request"):
        raise ValueError("publication policy must be local or pull_request")
    if policy=="local":
        return {"status":"local_only","branch":branch,"target":target}
    subprocess.run(["git","push","-u","origin",branch],cwd=repository,check=True)
    found=subprocess.run([gh,"pr","list","--head",branch,"--base",target,"--json","number,url","--limit","1"],
        cwd=repository,capture_output=True,text=True,check=True)
    existing=json.loads(found.stdout or "[]")
    if existing:
        return {"status":"pull_request_exists","branch":branch,"target":target,
            "number":existing[0].get("number"),"url":existing[0].get("url")}
    created=subprocess.run([gh,"pr","create","--fill","--base",target],cwd=repository,capture_output=True,text=True,check=True)
    return {"status":"pull_request_created","branch":branch,"target":target,"url":created.stdout.strip()}


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--repository",required=True); parser.add_argument("--branch",required=True)
    parser.add_argument("--target",required=True); parser.add_argument("--policy",choices=("local","pull_request"),required=True)
    args=parser.parse_args(argv)
    try: print(json.dumps(publish(args.repository,args.branch,args.target,args.policy),sort_keys=True)); return 0
    except (OSError,subprocess.CalledProcessError,ValueError,json.JSONDecodeError) as exc:
        print("publication: "+str(exc),file=sys.stderr); return 1


if __name__=="__main__": raise SystemExit(main())
