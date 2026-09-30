"""Aggregate observed dispatch cost without inferring missing usage."""

from __future__ import annotations

import math


BACKENDS = ("codex", "opencode")
COUNT_FIELDS = ("semantic_invocations", "backend_model_turns", "transport_retries",
                "jev_calls", "escaped_defects")
TOKEN_FIELDS = {"input": "input_tokens", "output": "output_tokens",
                "cached": "cached_tokens"}


def _number(value, label):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("%s must be a non-negative integer or null" % label)
    return value


def _measurement(value, label):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("%s must be a finite non-negative number or null" % label)
    return value


def _known_total(values):
    if not values or any(value is None for value in values):
        return None
    return sum(values)


def _summarize(records):
    ids = set()
    fields = {name: [] for name in COUNT_FIELDS}
    tokens = {name: [] for name in TOKEN_FIELDS}
    latency = []
    backends = {name: [] for name in BACKENDS}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError("record %d must be an object" % index)
        backend = record.get("backend")
        if backend not in BACKENDS:
            raise ValueError("record %d backend must be codex or opencode" % index)
        dispatch_id = record.get("dispatch_id")
        if not isinstance(dispatch_id, str) or not dispatch_id:
            raise ValueError("record %d requires dispatch_id" % index)
        if dispatch_id in ids:
            raise ValueError("duplicate dispatch_id: %s" % dispatch_id)
        ids.add(dispatch_id)
        usage = record.get("usage")
        if usage is not None and not isinstance(usage, dict):
            raise ValueError("record %d usage must be an object or null" % index)
        observed = {}
        for name in COUNT_FIELDS:
            value = _number(record.get(name), "record %d %s" % (index, name))
            fields[name].append(value)
            observed[name] = value
        for name, source in TOKEN_FIELDS.items():
            raw = usage.get(source) if isinstance(usage, dict) else None
            value = _number(raw, "record %d usage.%s" % (index, source))
            tokens[name].append(value)
        observed_tokens = {name: _number(
            usage.get(source) if isinstance(usage, dict) else None,
            "record %d usage.%s" % (index, source))
            for name, source in TOKEN_FIELDS.items()}
        observed_latency = _measurement(record.get("latency_ms"),
                                        "record %d latency_ms" % index)
        latency.append(observed_latency)
        observed["latency_ms_total"] = observed_latency
        observed["tokens"] = observed_tokens
        backends[backend].append(observed)

    result = {name: _known_total(values) for name, values in fields.items()}
    result["tokens"] = {name: _known_total(values) for name, values in tokens.items()}
    result["latency_ms_total"] = _known_total(latency)
    result["by_backend"] = {}
    for backend in BACKENDS:
        subset = backends[backend]
        result["by_backend"][backend] = {
            **{name: _known_total([row[name] for row in subset])
               for name in COUNT_FIELDS},
            "tokens": {name: _known_total([row["tokens"][name] for row in subset])
                       for name in TOKEN_FIELDS},
            "latency_ms_total": _known_total([row["latency_ms_total"] for row in subset]),
        }
    return result


def summarize(records):
    """Return sums only when every record provides that evidence; else null."""
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    return _summarize(records)


def compare_cost(baseline, current):
    """Allow cost claims only from comparable measured usage and quality data."""
    if not isinstance(baseline, dict) or not isinstance(current, dict):
        raise ValueError("baseline and current summaries must be objects")
    dimensions = ("input", "output", "cached")
    pairs = []
    for key in dimensions:
        old_tokens = baseline.get("tokens")
        new_tokens = current.get("tokens")
        if not isinstance(old_tokens, dict) or not isinstance(new_tokens, dict):
            raise ValueError("token summaries must be objects")
        old = _number(old_tokens.get(key), "baseline tokens.%s" % key)
        new = _number(new_tokens.get(key), "current tokens.%s" % key)
        if old is None or new is None:
            return {"status": "insufficient_evidence", "savings_claim_allowed": False,
                    "reason": "token usage is unknown"}
        pairs.append((old, new))
    old_latency = _measurement(baseline.get("latency_ms_total"), "baseline latency_ms_total")
    new_latency = _measurement(current.get("latency_ms_total"), "current latency_ms_total")
    old_defects = _number(baseline.get("escaped_defects"), "baseline escaped_defects")
    new_defects = _number(current.get("escaped_defects"), "current escaped_defects")
    if None in (old_latency, new_latency, old_defects, new_defects):
        return {"status": "insufficient_evidence", "savings_claim_allowed": False,
                "reason": "latency or escaped-defect evidence is unknown"}
    if new_defects > old_defects:
        return {"status": "quality_regression", "savings_claim_allowed": False,
                "reason": "escaped defects increased"}
    worsened = any(new > old for old, new in pairs) or new_latency > old_latency
    reduced = any(new < old for old, new in pairs) or new_latency < old_latency
    if worsened:
        return {"status": "usage_tradeoff", "savings_claim_allowed": False,
                "reason": "one or more measured usage dimensions increased"}
    if reduced:
        return {"status": "measured_usage_reduction", "savings_claim_allowed": False,
                "reason": "usage dimensions fell, but no pricing model establishes cost savings"}
    return {"status": "no_measured_usage_reduction", "savings_claim_allowed": False,
            "reason": "no measured token or latency usage dimension decreased"}
