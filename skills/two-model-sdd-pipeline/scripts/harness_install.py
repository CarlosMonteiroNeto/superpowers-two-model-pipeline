"""Immutable harness bundle installation and project binding (Round 1 Task 4).

An install root keeps versioned immutable bundles under
``.harness/bundles/<id>/``. Each bundle carries the complete harness:
runtime files, prompts, skills, canonical docs and license. A candidate
bundle is staged and validated before it is atomically selected through
``.harness/selected``; failed validation preserves the prior selection,
so pinned projects and active runs retain their old bundle.
Backend-specific entry points (``.harness/entrypoints/<backend>.sh``)
resolve the selected bundle through relocatable identities: they locate
their install root from their own path and never hard-code it.

Project bindings live in the project itself at
``.superpowers/harness.json`` (written by the ``harness-project``
script): version, bundle id, bundle hash, backend, a relocatable
backend configuration reference and policy references.
``resolve_bundle(project)`` verifies the pin against the install root
found through ``$SUPERPOWERS_HARNESS_ROOT``. A missing pin is a
diagnosed error, never a silent fallback to the newest installation.

Usage:
  harness_install.stage_bundle(install_root, bundle_id, source_dir)
  harness_install.select_bundle(install_root, bundle_id)
  harness_install.selected_bundle(install_root) -> str | None
  harness_install.resolve_bundle(project, install_root=None) -> dict
  harness_install.bundle_hash(bundle_dir) -> str
  harness_install.export_bundle(bundle_dir, output_path) -> str
Invalid inputs raise harness_install.HarnessInstallError (a ValueError).
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

BUNDLE_VERSION = 1
BACKENDS = ("codex", "opencode")

HARNESS_DIRNAME = ".harness"
BUNDLES_DIRNAME = "bundles"
STAGING_DIRNAME = "staging"
SELECTED_FILENAME = "selected"
ENTRYPOINTS_DIRNAME = "entrypoints"
MANIFEST_FILENAME = "manifest.json"

# Package the complete runtime and documentation trees. The manifest is built
# from the source inventory, so newly added scripts, skills and prompts cannot
# silently fall out of the bundle or its content hash.
PACKAGE_DIRS = (
    "agent",
    "assets",
    "docs",
    "hooks",
    "scripts",
    "skills",
    ".codex-plugin",
    ".opencode",
)
PACKAGE_FILES = (
    "LICENSE",
    "README.md",
    "RELEASE-NOTES.md",
    "roadmap.md",
)

# Core contract sentinels must be present even when an optional package tree
# is absent from a downstream distribution.
REQUIRED_BUNDLE_FILES = (
    "skills/two-model-sdd-pipeline/scripts/pipeline_config.py",
    "skills/two-model-sdd-pipeline/scripts/dispatch_contract.py",
    "skills/two-model-sdd-pipeline/schemas/runtime.schema.json",
    "agent/two-model-coder.md",
    "agent/two-model-reviewer.md",
    "agent/two-model-task-generator.md",
    "skills/brainstorming/SKILL.md",
    "skills/two-model-sdd-pipeline/SKILL.md",
    "README.md",
    "LICENSE",
)

BUNDLE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")

ENTRYPOINT_TEMPLATE = r"""#!/usr/bin/env bash
# %(backend)s backend entry point for the immutable harness bundle.
# It enrolls the current project on first use, then resolves that project's
# immutable pin. A new selected version is offered before a fresh run.
#
# Usage: %(backend)s.sh [--project DIR] [--install-root DIR] [PLAN_FILE ...]
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
project="${SUPERPOWERS_PROJECT_DIR:-$PWD}"
prepare_choice=""
runtime_args=()

# Keep compatibility with callers that supplied INSTALL_ROOT as the first
# argument before the project-aware entry point was introduced.
if [[ "${1:-}" != "" && -f "$1/.harness/selected" ]]; then
  root="$1"
  shift
fi

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --install-root)
      [[ "$#" -ge 2 ]] || { echo "usage: %(backend)s.sh [--project DIR] [--install-root DIR] [PLAN_FILE ...]" >&2; exit 2; }
      root="$2"
      shift 2
      ;;
    --project)
      [[ "$#" -ge 2 ]] || { echo "usage: %(backend)s.sh [--project DIR] [--install-root DIR] [PLAN_FILE ...]" >&2; exit 2; }
      project="$2"
      shift 2
      ;;
    --accept-upgrade|--keep-pinned|--resume)
      [[ -z "$prepare_choice" ]] || { echo "choose only one of --accept-upgrade, --keep-pinned and --resume" >&2; exit 2; }
      prepare_choice="$1"
      shift
      ;;
    *)
      runtime_args+=("$1")
      shift
      ;;
  esac
done

# Existing plan ledgers identify active runs. Always retain the project's
# current bundle for those runs, including after an interrupted invocation.
plan_path=""
for candidate in "${runtime_args[@]}"; do
  candidate_path="$candidate"
  if command -v cygpath >/dev/null 2>&1; then
    candidate_path="$(cygpath -u "$candidate" 2>/dev/null || printf '%%s' "$candidate")"
  fi
  if [[ "$candidate_path" != /* ]]; then
    # run-pipeline starts from the project root, so relative plan paths are
    # interpreted there even when the entry point was invoked elsewhere.
    candidate_path="$project/$candidate_path"
  fi
  if [[ -f "$candidate_path" ]]; then
    plan_path="$candidate_path"
    break
  fi
done
if [[ -n "$plan_path" ]]; then
  plan_slug="$(python3 -c 'import os,sys; n=os.path.basename(sys.argv[1]); print(os.path.splitext(n)[0])' "$plan_path")"
  if [[ -s "$project/.superpowers/two-model/$plan_slug/ledger.jsonl" ]]; then
    if [[ "$prepare_choice" == "--accept-upgrade" ]]; then
      echo "harness entry point: active plan ledger keeps its original bundle; ignoring --accept-upgrade" >&2
    fi
    prepare_choice="--resume"
  fi
fi

selected="$(cat "$root/.harness/selected")"
prepare="$root/.harness/bundles/$selected/skills/two-model-sdd-pipeline/scripts/harness-project"
[[ -f "$prepare" ]] || { echo "harness entry point: selected bundle is incomplete: $selected" >&2; exit 2; }

set +e
bundle_dir="$(python3 "$prepare" prepare --project "$project" --backend "%(backend)s" --install-root "$root" ${prepare_choice:+"$prepare_choice"})"
prepare_status=$?
set -e
if [[ "$prepare_status" -eq 4 && -z "$prepare_choice" ]]; then
  if [[ ! -t 0 ]]; then
    echo "harness entry point: upgrade decision required; rerun with --accept-upgrade or --keep-pinned" >&2
    exit 4
  fi
  printf 'Accept this harness upgrade? [y/N] '
  IFS= read -r answer || answer=""
  if [[ "$answer" =~ ^[Yy]([Ee][Ss])?$ ]]; then
    prepare_choice="--accept-upgrade"
  else
    prepare_choice="--keep-pinned"
  fi
  bundle_dir="$(python3 "$prepare" prepare --project "$project" --backend "%(backend)s" --install-root "$root" "$prepare_choice")"
  prepare_status=$?
fi
if [[ "$prepare_status" -ne 0 ]]; then
  exit "$prepare_status"
fi

if command -v cygpath >/dev/null 2>&1; then
  bundle_dir="$(cygpath -u "$bundle_dir")"
  root_for_python="$(cygpath -w "$root")"
else
  root_for_python="$root"
fi

if [[ "${#runtime_args[@]}" -gt 0 ]]; then
  if [[ "%(backend)s" != "opencode" ]]; then
    echo "Codex pipeline execution is not included in R1; use the resolved configuration bundle only" >&2
    exit 2
  fi
  export SUPERPOWERS_HARNESS_ROOT="$root_for_python"
  cd "$project"
  exec bash "$bundle_dir/skills/two-model-sdd-pipeline/scripts/run-pipeline" "${runtime_args[@]}"
fi

if command -v cygpath >/dev/null 2>&1; then
  bundle_dir="$(cygpath -w "$bundle_dir")"
fi
printf '%%s\n' "$bundle_dir"
"""


class HarnessInstallError(ValueError):
    """A bundle, selection, entry point or project pin is invalid."""


def _fail(message):
    raise HarnessInstallError(message)


def _harness_dir(install_root):
    return os.path.join(str(install_root), HARNESS_DIRNAME)


def _bundles_dir(install_root):
    return os.path.join(_harness_dir(install_root), BUNDLES_DIRNAME)


def _staging_dir(install_root, bundle_id):
    return os.path.join(
        _harness_dir(install_root), STAGING_DIRNAME, bundle_id)


def _bundle_dir(install_root, bundle_id):
    return os.path.join(_bundles_dir(install_root), bundle_id)


def _selected_path(install_root):
    return os.path.join(_harness_dir(install_root), SELECTED_FILENAME)


def _entrypoints_dir(install_root):
    return os.path.join(_harness_dir(install_root), ENTRYPOINTS_DIRNAME)


def _check_bundle_id(bundle_id):
    if not isinstance(bundle_id, str) or not BUNDLE_ID_PATTERN.match(
            bundle_id):
        _fail("invalid bundle id: %r" % (bundle_id,))


def _read_bytes(path):
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError as exc:
        _fail("cannot read %s: %s" % (path, exc))


def _bundle_inventory(directory):
    """Return every regular package file using normalized relative paths."""
    base = os.path.abspath(str(directory))
    paths = []
    for rel in PACKAGE_DIRS:
        package_root = os.path.join(base, rel)
        if not os.path.lexists(package_root):
            continue
        if os.path.islink(package_root) or not os.path.isdir(package_root):
            _fail("package root must be a directory: %s" % rel)
        for current, dirs, files in os.walk(package_root, followlinks=False):
            dirs[:] = sorted(
                name for name in dirs
                if name not in ("__pycache__", ".pytest_cache",
                                ".mypy_cache", ".ruff_cache"))
            for name in list(dirs):
                path = os.path.join(current, name)
                if os.path.islink(path):
                    _fail("package trees cannot contain symlink directories: "
                          "%s" % os.path.relpath(path, base))
            for name in sorted(files):
                if (name.endswith((".pyc", ".pyo"))
                        or name in (".DS_Store", "Thumbs.db")):
                    continue
                path = os.path.join(current, name)
                if os.path.islink(path) or not os.path.isfile(path):
                    _fail("package trees can contain regular files only: "
                          "%s" % os.path.relpath(path, base))
                paths.append(os.path.relpath(path, base).replace(os.sep, "/"))
    for rel in PACKAGE_FILES:
        path = os.path.join(base, rel)
        if os.path.lexists(path):
            if os.path.islink(path) or not os.path.isfile(path):
                _fail("package file must be a regular file: %s" % rel)
            paths.append(rel)
    return sorted(set(paths))


def _manifest_files(directory, manifest):
    """Verify the manifest lists exactly the package files on disk."""
    files = manifest.get("files")
    if (not isinstance(files, list)
            or any(not isinstance(item, str) for item in files)
            or files != sorted(set(files))):
        _fail("bundle manifest has an invalid file list")
    for rel in files:
        if (not rel or rel.startswith("/") or "\\" in rel
                or any(part in ("", ".", "..") for part in rel.split("/"))):
            _fail("bundle manifest contains an unsafe path: %r" % rel)
    actual = _bundle_inventory(directory)
    if files != actual:
        _fail("bundle manifest file list does not match package contents")
    return files


def _source_modes(source_dir, files):
    """Read package modes, preferring Git's portable executable metadata."""
    modes = {}
    for rel in files:
        path = os.path.join(str(source_dir), *rel.split("/"))
        modes[rel] = os.stat(path).st_mode & 0o777
    try:
        result = subprocess.run(
            ["git", "-C", str(source_dir), "ls-files", "--stage", "-z"],
            capture_output=True, check=False)
    except OSError:
        return modes
    if result.returncode != 0:
        return modes
    package_files = set(files)
    for record in result.stdout.split(b"\x00"):
        if not record or b"\t" not in record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        parts = metadata.split()
        if len(parts) != 3 or parts[2] != b"0":
            continue
        try:
            rel = raw_path.decode("utf-8")
            mode = int(parts[0], 8) & 0o777
        except (UnicodeDecodeError, ValueError):
            continue
        if rel in package_files:
            modes[rel] = mode
    return modes


def _apply_file_mode(path, mode):
    """Apply executable modes on POSIX and through Git Bash on Windows."""
    if os.name != "nt":
        os.chmod(path, mode)
        return
    if not (mode & 0o111):
        return
    chmod = shutil.which("chmod")
    if not chmod:
        _fail("cannot preserve executable mode for %s: chmod is unavailable"
              % path)
    try:
        result = subprocess.run(
            [chmod, "%o" % mode, str(path)],
            capture_output=True, text=True, check=False)
    except OSError as exc:
        _fail("cannot preserve executable mode for %s: %s" % (path, exc))
    if result.returncode != 0:
        _fail("cannot preserve executable mode for %s: %s"
              % (path, result.stderr.strip()))


def _manifest_modes(manifest, files):
    modes = manifest.get("modes")
    if not isinstance(modes, dict) or set(modes) != set(files):
        _fail("bundle manifest has an invalid file mode map")
    for rel, mode in modes.items():
        if (not isinstance(mode, int) or isinstance(mode, bool)
                or mode < 0 or mode > 0o777):
            _fail("bundle manifest has an invalid mode for %s" % rel)
    return modes


def _content_hash(directory, files=None, modes=None):
    """Hash every listed package file and its portable permission mode."""
    digest = hashlib.sha256()
    inventory = files if files is not None else _bundle_inventory(directory)
    mode_map = modes or {
        rel: os.stat(os.path.join(str(directory), *rel.split("/"))).st_mode
        & 0o777 for rel in inventory
    }
    for rel in sorted(inventory):
        path = os.path.join(str(directory), *rel.split("/"))
        content = _read_bytes(path)
        digest.update(rel.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(("%03o" % mode_map[rel]).encode("ascii"))
        digest.update(b"\x00")
        digest.update(content)
        digest.update(b"\x00")
    return digest.hexdigest()


def _bind_content(content_hash, bundle_id):
    """Bind the content hash to the bundle identity."""
    digest = hashlib.sha256()
    digest.update(content_hash.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(json.dumps(bundle_id, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()


def bundle_hash(bundle_dir):
    """Verify and hash the complete bundle bound to its identity."""
    manifest = _read_manifest(bundle_dir)
    bundle_id = manifest.get("id")
    _check_bundle_id(bundle_id if isinstance(bundle_id, str) else "")
    files = _manifest_files(bundle_dir, manifest)
    modes = _manifest_modes(manifest, files)
    actual = _bind_content(_content_hash(bundle_dir, files, modes), bundle_id)
    if manifest.get("bundle_hash") != actual:
        _fail("bundle %r failed manifest hash verification" % bundle_id)
    return actual


def _validate_source(source_dir):
    missing = []
    for rel in REQUIRED_BUNDLE_FILES:
        if not os.path.isfile(os.path.join(str(source_dir), rel)):
            missing.append(rel)
    if missing:
        _fail("incomplete bundle: missing %s" % ", ".join(sorted(missing)))
    for rel in ("agent", "docs", "hooks", "scripts", "skills",
                ".codex-plugin", ".opencode"):
        path = os.path.join(str(source_dir), rel)
        if not os.path.isdir(path):
            _fail("incomplete bundle: missing package directory %s" % rel)


def _write_manifest(directory, bundle_id, bundle_hash, files, modes):
    manifest = {
        "version": BUNDLE_VERSION,
        "id": bundle_id,
        "bundle_hash": bundle_hash,
        "backends": list(BACKENDS),
        "files": sorted(files),
        "modes": {rel: modes[rel] for rel in sorted(files)},
    }
    path = os.path.join(str(directory), MANIFEST_FILENAME)
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except OSError as exc:
        _fail("cannot write bundle manifest: %s" % exc)
    return manifest


def _read_manifest(bundle_dir):
    try:
        with open(os.path.join(str(bundle_dir), MANIFEST_FILENAME),
                   encoding="utf-8") as handle:
            manifest = json.load(handle)
    except FileNotFoundError:
        _fail("no staged bundle at %s" % bundle_dir)
    except OSError as exc:
        _fail("cannot read bundle manifest: %s" % exc)
    except ValueError as exc:
        _fail("bundle manifest is not valid JSON: %s" % exc)
    if not isinstance(manifest, dict):
        _fail("bundle manifest must be a JSON object")
    return manifest


def stage_bundle(install_root, bundle_id, source_dir):
    """Stage and validate a candidate bundle without selecting it."""
    _check_bundle_id(bundle_id)
    if not os.path.isdir(str(source_dir)):
        _fail("no such bundle source: %s" % source_dir)
    _validate_source(source_dir)
    staging = _staging_dir(install_root, bundle_id)
    if os.path.lexists(staging):
        shutil.rmtree(staging, ignore_errors=True)
    try:
        os.makedirs(staging)
    except OSError as exc:
        _fail("cannot create staging directory: %s" % exc)
    try:
        files = _bundle_inventory(source_dir)
        modes = _source_modes(source_dir, files)
        for rel in files:
            destination = os.path.join(staging, *rel.split("/"))
            parent = os.path.dirname(destination)
            try:
                os.makedirs(parent, exist_ok=True)
                shutil.copy2(
                    os.path.join(str(source_dir), *rel.split("/")),
                    destination)
                _apply_file_mode(destination, modes[rel])
            except OSError as exc:
                _fail("cannot stage %s: %s" % (rel, exc))
        content_hash = _bind_content(
            _content_hash(staging, files, modes), bundle_id)
        manifest = _write_manifest(
            staging, bundle_id, content_hash, files, modes)
        final = _bundle_dir(install_root, bundle_id)
        if os.path.lexists(final):
            old_manifest = _read_manifest(final)
            old_hash = bundle_hash(final)
            if (old_manifest.get("id") == bundle_id
                    and old_hash == content_hash):
                shutil.rmtree(staging, ignore_errors=True)
                return old_manifest
            _fail("bundle id %r is immutable and already contains "
                  "different content" % bundle_id)
        try:
            os.makedirs(os.path.dirname(final), exist_ok=True)
            os.rename(staging, final)
        except OSError as exc:
            _fail("cannot publish staged bundle: %s" % exc)
    except HarnessInstallError:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return manifest


def _write_entry_points(install_root):
    directory = _entrypoints_dir(install_root)
    try:
        os.makedirs(directory, exist_ok=True)
        for backend in BACKENDS:
            path = os.path.join(directory, "%s.sh" % backend)
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(ENTRYPOINT_TEMPLATE % {"backend": backend})
            os.chmod(path, 0o755)
    except OSError as exc:
        _fail("cannot write backend entry points: %s" % exc)


def select_bundle(install_root, bundle_id):
    """Validate the staged bundle and atomically select it."""
    _check_bundle_id(bundle_id)
    bundle_dir = _bundle_dir(install_root, bundle_id)
    manifest = _read_manifest(bundle_dir)
    if manifest.get("version") != BUNDLE_VERSION:
        _fail("bundle %r has unsupported version %r"
              % (bundle_id, manifest.get("version")))
    if manifest.get("id") != bundle_id:
        _fail("bundle identity mismatch for %r" % bundle_id)
    try:
        bundle_hash(bundle_dir)
    except HarnessInstallError as exc:
        _fail("bundle %r failed hash verification (%s); "
              "prior selection preserved" % (bundle_id, exc))
    # Entry points are generic, but they are part of a successful install.
    # Write them before advancing the global pointer so a filesystem failure
    # cannot report an error after changing the selected bundle.
    _write_entry_points(install_root)
    selected_path = _selected_path(install_root)
    try:
        os.makedirs(os.path.dirname(selected_path), exist_ok=True)
        handle, tmp_name = tempfile.mkstemp(
            dir=os.path.dirname(selected_path),
            prefix=SELECTED_FILENAME + ".",
            suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as tmp:
                tmp.write(bundle_id + "\n")
            os.replace(tmp_name, selected_path)
        except OSError:
            try:
                os.remove(tmp_name)
            except OSError:
                pass
            raise
    except OSError as exc:
        _fail("cannot select bundle %r: %s" % (bundle_id, exc))
    return manifest


def selected_bundle(install_root):
    """Return the selected bundle id, or None when nothing is selected."""
    try:
        with open(_selected_path(install_root), encoding="utf-8") as handle:
            selected = handle.read().strip()
    except OSError:
        return None
    return selected or None


def resolve_bundle(project, install_root=None):
    """Verify the project pin against the install root.

    Returns the verified binding (bundle id, directory, hash, backend,
    backend configuration and policy references). A missing pin, an
    unknown bundle, or a hash mismatch raises HarnessInstallError; the
    resolver never falls back to the newest installation.
    """
    root = install_root or os.environ.get("SUPERPOWERS_HARNESS_ROOT")
    if not root:
        _fail("no harness install root: set SUPERPOWERS_HARNESS_ROOT")
    pin_path = os.path.join(str(project), ".superpowers", "harness.json")
    try:
        with open(pin_path, encoding="utf-8") as handle:
            pin = json.load(handle)
    except FileNotFoundError:
        _fail("missing pin for project %s: enroll it with "
              "harness-project init; no fallback to the newest "
              "installation" % project)
    except OSError as exc:
        _fail("cannot read project pin %s: %s" % (pin_path, exc))
    except ValueError as exc:
        _fail("project pin %s is not valid JSON: %s" % (pin_path, exc))
    if not isinstance(pin, dict):
        _fail("project pin %s must be a JSON object" % pin_path)
    if pin.get("version") != BUNDLE_VERSION:
        _fail("project pin %s has unsupported version %r"
              % (pin_path, pin.get("version")))
    bundle_id = pin.get("bundle")
    _check_bundle_id(bundle_id if isinstance(bundle_id, str) else "")
    backend = pin.get("backend")
    if backend not in BACKENDS:
        _fail("project pin %s names unsupported backend %r"
              % (pin_path, backend))
    bundle_dir = _bundle_dir(root, bundle_id)
    if not os.path.isdir(bundle_dir):
        _fail("pinned bundle %r for project %s is not installed; "
              "no fallback to the newest installation" % (bundle_id, project))
    recorded = pin.get("bundle_hash")
    actual = bundle_hash(bundle_dir)
    if not recorded or recorded != actual:
        _fail("pinned bundle %r for project %s failed hash verification"
              % (bundle_id, project))
    return {
        "bundle_id": bundle_id,
        "bundle_dir": bundle_dir,
        "bundle_hash": actual,
        "backend": backend,
        "backend_config": pin.get("backend_config"),
        "policy_refs": pin.get("policy_refs"),
    }


def export_bundle(bundle_dir, output_path):
    """Export a staged bundle as a deterministic archive.

    Both package paths (.zip and .tar.gz) carry the same files: the
    manifest plus every required bundle category. Entries are sorted
    with normalized timestamps and modes so repeated exports agree.
    """
    manifest = _read_manifest(bundle_dir)
    bundle_hash(bundle_dir)
    names = [MANIFEST_FILENAME] + _manifest_files(bundle_dir, manifest)
    output = str(output_path)
    try:
        if output.endswith(".zip"):
            with zipfile.ZipFile(
                    output, "w", zipfile.ZIP_DEFLATED) as archive:
                for name in names:
                    source = os.path.join(str(bundle_dir), name)
                    info = zipfile.ZipInfo(
                        filename=name, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    source_mode = manifest["modes"].get(name, 0o644)
                    info.external_attr = (source_mode << 16)
                    with open(source, "rb") as handle:
                        archive.writestr(info, handle.read())
        elif output.endswith(".tar.gz"):
            import gzip
            with open(output, "wb") as raw:
                with gzip.GzipFile(
                        filename="", mode="wb", compresslevel=9,
                        mtime=0, fileobj=raw) as compressed:
                    with tarfile.open(fileobj=compressed, mode="w",
                                       format=tarfile.USTAR_FORMAT,
                                       pax_headers={}) as archive:
                        for name in names:
                            source = os.path.join(str(bundle_dir), name)
                            entry = archive.gettarinfo(source, arcname=name)
                            entry.uid = 0
                            entry.gid = 0
                            entry.uname = ""
                            entry.gname = ""
                            entry.mtime = 0
                            entry.mode = manifest["modes"].get(name, 0o644)
                            with open(source, "rb") as handle:
                                archive.addfile(entry, handle)
        else:
            _fail("unsupported package path %r: use .zip or .tar.gz"
                  % output)
    except OSError as exc:
        _fail("cannot export bundle to %s: %s" % (output, exc))
    return output


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="harness_install")
    sub = parser.add_subparsers(dest="command", required=True)
    stage = sub.add_parser("stage")
    stage.add_argument("--install-root", required=True)
    stage.add_argument("--bundle", required=True)
    stage.add_argument("--source", required=True)
    select = sub.add_parser("select")
    select.add_argument("--install-root", required=True)
    select.add_argument("--bundle", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "stage":
            manifest = stage_bundle(
                args.install_root, args.bundle, args.source)
        else:
            manifest = select_bundle(args.install_root, args.bundle)
    except HarnessInstallError as exc:
        print("harness_install: %s" % exc, file=sys.stderr)
        return 2
    except OSError as exc:
        print("harness_install: operational failure: %s" % exc,
              file=sys.stderr)
        return 3
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
