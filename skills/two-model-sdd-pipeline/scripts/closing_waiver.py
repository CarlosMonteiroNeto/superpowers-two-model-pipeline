"""Validate a fixed-path supervisor waiver against the closing candidate."""
from __future__ import annotations
import hashlib, json, pathlib, subprocess, sys
from baseline_failures import compare, validate_waiver
from gate_evidence import create_workspace_manifest

def main(workspace: str) -> int:
    ws=pathlib.Path(workspace); state=ws/"supervisor"
    baseline=json.loads((state/"baseline-evidence.json").read_text(encoding="utf-8"))
    current=json.loads((state/"current-evidence.json").read_text(encoding="utf-8"))
    waiver=json.loads((state/"waiver.json").read_text(encoding="utf-8"))
    ledger=ws/"ledger.jsonl"; raw=ledger.read_bytes()
    rows=[json.loads(line) for line in raw.splitlines() if line.strip()]
    for phase,name in (("baseline","baseline-evidence.json"),("closing","current-evidence.json")):
        digest=hashlib.sha256((state/name).read_bytes()).hexdigest()
        events=[row for row in rows if row.get("type")=="suite_evidence" and row.get("phase")==phase]
        if len(events)!=1 or events[0].get("evidence_hash")!=digest:
            raise ValueError("%s suite evidence is not uniquely bound to supervisor ledger" % phase)
    commit=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    plan=json.loads((ws/"plan.json").read_text(encoding="utf-8"))
    tasks=[str(item["id"]) for item in plan["tasks"] if isinstance(item,dict) and item.get("id") is not None]
    if not tasks or any(not item.get("toolchain_id") for item in plan["tasks"] if isinstance(item,dict)):
        raise ValueError("waiver requires explicit supervisor plan toolchain identities")
    manifest=create_workspace_manifest(str(ws),tasks,"tasks")
    expected={"head_commit":"head_commit","tree_hash":"tree_hash","config_hash":"config_hash","environment_hash":"environment_hash"}
    mismatch=[key for key,value in expected.items() if current.get(key)!=manifest["identity"].get(value)]
    if mismatch:
        detail="; ".join("%s evidence=%s manifest=%s"%(key,current.get(key),manifest["identity"].get(expected[key])) for key in mismatch)
        raise ValueError("closing evidence identity does not match final candidate manifest: "+detail)
    if current["source_hash"] != hashlib.sha256(manifest["identity"]["tree_hash"].encode()).hexdigest():
        raise ValueError("closing evidence source does not match final candidate tree")
    comparison=compare(baseline,current)
    candidate={"baseline":baseline,"current":current,"recorded_comparison":comparison,
        "candidate_commit":commit,"approval_ledger":str(ledger),
        "ledger_revision":hashlib.sha256(raw).hexdigest()}
    result=validate_waiver(waiver,candidate)
    print(json.dumps(result,sort_keys=True))
    return 0

if __name__=="__main__":
    try: raise SystemExit(main(sys.argv[1]))
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print("CLOSING-WAIVER: "+str(exc),file=sys.stderr); raise SystemExit(1)
