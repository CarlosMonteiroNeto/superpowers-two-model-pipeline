"""Resolve applicable versioned product requirement profiles deterministically."""


def _matches(context, applicability):
    if not isinstance(applicability, dict):
        raise ValueError("profile applicability must be an object")
    for key, expected in applicability.items():
        actual = context.get(key)
        if isinstance(expected, dict):
            if "equals" in expected and actual != expected["equals"]:
                return False
            if "in" in expected and actual not in expected["in"]:
                return False
            if set(expected) - {"equals", "in"}:
                raise ValueError("unsupported applicability operator for {}".format(key))
        elif actual != expected:
            return False
    return True


def _validate_requirement(requirement, profile_id):
    if not isinstance(requirement, dict):
        raise ValueError("requirements must be objects")
    required = ("id", "description", "checks", "dependencies")
    if any(key not in requirement for key in required):
        raise ValueError("profile {} has an incomplete requirement".format(profile_id))
    if not isinstance(requirement["id"], str) or not requirement["id"]:
        raise ValueError("requirement id must be non-empty")
    if not isinstance(requirement["description"], str) or not requirement["description"]:
        raise ValueError("requirement description must be non-empty")
    for key in ("checks", "dependencies"):
        value = requirement[key]
        if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
            raise ValueError("requirement {} must be a list of non-empty strings".format(key))


def resolve(context, profiles):
    """Return applicable requirements, reasoned opt-outs, and conflicts/questions."""
    if not isinstance(context, dict):
        raise ValueError("context must be an object")
    if not isinstance(profiles, list):
        raise ValueError("profiles must be a list")
    selected_profiles = []
    seen_profiles = set()
    for profile in profiles:
        if not isinstance(profile, dict):
            raise ValueError("profiles must contain objects")
        profile_id = profile.get("profile_id")
        version = profile.get("version")
        if not isinstance(profile_id, str) or not profile_id or not isinstance(version, str) or not version:
            raise ValueError("profile_id and version are required")
        if profile_id in seen_profiles:
            raise ValueError("duplicate profile_id: {}".format(profile_id))
        seen_profiles.add(profile_id)
        requirements = profile.get("requirements")
        if not isinstance(requirements, list):
            raise ValueError("profile requirements must be a list")
        for requirement in requirements:
            _validate_requirement(requirement, profile_id)
        if _matches(context, profile.get("applicability", {})):
            selected_profiles.append(profile)

    owners = {}
    questions = []
    for profile in sorted(selected_profiles, key=lambda item: item["profile_id"]):
        for requirement in profile["requirements"]:
            item = dict(requirement)
            item["profile_id"] = profile["profile_id"]
            item["profile_version"] = profile["version"]
            owners.setdefault(item["id"], []).append(item)

    requirements = []
    for requirement_id in sorted(owners):
        candidates = owners[requirement_id]
        signatures = {(item["description"], tuple(item["checks"]), tuple(item["dependencies"])) for item in candidates}
        if len(signatures) > 1:
            questions.append({
                "type": "profile_conflict",
                "requirement_id": requirement_id,
                "profiles": [item["profile_id"] for item in candidates],
                "reason": "applicable profiles define conflicting requirements",
            })
            continue
        requirements.append(candidates[0])

    opt_outs = context.get("opt_outs", {})
    if not isinstance(opt_outs, dict):
        raise ValueError("context.opt_outs must be an object")
    exceptions = []
    retained = []
    for requirement in requirements:
        reason = opt_outs.get(requirement["id"])
        if reason is None:
            retained.append(requirement)
        elif not isinstance(reason, str) or not reason.strip():
            questions.append({"type": "opt_out_reason_required", "requirement_id": requirement["id"]})
            retained.append(requirement)
        else:
            exceptions.append({"requirement_id": requirement["id"], "reason": reason.strip(), "profile_id": requirement["profile_id"]})

    # Find strongly connected components in the selected dependency graph.
    by_id = {item["id"]: item for item in retained}
    indexes = {}
    lowlinks = {}
    stack = []
    on_stack = set()
    cycles = []
    next_index = [0]

    def visit(node):
        indexes[node] = lowlinks[node] = next_index[0]
        next_index[0] += 1
        stack.append(node)
        on_stack.add(node)
        for dependency in sorted(by_id[node]["dependencies"]):
            if dependency not in by_id:
                continue
            if dependency not in indexes:
                visit(dependency)
                lowlinks[node] = min(lowlinks[node], lowlinks[dependency])
            elif dependency in on_stack:
                lowlinks[node] = min(lowlinks[node], indexes[dependency])
        if lowlinks[node] == indexes[node]:
            component = []
            while True:
                member = stack.pop()
                on_stack.remove(member)
                component.append(member)
                if member == node:
                    break
            if len(component) > 1 or node in by_id[node]["dependencies"]:
                cycles.append(sorted(component))

    for requirement_id in sorted(by_id):
        if requirement_id not in indexes:
            visit(requirement_id)

    cyclic_ids = {item for cycle in cycles for item in cycle}
    if cycles:
        questions.extend({"type": "dependency_cycle", "requirement_ids": cycle}
                         for cycle in sorted(cycles))

    unavailable = set(cyclic_ids)
    unresolved = {}
    changed = True
    while changed:
        changed = False
        for requirement in retained:
            requirement_id = requirement["id"]
            if requirement_id in unavailable:
                continue
            missing = sorted(set(requirement["dependencies"]) & unavailable)
            # Unknown and conflicted/opted-out requirements are unavailable too.
            missing.extend(sorted(set(requirement["dependencies"]) - set(by_id)))
            missing = sorted(set(missing))
            if missing:
                unresolved[requirement_id] = missing
                unavailable.add(requirement_id)
                changed = True

    questions.extend({"type": "unresolved_dependency", "requirement_id": requirement_id,
                      "dependencies": dependencies}
                     for requirement_id, dependencies in sorted(unresolved.items()))
    retained = [item for item in retained if item["id"] not in unavailable]
    return {"requirements": retained, "exceptions": exceptions, "questions": questions,
            "profiles": [{"profile_id": item["profile_id"], "version": item["version"]}
                         for item in sorted(selected_profiles, key=lambda item: item["profile_id"])]}
