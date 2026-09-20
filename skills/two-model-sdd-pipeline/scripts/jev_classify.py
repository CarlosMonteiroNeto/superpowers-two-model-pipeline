"""Strict Choice-only TypeSafe adapter with private cache and circuit state."""
import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.request

import jev_store

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
ADAPTER_VERSION = "1"
VALID_SITES = {"site1", "site2", "site3", "site4", "site5"}


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _identity(schema, state, cache_key):
    body = {"state": state, "questions": schema.get("questions"), "model": schema.get("model"),
            "endpoint": schema.get("endpoint", ENDPOINT), "adapter_version": ADAPTER_VERSION, "namespace": cache_key}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def _error(status, message, identity=None, schema_hash=None, error_kind=None):
    return {"status": status, "answers": {}, "model": None, "usage": None, "request_hash": identity,
            "cache_hit": False, "error": message, "schema_hash": schema_hash,
            "error_kind": error_kind}


def _validate_schema(schema, threshold):
    if not isinstance(schema, dict) or not isinstance(schema.get("model"), str) or not schema["model"].strip():
        raise ValueError("schema requires a nonempty model")
    if not isinstance(schema.get("questions"), dict):
        raise ValueError("schema questions must be an object")
    if not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("threshold must be finite in [0, 1]")
    for qid, question in schema["questions"].items():
        if not isinstance(question, dict):
            raise ValueError("each Choice question must be an object")
        criteria = question.get("criteria")
        if (not isinstance(qid, str) or not qid or question.get("type") != "choice"
                or not isinstance(question.get("instructions"), str) or not question["instructions"].strip()
                or not isinstance(criteria, dict) or len(criteria) < 2
                or any(not isinstance(key, str) or not key for key in criteria)
                or any(value is not None and not isinstance(value, str) for value in criteria.values())):
            raise ValueError("each Choice question requires type, instructions, and criteria")


def _validated_answers(schema, response):
    if not isinstance(response, dict) or not isinstance(response.get("model"), str) or not response["model"].strip():
        raise ValueError("response requires a model")
    if response["model"] != schema["model"]:
        raise ValueError("response model does not match requested model")
    if not isinstance(response.get("usage"), dict):
        raise ValueError("answered response requires usage")
    answers = response.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(schema["questions"]):
        raise ValueError("response question set mismatch")
    normalized = {}
    for qid, question in schema["questions"].items():
        answer = answers[qid]
        if not isinstance(answer, dict): raise ValueError("answer must be an object")
        options = list(question["criteria"])
        probabilities = answer.get("probabilities")
        choice = answer.get("choice")
        confidence = answer.get("confidence")
        if answer.get("type") != "choice" or choice not in options or not isinstance(probabilities, dict) or set(probabilities) != set(options):
            raise ValueError("Choice options mismatch")
        if not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("invalid confidence")
        values = list(probabilities.values())
        if any(not isinstance(x, (int, float)) or not math.isfinite(x) or not 0 <= x <= 1 for x in values) or abs(sum(values) - 1) > 1e-6:
            raise ValueError("invalid probabilities")
        maximum = max(values)
        if probabilities[choice] < maximum - 1e-12:
            raise ValueError("selected Choice must be maximal")
        normalized[qid] = {"type": "choice", "choice": choice, "probabilities": probabilities, "confidence": confidence}
    return normalized


def _default_transport(payload, timeout, api_key):
    request = urllib.request.Request(ENDPOINT, data=_canonical(payload).encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.getcode(), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return exc.code, {"error": body}


def _call(transport, payload, attempts, timeout, api_key, sleep):
    last = "transport unavailable"
    for number in range(attempts):
        try:
            status, response = transport(payload, timeout, api_key)
            if status == 200:
                return response
            last = "remote response unavailable"
            retry = status == 429 or status == 529 or 500 <= status <= 599
            if not retry: break
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            last = str(exc) or "transport unavailable"
        if number + 1 < attempts:
            sleep(min(2, 1))
    raise RuntimeError(last)


def classify(schema, state, *, workspace, site, threshold=.9, cache_key=None, refresh=False, reset_circuit=False,
             transport=None, sleep=time.sleep, api_key=None):
    """Return (exit_code, envelope). The injected transport is test-only."""
    try:
        if site not in VALID_SITES:
            raise ValueError("unknown Jev site")
        _validate_schema(schema, threshold)
        if not isinstance(workspace, str) or not workspace: raise ValueError("workspace is required")
        identity = _identity(schema, state, cache_key)
        schema_hash = hashlib.sha256(_canonical(schema).encode("utf-8")).hexdigest()
    except ValueError as exc:
        # Keep the public envelope status compatible with the classifier
        # contract (unavailable), while making the local/setup nature of an
        # exit-2 failure explicit to runtime advisory callers.
        return 2, _error("unavailable", str(exc), schema_hash=None, error_kind="setup_error")
    if reset_circuit:
        jev_store.reset_circuit(workspace, site)
    if not refresh:
        try:
            cached = jev_store.read_cache(workspace, site, identity)
        except Exception as exc:
            return 3, _error("cache_unavailable", str(exc) or "cache unavailable", identity,
                             schema_hash, error_kind="cache_error")
        if cached:
            try:
                answers = _validated_answers(schema, {"model": cached["model"], "usage": cached["usage"], "answers": cached["answers"]})
                cached.update({"status": "answered", "answers": answers, "request_hash": identity, "cache_hit": True, "error": None, "schema_hash": schema_hash})
                return (0 if all(a["confidence"] >= threshold for a in answers.values()) else 1), cached
            except (KeyError, ValueError, TypeError):
                pass
    try:
        circuit = jev_store.circuit_state(workspace, site)
    except Exception as exc:
        return 3, _error("cache_unavailable", str(exc) or "circuit state unavailable", identity,
                         schema_hash, error_kind="cache_error")
    if circuit.get("failures", 0) >= 3:
        return 1, _error("circuit_open", "circuit is open", identity, schema_hash)
    if not schema["questions"]:
        return 0, {"status": "answered", "answers": {}, "model": schema["model"], "usage": {}, "request_hash": identity, "cache_hit": False, "error": None, "schema_hash": schema_hash}
    key = api_key if api_key is not None else os.environ.get("TYPESAFE_API_KEY")
    if transport is None and not key:
        jev_store.record_failure(workspace, site)
        return 3, _error("unavailable", "TYPESAFE_API_KEY is unavailable", identity, schema_hash,
                         error_kind="provider_unavailable")
    payload_questions = {}
    for qid, question in schema["questions"].items():
        payload_questions[qid] = {"type": "choice", "instructions": question["instructions"], "criteria": question["criteria"]}
    payload = {"model": schema["model"], "state": state, "questions": payload_questions}
    attempts, timeout = (1, 10) if site in ("site3", "site4") else (2, 30)
    try:
        response = _call(transport or _default_transport, payload, attempts, timeout, key, sleep)
        answers = _validated_answers(schema, response)
    except (RuntimeError, ValueError, TypeError, KeyError) as exc:
        jev_store.record_failure(workspace, site)
        return 3, _error("unavailable", str(exc) or "invalid response", identity, schema_hash,
                         error_kind="provider_unavailable")
    jev_store.record_success(workspace, site)
    envelope = {"status": "answered", "answers": answers, "model": response["model"], "usage": response.get("usage"),
                "request_hash": identity, "cache_hit": False, "error": None, "schema_hash": schema_hash}
    try:
        jev_store.write_cache(workspace, site, identity, envelope)
    except Exception as exc:
        return 3, _error("cache_unavailable", str(exc) or "cache unavailable", identity,
                         schema_hash, error_kind="cache_error")
    return (0 if all(a["confidence"] >= threshold for a in answers.values()) else 1), envelope


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="jev-classify")
    parser.add_argument("schema_file")
    parser.add_argument("state_file")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--site", required=True)
    parser.add_argument("--threshold", type=float, default=.9)
    parser.add_argument("--cache-key")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--reset-circuit", action="store_true")
    args = parser.parse_args(argv)
    try:
        with open(args.schema_file, encoding="utf-8") as h: schema = json.load(h)
        with open(args.state_file, encoding="utf-8") as h: state = json.load(h)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps(_error("unavailable", str(exc), error_kind="setup_error")))
        return 2
    code, envelope = classify(schema, state, workspace=args.workspace, site=args.site, threshold=args.threshold,
                              cache_key=args.cache_key, refresh=args.refresh, reset_circuit=args.reset_circuit)
    print(json.dumps(envelope, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
