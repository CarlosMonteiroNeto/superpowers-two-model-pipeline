TRIGGER_KEYWORDS = ["definition of done", "sqa", "sqc", "iso 25010",
                    "compliance", "maturity", "pareto", "gqm", "audit",
                    "prevention", "appraisal"]
NON_TRIGGER_MARKERS = ["uml diagram", "terraform for s3", "sequence diagram"]

def load_text(path):
    return open(path, encoding="utf-8").read().lower()

def matches(text, intent):
    intent = intent.lower()
    return sum(1 for k in TRIGGER_KEYWORDS if k in text and k in intent) >= 1

def test_quality_triggers():
    text = load_text("skills/quality-gate/SKILL.md")
    assert matches(text, "define Definition of Done with ISO 25010 criteria")
    assert matches(text, "audit whether the team follows the documented process")
    assert matches(text, "classify prevention versus appraisal versus failure cost")
    assert not any(m in text for m in NON_TRIGGER_MARKERS)
