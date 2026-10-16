import re

TRIGGER_KEYWORDS = ["sequence diagram", "collaboration", "inheritance",
                    "composition", "encapsulation", "nielsen", "pour",
                    "fidelity", "uml"]
NON_TRIGGER_MARKERS = ["function points", "helm chart", "terraform"]

def load_text(path):
    return open(path, encoding="utf-8").read().lower()

def matches(text, intent):
    intent = intent.lower()
    return sum(1 for k in TRIGGER_KEYWORDS if k in text and k in intent) >= 1

def test_design_triggers():
    text = load_text("skills/design-oo-ux/SKILL.md")
    assert matches(text, "choose between sequence and collaboration diagram")
    assert matches(text, "inheritance versus composition decision")
    assert matches(text, "evaluate interface against Nielsen heuristics")
    assert not any(m in text for m in NON_TRIGGER_MARKERS)
