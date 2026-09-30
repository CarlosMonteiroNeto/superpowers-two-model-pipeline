"""Refresh and commit tracked Graphify project-view files before final review."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
from typing import Sequence


SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
RULES_PATH = SCRIPT_DIR.parent / "toolchains" / "test-impact-rules.json"


def _run(repository: pathlib.Path, args: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *args], cwd=repository,
                            capture_output=True, text=True)
    if result.returncode:
        raise ValueError("git %s failed: %s" % (" ".join(args), result.stderr.strip()))
    return result


def refresh(repository: str | pathlib.Path, graphify_command: Sequence[str] = ("graphify",)) -> dict:
    root = pathlib.Path(repository).resolve()
    if not graphify_command or not all(isinstance(part, str) and part for part in graphify_command):
        raise ValueError("Graphify executable must be configured")
    policy = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    graphify_policy = policy.get("graphify", {})
    versions = graphify_policy.get("version_allowlist") if isinstance(graphify_policy, dict) else None
    if not isinstance(versions, list) or len(versions) != 1 or not isinstance(versions[0], str):
        raise ValueError("Graphify version policy is missing or ambiguous")

    tracked_status = _run(root, ["status", "--porcelain=v1", "--untracked-files=all", "--", "graphify-out"])
    if tracked_status.stdout.strip():
        raise ValueError("pre-existing changes under graphify-out/ must be resolved before publication refresh")
    staged = _run(root, ["diff", "--cached", "--name-only"])
    dirty_tracked = _run(root, ["status", "--porcelain=v1", "--untracked-files=no"])
    if staged.stdout.strip() or dirty_tracked.stdout.strip():
        raise ValueError("tracked worktree changes must be committed before Graphify publication refresh")
    untracked_before = set(_run(root, ["ls-files", "--others", "--exclude-standard"]).stdout.splitlines())

    version_result = subprocess.run([*graphify_command, "--version"], cwd=root,
                                     capture_output=True, text=True, timeout=30)
    match = re.search(r"\bgraphify\s+(\d+\.\d+\.\d+)\b",
                      version_result.stdout or "", re.IGNORECASE)
    if version_result.returncode or match is None or match.group(1) != versions[0]:
        raise ValueError("Graphify version is unavailable or outside the allowlist")
    update = subprocess.run([*graphify_command, "update"], cwd=root,
                            capture_output=True, text=True, timeout=600)
    if update.returncode:
        raise ValueError("Graphify update failed: %s" % (update.stderr.strip() or "nonzero exit"))

    after = _run(root, ["status", "--porcelain=v1", "--untracked-files=all", "--", "graphify-out"])
    if any(line.startswith("??") for line in after.stdout.splitlines()):
        raise ValueError("Graphify refresh created untracked graphify-out files; refusing partial publication")
    dirty_after = _run(root, ["status", "--porcelain=v1", "--untracked-files=no"])
    outside = [line[3:] for line in dirty_after.stdout.splitlines()
               if line[3:] and not line[3:].startswith("graphify-out/")]
    if outside:
        raise ValueError("Graphify refresh modified tracked files outside graphify-out/: " + repr(outside))
    untracked_after = set(_run(root, ["ls-files", "--others", "--exclude-standard"]).stdout.splitlines())
    new_untracked = sorted(untracked_after - untracked_before)
    if new_untracked:
        raise ValueError("Graphify refresh created untracked files: " + ", ".join(new_untracked[:10]))
    changed = [line for line in _run(root, ["diff", "--name-only", "--", "graphify-out"]).stdout.splitlines() if line]
    if not changed:
        return {"status": "unchanged", "head": _run(root, ["rev-parse", "HEAD"]).stdout.strip(),
                "files": []}
    if any(not path.startswith("graphify-out/") for path in changed):
        raise ValueError("Graphify refresh reported a path outside graphify-out/: " + repr(changed))
    _run(root, ["add", "--", *changed])
    staged_paths = [line for line in _run(root, ["diff", "--cached", "--name-only"]).stdout.splitlines() if line]
    if staged_paths != changed:
        raise ValueError("staged Graphify paths differ from the refreshed tracked files")
    commit = subprocess.run(["git", "commit", "-m", "chore: refresh Graphify project view"],
                            cwd=root, capture_output=True, text=True)
    if commit.returncode:
        raise ValueError("cannot commit the Graphify refresh: %s" % commit.stderr.strip())
    remaining = _run(root, ["status", "--porcelain=v1", "--untracked-files=all", "--", "graphify-out"])
    if remaining.stdout.strip():
        raise ValueError("Graphify output changed or remained dirty after the refresh commit")
    return {"status": "refreshed", "head": _run(root, ["rev-parse", "HEAD"]).stdout.strip(),
            "files": changed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--graphify-bin", default="graphify")
    args = parser.parse_args(argv)
    try:
        result = refresh(args.repository, (args.graphify_bin,))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print("graph publication: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
