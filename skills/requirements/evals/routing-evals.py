import re

TRIGGER_KEYWORDS = ["requirements", "elicit", "nfr", "ambigu", "untestable",
                    "invest", "acceptance", "trade-off", "validation"]
NON_TRIGGER_MARKERS = ["dockerfile", "mutation", "terraform", "kubernetes"]

def load_text(path):
    return open(path, encoding="utf-8").read().lower()

def matches(text, intent):
    intent = intent.lower()
    return sum(1 for k in TRIGGER_KEYWORDS if k in text and k in intent) >= 1

def test_requirements_triggers():
    text = load_text("skills/requirements/SKILL.md")
    assert matches(text, "requirements are ambiguous and untestable")
    assert matches(text, "elicit NFR trade-offs for architecture")
    assert matches(text, "validate INVEST story criteria")
    assert not any(m in text for m in NON_TRIGGER_MARKERS)
