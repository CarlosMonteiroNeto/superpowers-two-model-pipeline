"""Deterministic parser for the Reviewer's verdict from opencode event logs.

Provides two pure functions:
  extract_verdict(text)      – extract a verdict dict from reviewer reply text
  extract_from_log(log_text) – extract a verdict from an opencode JSONL event log

And a CLI entry-point when run as __main__.
"""

import json
import re
import sys


def _extract_brace_block(text, start):
    """Run a balanced-brace scan from *start* and return the matching slice,
    or None if no balanced block is found."""
    depth = 0
    in_string = False
    escape = False
    end = -1

    for i in range(start, len(text)):
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
    return text[start : end + 1]


def _try_parse_verdict(candidate):
    """Attempt to parse *candidate* as a JSON dict containing "verdict".
    Handles a single trailing comma before the final ``}``."""
    # Try as-is first.
    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict) and "verdict" in obj:
            return obj
    except json.JSONDecodeError:
        pass

    # Tolerate trailing comma: strip a comma (with any intervening
    # whitespace) immediately before the final ``}`` — one structural
    # repair only, anchored at the end of the string so commas inside
    # string literals are never touched.
    rstripped = candidate.rstrip()
    fixed = re.sub(r",\s*}$", "}", rstripped, count=1)
    try:
        obj = json.loads(fixed)
        if isinstance(obj, dict) and "verdict" in obj:
            return obj
    except json.JSONDecodeError:
        pass

    return None


def extract_verdict(text):
    """Return the verdict dict parsed from *text*, or None if absent.

    Iterates every ``{`` in *text*, runs a balanced-brace scan from each,
    and returns the first dict that contains ``"verdict"``.  Tolerates
    prose before/after the JSON, ``````json`` fences, a single trailing
    comma before the final ``}``, newlines inside strings, and unicode
    escapes.
    """
    if not text or not isinstance(text, str):
        return None

    # Strip ```json ... ``` fences if present (take the innermost block).
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)

    # Iterate every opening brace position – the verdict dict may not be
    # the first `{` in the text (e.g. prose containing braces).
    idx = 0
    while True:
        start = text.find("{", idx)
        if start == -1:
            break

        candidate = _extract_brace_block(text, start)
        if candidate is not None:
            verdict = _try_parse_verdict(candidate)
            if verdict is not None:
                return verdict

        # Advance past this position to try the next `{`.
        idx = start + 1

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
    except (FileNotFoundError, OSError) as exc:
        print("parse-review: cannot read logfile: {}: {}".format(logfile, exc), file=sys.stderr)
        sys.exit(1)

    verdict = extract_from_log(log_text)
    if verdict is None:
        sys.exit(1)

    try:
        with open(outfile, "w", encoding="utf-8") as fh:
            json.dump(verdict, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    except OSError as exc:
        print("parse-review: cannot write outfile: {}: {}".format(outfile, exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    _cli()
