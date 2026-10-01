"""Prepare compatible template material without overwriting target changes."""

from pathlib import PurePosixPath


def _files(files):
    if not isinstance(files, dict):
        return None
    for path, content in files.items():
        if (not isinstance(path, str) or not path or "\\" in path or ":" in path
                or PurePosixPath(path).is_absolute() or any(part in (".", "..") for part in PurePosixPath(path).parts)
                or not isinstance(content, str)):
            return None
    return dict(files)


def prepare(request, evidence):
    if not isinstance(request, dict) or not isinstance(evidence, dict):
        return {"status": "question", "reason": "request or candidate evidence is missing"}
    compatibility = evidence.get("compatibility")
    if compatibility == "incompatible" or compatibility is False:
        return {"status": "block", "reason": "candidate is technically incompatible"}
    license_info = evidence.get("license")
    if compatibility != "compatible" or not isinstance(license_info, dict) or license_info.get("status") != "known" or not license_info.get("value"):
        return {"status": "question", "reason": "compatibility or license evidence is ambiguous"}
    requirements = request.get("requirements", [])
    checks = evidence.get("checks")
    if not isinstance(requirements, list) or not isinstance(checks, dict):
        return {"status": "question", "reason": "technical requirement checks are missing"}
    if any(checks.get(requirement) is False for requirement in requirements):
        return {"status": "block", "reason": "candidate fails a required technical check"}
    if any(checks.get(requirement) is not True for requirement in requirements):
        return {"status": "question", "reason": "required technical checks are incomplete"}
    source = evidence.get("source")
    if not source:
        return {"status": "question", "reason": "source provenance is missing"}
    if "files" not in evidence:
        return {"status": "question", "reason": "candidate files were not verified"}
    files, target = _files(evidence.get("files")), _files(request.get("target_files", {}))
    if files is None or target is None:
        return {"status": "block", "reason": "candidate or target file paths are unsafe"}
    conflicts = sorted(path for path in files.keys() & target.keys() if files[path] != target[path])
    if conflicts or evidence.get("conflicts"):
        return {"status": "question", "reason": "template adoption needs a user merge", "conflicts": conflicts + list(evidence.get("conflicts", [])), "preserved_local": target}
    merged = dict(files)
    merged.update(target)
    return {"status": "adopted", "source": source, "license": license_info,
            "files": merged, "preserved_local": target, "requirements_checked": list(requirements)}
