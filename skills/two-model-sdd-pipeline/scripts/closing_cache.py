"""Check whether supervisor closing evidence can be reused byte-for-byte."""
import hashlib,json,pathlib,subprocess,sys

def valid(workspace:str)->bool:
    ws=pathlib.Path(workspace); state=ws/"supervisor"; evidence_path=state/"current-evidence.json"
    manifest_path=ws/"impact-manifest.json"; ledger_path=ws/"ledger.jsonl"
    if not all(path.is_file() for path in (evidence_path,manifest_path,ledger_path,ws/"plan.json")): return False
    from gate_evidence import create_workspace_manifest, matches, validate_manifest
    plan=json.loads((ws/"plan.json").read_text(encoding="utf-8"))
    tasks=[str(task["id"]) for task in plan["tasks"] if isinstance(task,dict) and task.get("id") is not None]
    if not tasks or any(not task.get("toolchain_id") for task in plan["tasks"] if isinstance(task,dict)): return False
    prior=validate_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
    current=create_workspace_manifest(workspace,tasks,"tasks")
    if current["selection_hash"]!=prior["selection_hash"]: return False
    evidence=json.loads(evidence_path.read_text(encoding="utf-8"))
    if any(evidence.get(field)!=current["identity"][key] for field,key in (
        ("head_commit","head_commit"),("tree_hash","tree_hash"),("config_hash","config_hash"),
        ("environment_hash","environment_hash"))): return False
    required={str(task["toolchain_id"]) for task in plan["tasks"]}
    if {suite["id"] for suite in evidence.get("suites",[])}!=required: return False
    digest=hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    records=[json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    suite_events=[row for row in records if row.get("type")=="suite_evidence" and row.get("phase")=="closing"]
    if not suite_events or suite_events[-1].get("evidence_hash")!=digest: return False
    gate_records=[row for row in records if row.get("type")=="impact_gate_evidence" and row.get("phase")=="closing"]
    candidate={"commit":current["identity"]["head_commit"],"tree_hash":current["identity"]["tree_hash"],
        "config_hash":current["identity"]["config_hash"],"environment_hash":current["identity"]["environment_hash"],
        "impact_manifest":current}
    return bool(gate_records and matches(gate_records[-1],candidate))

if __name__=="__main__":
    try: raise SystemExit(0 if valid(sys.argv[1]) else 1)
    except (OSError,ValueError,TypeError,KeyError,subprocess.CalledProcessError): raise SystemExit(1)
