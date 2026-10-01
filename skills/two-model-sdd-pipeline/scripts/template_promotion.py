"""Stage reviewed reusable assets in a local repository; never publish remotely."""

import argparse
import errno
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath


_EXCLUDED = {".env", ".env.local", "credentials.json", "secrets.json", "catalog.sqlite", "catalog.sqlite3",
             "template-catalog.sqlite3", "embeddings.json", "private-project-notes.md"}


def _safe_path(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        return False
    if any(part in ("", ".", "..") for part in value.split("/")):
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and bool(path.parts)


def _normalized_path(value):
    return "/".join(unicodedata.normalize("NFC", part).casefold() for part in value.split("/"))


def _valid_payload_paths(files):
    """Validate portable physical destinations before creating staging paths."""
    normalized = {}
    for path in files:
        if not _safe_path(path):
            return False
        canonical = _normalized_path(path)
        parts = canonical.split("/")
        if parts[0] == "release.json":
            return False
        if canonical in normalized:
            return False
        normalized[canonical] = path
    paths = set(normalized)
    return not any(any(parent in paths for parent in ("/".join(parts[:index]) for index in range(1, len(parts))))
                   for parts in (path.split("/") for path in paths))


def _target_matches(target, expected_manifest, expected_files):
    """Return whether an existing stage is the exact regular-file payload."""
    try:
        if target.is_symlink() or not target.is_dir():
            return False
        manifest_path = target / "release.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            return False
        if manifest_path.read_text(encoding="utf-8") != expected_manifest:
            return False

        expected_paths = set(expected_files) | {"release.json"}
        actual_paths = set()
        for current, directories, filenames in os.walk(target, followlinks=False):
            current_path = Path(current)
            for dirname in directories:
                if (current_path / dirname).is_symlink():
                    return False
            for filename in filenames:
                candidate = current_path / filename
                if candidate.is_symlink() or not candidate.is_file():
                    return False
                resolved = candidate.resolve(strict=True)
                if os.path.commonpath((str(target.resolve()), str(resolved))) != str(target.resolve()):
                    return False
                actual_paths.add(candidate.relative_to(target).as_posix())
        if actual_paths != expected_paths:
            return False
        for relative, content in expected_files.items():
            candidate = target.joinpath(*PurePosixPath(relative).parts)
            if candidate.read_bytes() != content.encode("utf-8"):
                return False
        return True
    except (OSError, UnicodeError, ValueError):
        return False


def _excluded(path):
    parts = {part.lower() for part in PurePosixPath(path).parts}
    base = PurePosixPath(path).name.lower()
    suffix = PurePosixPath(path).suffix.lower()
    return (base in _EXCLUDED or base.startswith((".env", "secret", "credential"))
            or suffix in {".sqlite", ".sqlite3", ".db"}
            or any(part in {"private", "private-evidence", "embeddings", "embedding", ".git"} for part in parts)
            or "evidence" in base)


def _verified_dependencies(catalog):
    dependencies = catalog.get("dependencies", [])
    if not isinstance(dependencies, list):
        return False
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            return False
        if not all(isinstance(dependency.get(key), str) and dependency[key] for key in ("name", "version")):
            return False
        if re.search(r"todo|latest|\*", dependency["version"], re.IGNORECASE):
            return False
        if dependency.get("compatible") is not True or dependency.get("license", {}).get("status") != "known":
            return False
    return True


def stage(request, catalog):
    """Atomically stage a verified asset; repeated identical calls are idempotent."""
    if not isinstance(request, dict) or not isinstance(catalog, dict):
        return {"status": "blocked", "reason": "request and catalog must be objects"}
    identity_fields = ("asset_id", "version", "source_identity")
    if any(not isinstance(request.get(key), str) or not request[key] for key in identity_fields):
        return {"status": "blocked", "reason": "promotion identity is incomplete"}
    if any(request.get(key) != catalog.get(key) for key in ("asset_id", "source_identity")):
        return {"status": "blocked", "reason": "catalog provenance does not match promotion request"}
    if catalog.get("license", {}).get("status") != "known" or not catalog.get("license", {}).get("value"):
        return {"status": "blocked", "reason": "known license evidence is required"}
    verification = catalog.get("verification", {})
    if not isinstance(verification, dict) or verification.get("api") is not True or verification.get("tests") is not True:
        return {"status": "blocked", "reason": "API and tests verification are required"}
    if not _verified_dependencies(catalog):
        return {"status": "blocked", "reason": "dependency versions, compatibility, and licenses must be verified"}
    files = request.get("files")
    if not isinstance(files, dict) or any(not _safe_path(path) or not isinstance(content, str) for path, content in files.items()):
        return {"status": "blocked", "reason": "files must use safe relative text paths"}
    if not _valid_payload_paths(files):
        return {"status": "blocked", "reason": "files contain reserved, aliased, or conflicting destinations"}
    included = {path: content for path, content in files.items() if not _excluded(path)}
    if not included:
        return {"status": "blocked", "reason": "no distributable files remain after exclusions"}
    repository_value = request.get("repository")
    if not isinstance(repository_value, str) or not repository_value.strip():
        return {"status": "blocked", "reason": "an existing local staging repository must be selected"}
    repository = Path(repository_value).resolve()
    if not repository.is_dir():
        return {"status": "blocked", "reason": "staging repository must already exist locally"}
    key = "\0".join((request["asset_id"], request["version"], request["source_identity"]))
    stage_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    staging_root = repository / ".staging"
    if staging_root.exists():
        resolved_staging = staging_root.resolve()
        if os.path.commonpath((str(repository), str(resolved_staging))) != str(repository):
            return {"status": "blocked", "reason": "staging path escapes the selected repository"}
    target = staging_root / stage_id
    if target.is_symlink():
        return {"status": "blocked", "reason": "staging target may not be a symbolic link"}
    manifest = {"status": "staged", "stage_id": stage_id, "asset_id": request["asset_id"], "version": request["version"],
                "source_identity": request["source_identity"], "license": catalog["license"],
                "dependencies": catalog.get("dependencies", []), "files": included}
    expected = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if target.exists():
        if _target_matches(target, expected, included):
            return {"status": "staged", "stage_id": stage_id, "path": str(target), "files": included, "idempotent": True}
        return {"status": "overwrite_refused", "stage_id": stage_id, "path": str(target)}
    staging_root.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=".stage-", dir=str(staging_root)))
    try:
        for relative, content in included.items():
            destination = temp_root.joinpath(*PurePosixPath(relative).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
        (temp_root / "release.json").write_text(expected, encoding="utf-8")
        try:
            os.replace(str(temp_root), str(target))
        except OSError as error:
            # Directory replacement may report EEXIST, ENOTEMPTY, or EISDIR
            # depending on the platform when another writer publishes first.
            if not (isinstance(error, FileExistsError) or error.errno in {errno.EEXIST, errno.ENOTEMPTY, errno.EISDIR}) or not target.exists():
                raise
            if not _target_matches(target, expected, included):
                return {"status": "overwrite_refused", "stage_id": stage_id, "path": str(target)}
            return {"status": "staged", "stage_id": stage_id, "path": str(target), "files": included, "idempotent": True}
    finally:
        if temp_root.exists():
            shutil.rmtree(temp_root)
    return {"status": "staged", "stage_id": stage_id, "path": str(target), "files": included, "idempotent": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Stage a reviewed asset in a local template repository")
    parser.add_argument("request_json")
    parser.add_argument("catalog_json")
    args = parser.parse_args(argv)
    try:
        request = json.loads(Path(args.request_json).read_text(encoding="utf-8"))
        catalog = json.loads(Path(args.catalog_json).read_text(encoding="utf-8"))
        result = stage(request, catalog)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["status"] == "staged" else 1
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("promote-template: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
