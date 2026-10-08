"""Extract an exact JSON task with its plan-wide execution contracts."""
import json
import pathlib
import sys


def extract(plan, number):
    tasks = plan.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("JSON plan must contain a tasks array")
    matches = [task for task in tasks if isinstance(task, dict) and str(task.get("id")) == str(number)]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one task with id {number}")
    # Preserve every task field and every shared constraint, including custom
    # contracts. Other tasks are deliberately omitted from this worker brief.
    brief = {key: value for key, value in plan.items() if key != "tasks"}
    brief["tasks"] = matches
    return json.dumps(brief, ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    try:
        plan = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
        text = extract(plan, sys.argv[2])
        pathlib.Path(sys.argv[3]).write_text(text, encoding="utf-8")
    except (OSError, ValueError, AttributeError) as exc:
        print(f"TASK-BRIEF: {exc}", file=sys.stderr)
        raise SystemExit(3)
