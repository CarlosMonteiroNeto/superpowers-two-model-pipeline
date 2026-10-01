"""Evidence-based dependency decisions and exclusive manifest write grants."""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from pathlib import PurePosixPath

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import state_lock


def evaluate(request, evidence):
    if not isinstance(request, dict) or not isinstance(evidence, dict):
        return {"status": "question", "reason": "request or dependency evidence is missing"}
    name, version = request.get("name"), request.get("version")
    if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
        return {"status": "block", "reason": "dependency name and version are required"}
    if re.search(r"todo|latest|\*", version, re.IGNORECASE):
        return {"status": "block", "reason": "floating or TODO dependency version is forbidden"}
    compatibility = evidence.get("compatible", evidence.get("compatibility"))
    if compatibility is False or compatibility == "incompatible" or (isinstance(compatibility, dict) and compatibility.get("status") == "incompatible"):
        return {"status": "block", "reason": "dependency is incompatible"}
    if evidence.get("conflict"):
        return {"status": "question", "reason": "dependency constraints conflict", "conflict": evidence["conflict"]}
    license_info = evidence.get("license")
    compatible = compatibility is True or compatibility == "compatible" or (isinstance(compatibility, dict) and compatibility.get("status") == "compatible")
    if not compatible or not isinstance(license_info, dict) or license_info.get("status") != "known" or not license_info.get("value"):
        return {"status": "question", "reason": "compatibility or license evidence is unknown"}
    return {"status": "allow", "dependency": {"name": name, "version": version,
            "license": license_info, "compatibility_evidence": evidence.get("compatibility_evidence")}}


def _resource_lock(path, owner):
    return state_lock.acquire_lock(path, owner)


def prepare(request, evidence, writer):
    """Run an approved manifest writer while holding the shared resource lock."""
    decision = evaluate(request, evidence)
    if decision["status"] != "allow":
        return decision
    write_paths = request.get("write_paths", ["pubspec.yaml", "pubspec.lock"])
    grants = request.get("granted_paths", [])
    valid_paths = lambda paths: isinstance(paths, list) and all(
        isinstance(path, str) and path and "\\" not in path and ":" not in path
        and not PurePosixPath(path).is_absolute()
        and all(part not in (".", "..") for part in PurePosixPath(path).parts)
        for path in paths
    )
    if not valid_paths(write_paths) or not write_paths or not valid_paths(grants) or not set(write_paths).issubset(set(grants)):
        return {"status": "blocked", "reason": "manifest and lockfile write grants are required"}
    lock_path, owner = request.get("lock_path"), request.get("owner")
    if not isinstance(lock_path, str) or not lock_path or not isinstance(owner, dict):
        return {"status": "blocked", "reason": "shared resource lock ownership is required"}
    try:
        with _resource_lock(lock_path, owner):
            result = writer()
    except (OSError, ValueError, RuntimeError) as error:
        return {"status": "question", "reason": "manifest resource is already claimed or cannot be locked", "detail": str(error)}
    return {"status": "written", "decision": decision, "result": result, "write_paths": write_paths}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Serialize a manifest-writing command under the shared resource lock")
    parser.add_argument("--lock", required=True)
    parser.add_argument("--repository-id", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    if not command:
        return 2
    owner = {"repository_id": args.repository_id, "branch": args.branch, "run_id": args.run_id}
    try:
        with _resource_lock(args.lock, owner):
            env = dict(os.environ, PIPELINE_DEPENDENCY_LOCK_HELD="1")
            executable = command
            if os.name == "nt" and Path(command[0]).suffix == "":
                executable = [env.get("BASH", "bash")] + command
            return subprocess.call(executable, env=env)
    except (OSError, ValueError, RuntimeError) as error:
        print("dependency-prepare: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
