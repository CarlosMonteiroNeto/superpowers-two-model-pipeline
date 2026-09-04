"""Deterministic parser for the Reviewer's verdict from opencode event logs.

Provides two pure functions:
  extract_verdict(text)      – extract a verdict dict from reviewer reply text
  extract_from_log(log_text) – extract a verdict from an opencode JSONL event log

And a CLI entry-point when run as __main__.
"""

import json
import re
import sys


def extract_verdict(text):
    """Return the verdict dict parsed from *text*, or None if absent.

    Tolerates prose before/after the JSON, ```json fences, a malformed
    trailing comma (comma before ``}``), newlines inside strings, and
    unicode escapes.
    """
    if not text or not isinstance(text, str):
        return None

    # Strip ```json ... ``` fences if present (take the innermost block).
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)

    # Find the first opening brace – start of the JSON object.
    start = text.find("{")
    if start == -1:
        return None

    # Balanced-brace scan with a generous bound to avoid infinite loops.
    depth = 0
    in_string = False
    escape = False
    end = -1
    bound = min(len(text), start + 10_000)

    for i in range(start, bound):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            if in_string:
                escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end == -1:
        return None

    candidate = text[start : end + 1]

    # Try parsing as-is first.
    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict) and "verdict" in obj:
            return obj
    except json.JSONDecodeError:
        pass

    # Tolerate trailing comma: strip a comma immediately before a closing brace.
    fixed = re.sub(r",\s*}", "}", candidate)
    try:
        obj = json.loads(fixed)
        if isinstance(obj, dict) and "verdict" in obj:
            return obj
    except json.JSONDecodeError:
        pass

    return None


def extract_from_log(log_text):
    """Parse an opencode JSONL event stream and return the verdict dict.

    Iterates ``type=="text"`` events, takes ``part.text``, and searches for
    a verdict object within it.  Returns ``None`` if no verdict is found.
    """
    if not log_text or not isinstance(log_text, str):
        return None

    for line in log_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "text":
            continue
        part = event.get("part", {})
        if part.get("type") != "text":
            continue
        raw = part.get("text", "")
        if not raw:
            continue

        # The text field may itself be a JSON-encoded string (escaped quotes
        # around the verdict).  Try to decode it first.
        candidate = raw
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, str):
                candidate = decoded
        except (json.JSONDecodeError, ValueError):
            pass

        verdict = extract_verdict(candidate)
        if verdict is not None:
            return verdict

    return None


def _cli():
    """CLI entry-point: parse-review LOGFILE OUTFILE."""
    if len(sys.argv) != 3:
        print("usage: parse-review LOGFILE OUTFILE", file=sys.stderr)
        sys.exit(2)

    logfile, outfile = sys.argv[1], sys.argv[2]

    try:
        with open(logfile, "r", encoding="utf-8") as fh:
            log_text = fh.read()
    except FileNotFoundError:
        print("parse-review: file not found: {}".format(logfile), file=sys.stderr)
        sys.exit(2)

    verdict = extract_from_log(log_text)
    if verdict is None:
        sys.exit(1)

    with open(outfile, "w", encoding="utf-8") as fh:
        json.dump(verdict, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


if __name__ == "__main__":
    _cli()
