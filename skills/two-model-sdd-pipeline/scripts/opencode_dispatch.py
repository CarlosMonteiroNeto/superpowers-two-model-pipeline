"""Compatibility boundary for legacy OpenCode launcher."""
import os
import subprocess


def invoke(request):
    if not isinstance(request, dict) or request.get("backend") != "opencode":
        raise ValueError("explicit opencode request required")
    args = request.get("argv")
    if not isinstance(args, list) or not args:
        raise ValueError("OpenCode adapter requires explicit argv")
    return subprocess.run(args, cwd=request.get("worktree"), capture_output=True, text=True)
