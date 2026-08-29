#!/usr/bin/env python3
"""Build a Graphify graph for a downloaded pub package BEFORE any LLM reads it.

Resolves the package's real directory from the project's package_config.json,
then runs `graphify update` on it so the LLM queries the interface instead of
reading raw source. Uses the real CLI form (`graphify update <pkg_dir>`) - the
old `graphify <pkg_dir> --out <dir>` form was rejected by the real CLI.

Usage:
  graphify-package PACKAGE [--config PACKAGE_CONFIG] [--root DIR]

PACKAGE_CONFIG defaults to `.dart_tool/package_config.json` under ROOT (or CWD).
GRAPHIFY_BIN env var overrides the graphify command (tests).
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.parse

GRAPHIFY_BIN = os.environ.get("GRAPHIFY_BIN", "graphify")


def resolve_package_dir(config, name, base_dir=None):
    """Pure: map a package name to its on-disk directory from a
    package_config.json dict. Raises KeyError when the package is absent."""
    for entry in config.get("packages", []):
        if entry.get("name") == name:
            root = entry.get("rootUri", "")
            if root.startswith("file://"):
                root = urllib.parse.urlparse(root).path
                if os.name == "nt" and len(root) > 2 and root[2] == ":":
                    root = root[1:]
            if not os.path.isabs(root) and base_dir:
                root = os.path.join(base_dir, root)
            return os.path.normpath(root)
    raise KeyError("package not found in package_config.json: {}".format(name))


def load_package_config(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Graphify a downloaded pub package")
    parser.add_argument("package")
    parser.add_argument("--config", default=None)
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)

    config_path = args.config or os.path.join(args.root, ".dart_tool", "package_config.json")
    config = load_package_config(config_path)
    pkg_dir = resolve_package_dir(config, args.package, base_dir=os.path.dirname(config_path) if args.config else None)

    subprocess.run(
        [GRAPHIFY_BIN, "update", pkg_dir],
        check=True,
    )
    print("GRAPHIFY-PACKAGE: graph built for {} at {}".format(args.package, pkg_dir))


if __name__ == "__main__":
    main()