"""Provider-neutral normalization around ecosystem research adapters."""


def collect(request, adapters):
    if not isinstance(request, dict) or not isinstance(adapters, dict):
        raise ValueError("request and adapters must be objects")
    search = adapters.get("search")
    if not callable(search):
        raise ValueError("a local search adapter is required")
    requirement = request.get("requirement")
    if not isinstance(requirement, str) or not requirement.strip():
        raise ValueError("request.requirement is required")
    raw = search(dict(request))
    if not isinstance(raw, list):
        raise ValueError("research adapter must return a list")
    alternatives = []
    for candidate in raw:
        if not isinstance(candidate, dict):
            continue
        name, source, evidence = candidate.get("name"), candidate.get("source"), candidate.get("evidence")
        license_info, compatibility = candidate.get("license"), candidate.get("compatibility")
        if not isinstance(name, str) or not name or not source or not evidence or license_info is None or compatibility is None:
            continue
        alternatives.append({key: value for key, value in candidate.items()})
    alternatives.sort(key=lambda item: (item["name"], str(item["source"])))
    selection = request.get("selection")
    selected = None
    questions = []
    if selection is not None:
        if not isinstance(selection, dict) or not isinstance(selection.get("name"), str) or not isinstance(selection.get("reason"), str) or not selection["reason"].strip():
            questions.append({"type": "selection_reason_required"})
        else:
            selected = next((item for item in alternatives if item["name"] == selection["name"]), None)
            if selected is None:
                questions.append({"type": "selection_not_in_evidence", "name": selection["name"]})
    return {"requirement": requirement, "alternatives": alternatives, "selection": selected,
            "selection_reason": selection.get("reason") if selected is not None else None, "questions": questions}


def main(argv=None):
    import argparse
    import json
    import sys
    from pathlib import Path
    parser = argparse.ArgumentParser(description="Normalize supplied offline solution research")
    parser.add_argument("request_json")
    parser.add_argument("evidence_json", help="Previously collected adapter candidates")
    args = parser.parse_args(argv)
    try:
        request = json.loads(Path(args.request_json).read_text(encoding="utf-8"))
        candidates = json.loads(Path(args.evidence_json).read_text(encoding="utf-8"))
        result = collect(request, {"search": lambda _request: candidates})
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print("solution-research: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
