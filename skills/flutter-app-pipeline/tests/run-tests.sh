#!/usr/bin/env bash
# Run the flutter-app-pipeline deterministic-script test suite.
# Usage: run-tests.sh   (set PYTHON to override the interpreter)
set -euo pipefail

cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"
exec "$PYTHON" -m unittest discover -s . -p 'test_*.py' -v