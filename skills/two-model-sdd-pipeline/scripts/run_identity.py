"""Canonical repository, plan and run identity helpers."""
import hashlib
import os
import subprocess


def _canonical(path):
    return os.path.realpath(os.path.abspath(os.path.expanduser(path)))


def create_identity(repo_root: str, plan_path: str, run_id: str) -> dict:
    root = _canonical(repo_root)
    plan = _canonical(plan_path if os.path.isabs(plan_path) else os.path.join(root, plan_path))
    try:
        relative = os.path.relpath(plan, root)
    except ValueError as exc:
        raise ValueError("plan must be inside its repository") from exc
    if relative == os.pardir or relative.startswith(os.pardir + os.sep):
        raise ValueError("plan must be inside its repository")
    rel = relative.replace(os.sep, "/")
    if os.name == "nt":
        rel = rel.casefold()
    if not run_id or not isinstance(run_id, str) or len(run_id) > 128 or any(ord(ch) < 32 for ch in run_id):
        raise ValueError("run_id must be a non-empty string")
    try:
        common = subprocess.check_output(["git", "rev-parse", "--git-common-dir"], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
        common = _canonical(common if os.path.isabs(common) else os.path.join(root, common))
    except (OSError, subprocess.CalledProcessError):
        common = root
    repo_key = common.casefold() if os.name == "nt" else common
    repo_id = hashlib.sha256(repo_key.encode("utf-8")).hexdigest()[:20]
    identity_payload = "\0".join((repo_id, rel, run_id))
    return {
        "repository_id": repo_id,
        "repository_root": root,
        "git_common_dir": common,
        "plan_path": rel,
        "run_id": run_id,
        "identity": hashlib.sha256(identity_payload.encode("utf-8")).hexdigest(),
        "workspace_key": hashlib.sha256(identity_payload.encode("utf-8")).hexdigest()[:20],
    }
