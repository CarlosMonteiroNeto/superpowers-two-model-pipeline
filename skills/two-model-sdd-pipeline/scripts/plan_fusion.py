"""CLI for Site 5 shadow recommendations and explicitly selected offline fusion."""
import argparse
import hashlib
import json
import os
import pathlib
import tempfile

import fusion_apply
import fusion_candidates
import jev_classify


POLICY_VERSION = fusion_apply.POLICY_VERSION


class DomainError(Exception):
    pass


def hash_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        raise ValueError("required input is unavailable: {}".format(path)) from exc


def _atomic_write(path, data, *, overwrite=False):
    destination = pathlib.Path(path)
    if destination.exists() and not overwrite:
        raise DomainError("output already exists; use --overwrite")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".plan-fusion-", dir=str(destination.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _schema(pairs):
    questions = {}
    for pair in pairs:
        first, second = pair["ids"]
        questions["pair-{}-{}".format(first, second)] = {
            "type": "choice",
            "instructions": (
                "Compare `state.pairs[{}].left` and `state.pairs[{}].right`. Choose "
                "same_shape_fuse only when their concrete edits share one transformation pattern "
                "and remain coherently testable and reviewable; otherwise choose keep_separate."
            ).format(len(questions), len(questions)),
            "criteria": {"same_shape_fuse": "Same concrete transformation pattern.", "keep_separate": "Different, unclear, or insufficiently related work."},
        }
    return {"model": "jev", "questions": questions}


def propose(draft_path, workspace, report_path):
    plan = _read_json(draft_path)
    candidates = fusion_candidates.build_candidates(plan, workspace)
    pairs = candidates["pairs"]
    report = {"draft_hash": candidates["draft_hash"], "policy_version": POLICY_VERSION, "mode": "shadow",
              "pairs": [], "exclusions": candidates["exclusions"], "request_identities": [], "source_snapshot": plan}
    batches, oversized = fusion_candidates.batch_pairs(pairs, model="jev", schema_builder=_schema)
    for ids in oversized:
        report["pairs"].append({"ids": ids, "status": "unevaluated", "reason": "pair exceeds 64KiB request budget", "selectable": False})
    for batch in batches:
        schema = _schema(batch)
        state = {"pairs": [{"left": pair["left"], "right": pair["right"]} for pair in batch]}
        code, envelope = jev_classify.classify(schema, state, workspace=workspace, site="site5")
        report["request_identities"].append(envelope.get("request_hash"))
        if code == 2:
            raise ValueError("jev classifier rejected local proposal input")
        for pair in batch:
            question_id = "pair-{}-{}".format(*pair["ids"])
            answer = envelope.get("answers", {}).get(question_id)
            report["pairs"].append({"ids": pair["ids"], "choice": answer.get("choice") if answer else None,
                                    "confidence": answer.get("confidence") if answer else None,
                                    "probabilities": answer.get("probabilities") if answer else None,
                                    "candidate_hash": pair["candidate_hash"], "selectable": bool(answer and answer["choice"] == "same_shape_fuse" and answer["confidence"] >= .9),
                                    "status": envelope.get("status"), "request_hash": envelope.get("request_hash"),
                                    "raw_answer": answer})
        if code == 3:
            report["service_unavailable"] = envelope.get("error")
    _atomic_write(report_path, json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n")
    return report


def apply(draft_path, report_path, selection_path, output_path, overwrite=False):
    try:
        source_bytes = pathlib.Path(draft_path).read_bytes()
    except OSError as exc:
        raise ValueError("required input is unavailable: {}".format(draft_path)) from exc
    destination = pathlib.Path(output_path)
    if destination.resolve() == pathlib.Path(draft_path).resolve() or destination.name.casefold() == "plan.json":
        raise DomainError("output must be a distinct non-runtime plan file")
    plan = json.loads(source_bytes.decode("utf-8"))
    report, selection = _read_json(report_path), _read_json(selection_path)
    if not selection.get("pairs"):
        fusion_apply.apply_selection(plan, report, selection)
        _atomic_write(output_path, source_bytes, overwrite=overwrite)
        return
    output, _ = fusion_apply.apply_selection(plan, report, selection)
    _atomic_write(output_path, json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n", overwrite=overwrite)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="plan-fusion")
    commands = parser.add_subparsers(dest="command", required=True)
    propose_parser = commands.add_parser("propose")
    propose_parser.add_argument("draft")
    propose_parser.add_argument("--workspace", required=True)
    propose_parser.add_argument("--report", required=True)
    apply_parser = commands.add_parser("apply")
    apply_parser.add_argument("draft")
    apply_parser.add_argument("--report", required=True)
    apply_parser.add_argument("--selection", required=True)
    apply_parser.add_argument("--output", required=True)
    apply_parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "propose":
            propose(args.draft, args.workspace, args.report)
        else:
            apply(args.draft, args.report, args.selection, args.output, args.overwrite)
    except DomainError as exc:
        print("PLAN-FUSION: {}".format(exc), file=os.sys.stderr)
        return 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("PLAN-FUSION: {}".format(exc), file=os.sys.stderr)
        return 2 if isinstance(exc, (ValueError, json.JSONDecodeError)) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
