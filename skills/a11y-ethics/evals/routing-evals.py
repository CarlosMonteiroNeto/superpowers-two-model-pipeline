TRIGGER_KEYWORDS = ["nielsen", "wcag", "pour", "screen reader",
                    "consent", "bias", "heuristic", "satisfaction"]
NON_TRIGGER_MARKERS = ["story points", "database migration", "burndown"]

def load_text(path):
    return open(path, encoding="utf-8").read().lower()

def matches(text, intent):
    intent = intent.lower()
    return sum(1 for k in TRIGGER_KEYWORDS if k in text and k in intent) >= 1

def test_a11y_triggers():
    text = load_text("skills/a11y-ethics/SKILL.md")
    assert matches(text, "audit this interface against Nielsen heuristics and WCAG")
    assert matches(text, "check POUR accessibility with screen reader support")
    assert matches(text, "review personalization for bias and consent risks")
    assert not any(m in text for m in NON_TRIGGER_MARKERS)
