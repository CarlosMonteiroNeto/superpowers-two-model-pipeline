TRIGGER_KEYWORDS = ["backlog", "invest", "sprint", "retrospective",
                    "burndown", "planning poker", "dor", "dod"]
NON_TRIGGER_MARKERS = ["cyclomatic", "cloud storage tiers", "ec2"]

def load_text(path):
    return open(path, encoding="utf-8").read().lower()

def matches(text, intent):
    intent = intent.lower()
    return sum(1 for k in TRIGGER_KEYWORDS if k in text and k in intent) >= 1

def test_agile_triggers():
    text = load_text("skills/agile-loop/SKILL.md")
    assert matches(text, "refine the backlog with INVEST stories and DoR DoD")
    assert matches(text, "facilitate sprint planning daily review retro")
    assert matches(text, "estimate with planning poker and burndown")
    assert not any(m in text for m in NON_TRIGGER_MARKERS)
