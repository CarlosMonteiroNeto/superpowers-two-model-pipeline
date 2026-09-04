import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from parse_review import extract_verdict, extract_from_log

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"

if os.name == "nt":
    git_bash = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
    BASH = str(git_bash) if git_bash.exists() else "bash"
else:
    BASH = "bash"


def run_script(script, args, cwd, env_extra):
    env = dict(os.environ)
    env.update(env_extra)
    return subprocess.run(
        [BASH, str(SCRIPTS / script), *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
    )


VERDICT_JSON = json.dumps({
    "verdict": "APPROVED",
    "findings": [],
    "minors": ["note one"],
    "summary": "All good.",
})


def review_log_lines(text, extra_events=True):
    lines = []
    if extra_events:
        lines.append('{"type":"step_start","sessionID":"ses_x","part":{"type":"step-start"}}')
    lines.append('{"type":"text","sessionID":"ses_x","part":{"type":"text","text":' +
                 json.dumps(text) + '}}')
    if extra_events:
        lines.append('{"type":"step_finish","sessionID":"ses_x","part":{"reason":"stop"}}')
    return lines


class TestExtractVerdict(unittest.TestCase):
    def test_extracts_well_formed_verdict(self):
        text = "Here is my review.\n```json\n" + VERDICT_JSON + "\n```\n"
        self.assertEqual(extract_verdict(text), json.loads(VERDICT_JSON))

    def test_extracts_verdict_without_fences(self):
        text = "My review:\n" + VERDICT_JSON
        self.assertEqual(extract_verdict(text), json.loads(VERDICT_JSON))

    def test_tolerates_prose_around_json(self):
        text = "All evidence gathered. Final review:\n" + VERDICT_JSON + "\nThat is all."
        self.assertEqual(extract_verdict(text), json.loads(VERDICT_JSON))

    def test_tolerates_trailing_comma(self):
        malformed = VERDICT_JSON[:-1] + ",\n}"
        text = "```json\n" + malformed + "\n```\n"
        self.assertEqual(extract_verdict(text), json.loads(VERDICT_JSON))

    def test_tolerates_unicode_escapes_in_text(self):
        summary = "Sections \u00a75\u2192\u00a77 covered."
        verdict = json.loads(VERDICT_JSON)
        verdict["summary"] = summary
        text = "Review: " + json.dumps(verdict)
        self.assertEqual(extract_verdict(text), verdict)

    def test_no_verdict_returns_none(self):
        text = "No structured verdict here, just prose."
        self.assertIsNone(extract_verdict(text))


class TestExtractFromLog(unittest.TestCase):
    def test_finds_verdict_in_text_event(self):
        lines = review_log_lines("Review follows.\n" + VERDICT_JSON)
        self.assertEqual(extract_from_log("\n".join(lines)), json.loads(VERDICT_JSON))

    def test_unescapes_embedded_json(self):
        # The reviewer's reply is a raw JSON string; the log line embeds it as
        # the text field (escaped once), so extract_from_log must locate the
        # verdict object inside the unescaped text.
        log_line = json.dumps({
            "type": "text",
            "sessionID": "ses_x",
            "part": {"type": "text", "text": VERDICT_JSON},
        })
        self.assertEqual(extract_from_log(log_line), json.loads(VERDICT_JSON))

    def test_no_verdict_in_log_returns_none(self):
        lines = ['{"type":"text","sessionID":"ses_x","part":{"type":"text","text":"no verdict here"}}']
        self.assertIsNone(extract_from_log("\n".join(lines)))

    def test_empty_log_returns_none(self):
        self.assertIsNone(extract_from_log(""))


class TestParseReviewScript(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="parse-review-tests-"))

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_writes_verdict_file(self):
        log = self._tmp / "task-3-reviewer.log"
        log.write_text("\n".join(review_log_lines("Verdict:\n" + VERDICT_JSON)) + "\n", encoding="utf-8")
        out = self._tmp / "task-3-review.json"
        r = run_script("parse-review", [str(log), str(out)], cwd=self._tmp, env_extra={})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(out.exists())
        self.assertEqual(json.loads(out.read_text(encoding="utf-8")), json.loads(VERDICT_JSON))

    def test_no_verdict_exits_1(self):
        log = self._tmp / "task-3-reviewer.log"
        log.write_text('{"type":"text","sessionID":"s","part":{"type":"text","text":"plain"}}\n', encoding="utf-8")
        out = self._tmp / "task-3-review.json"
        r = run_script("parse-review", [str(log), str(out)], cwd=self._tmp, env_extra={})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertFalse(out.exists())

    def test_usage_exits_2(self):
        r = run_script("parse-review", [], cwd=self._tmp, env_extra={})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()