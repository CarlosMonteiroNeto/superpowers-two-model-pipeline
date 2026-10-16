TRIGGER_KEYWORDS = ["iaas", "paas", "saas", "ec2", "s3", "lambda",
                    "resilien", "shared responsibility", "iam"]
NON_TRIGGER_MARKERS = ["unit test with mocks", "retrospective", "invest"]

def load_text(path):
    return open(path, encoding="utf-8").read().lower()

def matches(text, intent):
    intent = intent.lower()
    return sum(1 for k in TRIGGER_KEYWORDS if k in text and k in intent) >= 1

def test_cloud_triggers():
    text = load_text("skills/cloud-deploy/SKILL.md")
    assert matches(text, "choose IaaS versus PaaS versus SaaS")
    assert matches(text, "map EC2 S3 Lambda to Azure and GCP equivalents")
    assert matches(text, "design resilient microservice deployment")
    assert not any(m in text for m in NON_TRIGGER_MARKERS)
