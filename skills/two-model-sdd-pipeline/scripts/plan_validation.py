"""Strict validation for executable canonical pipeline plans."""
import os
import re

TASK_REQUIRED = {"id", "title", "summary", "spec_refs", "touches", "depends_on", "acceptance"}
ROOT_REQUIRED = {"version", "title", "spec_doc", "global_constraints", "interfaces", "verification", "tasks"}
FORBIDDEN_CONTROLS = {"runtime", "model", "reasoning", "reasoning_effort", "backend", "executable", "approval", "force_approve"}


def _fail(message):
    raise ValueError("invalid plan: " + message)


def _relative(path, label):
    if not isinstance(path, str) or not path.strip() or "\\" in path:
        _fail("{} must be a canonical relative POSIX path".format(label))
    path = path.strip()
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path) or any(p in ("", ".", "..") for p in path.split("/")):
        _fail("{} escapes or aliases the repository: {}".format(label, path))
    return path


def validate_plan(plan: dict, repo_root: str) -> None:
    if not isinstance(plan, dict):
        _fail("root must be an object")
    missing = ROOT_REQUIRED - plan.keys()
    if missing:
        _fail("missing root fields: {}".format(", ".join(sorted(missing))))
    if isinstance(plan.get("version"), bool) or plan.get("version") != 1:
        _fail("unsupported plan version")
    if not isinstance(plan.get("title"), str) or not plan["title"].strip():
        _fail("title must be a non-empty string")
    if not _strings(plan.get("global_constraints")):
        _fail("global_constraints must be a non-empty string list")
    if not isinstance(plan.get("interfaces"), dict):
        _fail("interfaces must be an object")
    def reject_controls(value, location="plan"):
        if isinstance(value, dict):
            for key, child in value.items():
                if key.casefold() in FORBIDDEN_CONTROLS:
                    _fail("unsupported execution control: {}.{}".format(location, key))
                reject_controls(child, location + "." + key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                reject_controls(child, "{}[{}]".format(location, index))
    reject_controls(plan)
    root = os.path.realpath(repo_root)
    spec_doc = _relative(plan["spec_doc"], "spec_doc")
    _check_file(root, spec_doc)
    verification = plan.get("verification", {})
    if not isinstance(verification, dict):
        _fail("verification must be an object")
    if "toolchains" in verification and (not isinstance(verification["toolchains"], list) or not verification["toolchains"]):
        _fail("verification.toolchains must be a non-empty list")
    if not isinstance(verification.get("new_test_files", []), list):
        _fail("verification.new_test_files must be a list")
    toolchain_ids = set()
    for desc in verification.get("toolchains", []):
        if not isinstance(desc, dict) or not desc.get("id") or not desc.get("language"):
            _fail("toolchain descriptor requires id and language")
        if desc["id"] in toolchain_ids:
            _fail("duplicate toolchain id: {}".format(desc["id"]))
        toolchain_ids.add(desc["id"])
        for mode in ("test", "analyze", "format"):
            item = desc.get(mode)
            if item is not None:
                if (not isinstance(item, dict) or not isinstance(item.get("argv"), list)
                        or not item["argv"] or not all(isinstance(a, str) and a and "\0" not in a for a in item["argv"])
                        or not isinstance(item.get("cwd", "."), str)):
                    _fail("toolchain {} has invalid {} descriptor".format(desc["id"], mode))
                cwd = item.get("cwd", ".")
                if cwd != ".": _canonical_path(root, cwd, "toolchain cwd")
    new_tests = [_canonical_path(root, p, "new_test_files") for p in verification.get("new_test_files", [])]
    all_paths = list(new_tests)
    tasks = plan["tasks"]
    if not isinstance(tasks, list) or not tasks:
        _fail("tasks must be a non-empty list")
    ids = []
    seen_paths = {}
    for path in new_tests:
        _claim(path, seen_paths)
    for task in tasks:
        if not isinstance(task, dict) or TASK_REQUIRED - task.keys():
            _fail("every task requires {}".format(", ".join(sorted(TASK_REQUIRED))) )
        tid = task["id"]
        if isinstance(tid, bool) or not isinstance(tid, int) or tid < 1:
            _fail("task IDs must be positive integers")
        ids.append(tid)
        for field in ("title", "summary"):
            if not isinstance(task[field], str) or not task[field].strip():
                _fail("task {} requires {}".format(tid, field))
        if not _strings(task["acceptance"]) or not _strings(task["spec_refs"]):
            _fail("task {} acceptance and spec_refs must be non-empty string lists".format(tid))
        if not isinstance(task["depends_on"], list):
            _fail("task {} depends_on must be a list".format(tid))
        task_verification = task.get("verification")
        if task_verification is not None:
            if not isinstance(task_verification, dict) or not isinstance(task_verification.get("new_test_files", []), list):
                _fail("task {} verification metadata is invalid".format(tid))
            if "command" in task_verification and (not isinstance(task_verification["command"], str) or not task_verification["command"].strip()):
                _fail("task {} verification command is invalid".format(tid))
            for test_path in task_verification.get("new_test_files", []):
                test_path = _canonical_path(root, test_path, "task {} new_test_files".format(tid))
                _claim(test_path, seen_paths)
                all_paths.append(test_path)
        paths = task["touches"]
        if not isinstance(paths, list):
            _fail("task {} touches must be a list".format(tid))
        for path in paths:
            path = _canonical_path(root, path, "task {} touches".format(tid))
            _claim(path, seen_paths)
            all_paths.append(path)
        for ref in task["spec_refs"]:
            if not isinstance(ref, str) or "#" not in ref:
                _fail("task {} has invalid spec ref".format(tid))
            file, anchor = ref.split("#", 1)
            file = _relative(file, "spec ref")
            content = _check_file(root, file)
            headings = {_heading_slug(m.group(1)) for m in re.finditer(r"^#{1,6}\s+(.+?)\s*#*\s*$", content, re.M)}
            if anchor.lower() not in headings and anchor not in ("",):
                _fail("missing spec anchor {}#{}".format(file, anchor))
    if len(ids) != len(set(ids)) or sorted(ids) != list(range(1, len(ids) + 1)):
        _fail("task IDs must be unique and consecutive from 1")
    known = set(ids)
    graph = {}
    for task in tasks:
        tid = task["id"]
        deps = task["depends_on"]
        if any(isinstance(d, bool) or not isinstance(d, int) or d not in known or d == tid for d in deps) or len(deps) != len(set(deps)):
            _fail("task {} has invalid dependencies".format(tid))
        graph[tid] = deps
    visiting, visited = set(), set()
    def visit(node):
        if node in visiting: _fail("dependency cycle")
        if node in visited: return
        visiting.add(node)
        for dep in graph[node]: visit(dep)
        visiting.remove(node); visited.add(node)
    for node in graph: visit(node)
    return plan


def _strings(value):
    return isinstance(value, list) and bool(value) and all(isinstance(x, str) and x.strip() for x in value)


def _heading_slug(heading):
    # GitHub removes punctuation but turns each whitespace character into a
    # hyphen. Thus the roadmap's "D07 — Reuse" is `d07--reuse`, not `d07-reuse`.
    heading = heading.strip().lower()
    heading = re.sub(r"[^\w\s-]", "", heading, flags=re.UNICODE)
    return re.sub(r"\s", "-", heading).strip("-")


def _claim(path, seen):
    key = os.path.normcase(path)
    if key in seen and seen[key] != path:
        _fail("case/path alias: {} and {}".format(seen[key], path))
    seen[key] = path


def _canonical_path(root, path, label):
    path = _relative(path, label)
    absolute = os.path.realpath(os.path.join(root, *path.split("/")))
    try:
        if os.path.commonpath((root, absolute)) != root:
            _fail("{} resolves outside the repository: {}".format(label, path))
    except ValueError:
        _fail("{} resolves outside the repository: {}".format(label, path))
    return os.path.relpath(absolute, root).replace(os.sep, "/")


def _check_file(root, relative):
    path = os.path.realpath(os.path.join(root, *relative.split("/")))
    if os.path.commonpath((root, path)) != root or not os.path.isfile(path):
        _fail("missing or escaping spec file: {}".format(relative))
    with open(path, encoding="utf-8") as f:
        return f.read()
