TRIGGER_KEYWORDS = ["cohesion", "coupling", "pure function", "global",
                    "modular", "input validation", "top-down", "pseudocode"]
NON_TRIGGER_MARKERS = ["retrospective", "iaas", "paas"]

def load_text(path):
    return open(path, encoding="utf-8").read().lower()

def matches(text, intent):
    intent = intent.lower()
    return sum(1 for k in TRIGGER_KEYWORDS if k in text and k in intent) >= 1

def test_coding_triggers():
    text = load_text("skills/coding-standards/SKILL.md")
    assert matches(text, "split this module for high cohesion low coupling")
    assert matches(text, "avoid mutating globals, return values instead")
    assert matches(text, "review types, scope, and input validation")
    assert not any(m in text for m in NON_TRIGGER_MARKERS)
