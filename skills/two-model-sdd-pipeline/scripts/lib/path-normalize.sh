#!/usr/bin/env bash
# Normalize native Windows paths before POSIX tools consume them under MSYS.

normalize_posix_path() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -u "$1"
  else
    printf '%s\n' "$1"
  fi
}
