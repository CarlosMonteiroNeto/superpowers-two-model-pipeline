"""Export a complete, stopped task family without discarding raw evidence."""
import hashlib
import json
import os
import tarfile
import tempfile


def export_family(source: str, destination: str, manifest: dict) -> dict:
    if not isinstance(manifest, dict) or not manifest.get("run_id") or manifest.get("family_id") is None:
        raise ValueError("manifest requires run_id and family_id")
    if manifest.get("stopped") is not True:
        raise ValueError("cannot export a family with active workers")
    if manifest.get("strict") is True and (manifest.get("clean") is not True or manifest.get("approved") is not True or manifest.get("merged") is not True or not manifest.get("merged_tip")):
        raise ValueError("strict family manifest requires clean, approved and merged state with merged_tip")
    if manifest.get("clean") is False or manifest.get("approved") is False or manifest.get("merged") is False:
        raise ValueError("family is not clean, approved and integrated")
    root = os.path.realpath(source)
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("manifest files must be a non-empty list")
    resolved = []
    for name in files:
        if not isinstance(name, str) or os.path.isabs(name) or ".." in name.replace("\\", "/").split("/"):
            raise ValueError("invalid evidence path")
        path = os.path.realpath(os.path.join(root, name))
        if os.path.commonpath((root, path)) != root or not os.path.isfile(path):
            raise ValueError("missing or escaping evidence file: {}".format(name))
        resolved.append((name.replace("\\", "/"), path))
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix="family-", suffix=".tar.gz", dir=os.path.dirname(os.path.abspath(destination)))
    os.close(fd)
    digests = {}
    try:
        with tarfile.open(temp, "w:gz") as archive:
            for name, path in resolved:
                archive.add(path, arcname=name, recursive=False)
                with open(path, "rb") as f:
                    digests[name] = hashlib.sha256(f.read()).hexdigest()
            payload = dict(manifest, evidence_sha256=digests)
            info = tarfile.TarInfo("family-manifest.json")
            data = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()
            info.size = len(data)
            archive.addfile(info, __import__("io").BytesIO(data))
        with tarfile.open(temp, "r:gz") as archive:
            names = archive.getnames()
            if len(names) != len(set(names)) or "family-manifest.json" not in names:
                raise ValueError("archive integrity check failed")
            for name, expected in digests.items():
                stream = archive.extractfile(name)
                if stream is None or hashlib.sha256(stream.read()).hexdigest() != expected:
                    raise ValueError("archive evidence integrity check failed: {}".format(name))
        os.replace(temp, destination)
    finally:
        if os.path.exists(temp): os.unlink(temp)
    return {"run_id": manifest["run_id"], "family_id": manifest["family_id"], "destination": os.path.abspath(destination), "files": len(resolved), "sha256": digests}
