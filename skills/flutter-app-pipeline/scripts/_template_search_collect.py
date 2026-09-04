#!/usr/bin/env python3
"""Collect and score template candidates for template-search orchestrator.

Called by the template-search bash script. Outputs a JSON dict with:
  - presentation: list of scored candidates to display
  - exit_code: 0 (candidates), 1 (from-scratch), 2 (usage error)
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from template_score import collect_candidates


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Collect template candidates")
    parser.add_argument("--specific", required=True, help="Specific-category search query")
    parser.add_argument("--generic", required=True, help="Generic-category fallback search query")
    parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN"))
    args = parser.parse_args()

    result = collect_candidates(args.specific, args.generic, args.github_token)
    presentation = result.get("presentation", [])

    if not presentation:
        result["exit_code"] = 1
    else:
        result["exit_code"] = 0

    print(json.dumps(result, indent=2))
    sys.exit(result["exit_code"])


if __name__ == "__main__":
    main()
