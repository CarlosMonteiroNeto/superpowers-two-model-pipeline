TRIGGER_KEYWORDS = ["partition", "boundary value", "base-path", "first",
                    "tdd", "smoke", "regression", "ieee 829", "red"]
NON_TRIGGER_MARKERS = ["invest", "vpc network", "user story"]

def load_text(path):
    return open(path, encoding="utf-8").read().lower()

def matches(text, intent):
    intent = intent.lower()
    return sum(1 for k in TRIGGER_KEYWORDS if k in text and k in intent) >= 1

def test_verification_triggers():
    text = load_text("skills/verification-test/SKILL.md")
    assert matches(text, "design test cases by partition and boundary values")
    assert matches(text, "scaffold a FIRST TDD Red test")
    assert matches(text, "select smoke and regression candidates for automation")
    assert not any(m in text for m in NON_TRIGGER_MARKERS)
