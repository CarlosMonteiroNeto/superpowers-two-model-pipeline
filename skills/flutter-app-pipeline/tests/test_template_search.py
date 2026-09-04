import base64
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

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


def _pubspec_current(name):
    return 'name: {}\nenvironment:\n  sdk: ">=2.12.0 <4.0.0"\n'.format(name)


def _pubspec_dated(name):
    return 'name: {}\nenvironment:\n  sdk: ">=2.0.0 <3.0.0"\n'.format(name)


class StubGitHub:
    """Deterministic GitHub REST stub: serves canned search + repo data.

    search_map: {marker_substring: [full_name, ...]} - a search query whose
    decoded text contains the marker returns that repo list.
    repos: {full_name: {stars, created, commit_days, license, open, closed,
                        pubspec (str or None), readme (str)}}.
    """

    def __init__(self, search_map, repos):
        self.search_map = search_map
        self.repos = repos
        self._server = HTTPServer(("127.0.0.1", 0), self._make_handler())
        self.port = self._server.server_address[1]
        self.thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self._server.shutdown()
        self.thread.join(timeout=5)

    def base_url(self):
        return "http://127.0.0.1:{}".format(self.port)

    def _make_handler(self):
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    body = stub._route(self.path)
                    status = 200
                except KeyError:
                    body = b""
                    status = 404
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt, *args):
                pass

        return Handler

    def _route(self, path):
        parsed = urllib.parse.urlsplit(path)
        query = dict(urllib.parse.parse_qsl(parsed.query))
        segs = [s for s in parsed.path.split("/") if s]

        if segs[0] == "search" and segs[1] == "repositories":
            q = query.get("q", "")
            full_names = []
            for marker, names in self.search_map.items():
                if marker in q:
                    full_names = names
                    break
            items = []
            for name in full_names:
                r = self.repos[name]
                items.append({
                    "full_name": name,
                    "stargazers_count": r["stars"],
                    "license": {"spdx_id": r["license"]},
                    "created_at": r["created"],
                })
            return json.dumps({"items": items}).encode("utf-8")

        if segs[0] == "search" and segs[1] == "issues":
            q = query.get("q", "")
            name = None
            for full in self.repos:
                if full in q:
                    name = full
                    break
            if name is None:
                raise KeyError("unknown repo in issue query: " + q)
            state = "open" if "state:open" in q else "closed"
            count = self.repos[name]["open"] if state == "open" else self.repos[name]["closed"]
            return json.dumps({"total_count": count}).encode("utf-8")

        # /repos/{owner}/{repo}/...
        if segs[0] == "repos" and len(segs) >= 3:
            owner, repo = segs[1], segs[2]
            full = "{}/{}".format(owner, repo)
            if full not in self.repos:
                raise KeyError(full)
            r = self.repos[full]
            if len(segs) >= 4 and segs[3] == "commits":
                return json.dumps([{
                    "commit": {
                        "committer": {"date": r["commit_date"]},
                    },
                }]).encode("utf-8")
            if len(segs) >= 4 and segs[3] == "readme":
                if r.get("readme") is None:
                    raise KeyError(full + " readme")
                return json.dumps({
                    "content": base64.b64encode(r["readme"].encode("utf-8")).decode("ascii"),
                }).encode("utf-8")
            if len(segs) >= 5 and segs[3] == "contents" and segs[4] == "pubspec.yaml":
                if r.get("pubspec") is None:
                    raise KeyError(full + " pubspec")
                return json.dumps({
                    "content": base64.b64encode(r["pubspec"].encode("utf-8")).decode("ascii"),
                }).encode("utf-8")
            # /repos/{owner}/{repo}
            return json.dumps({
                "stargazers_count": r["stars"],
                "license": {"spdx_id": r["license"]},
                "created_at": r["created"],
            }).encode("utf-8")

        raise KeyError("unhandled path: " + path)


def _commit_date(days_ago):
    import datetime
    dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)
    return dt.isoformat()


def _created_years_ago(years):
    import datetime
    dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=int(years * 365))
    return dt.isoformat()


class TemplateSearchTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="pipeline-template-search-")
        self._stubs = []

    def tearDown(self):
        for stub in self._stubs:
            stub.stop()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _stub(self, search_map, repos):
        stub = StubGitHub(search_map, repos).start()
        self._stubs.append(stub)
        return stub

    def _run(self, args, stub, extra_env=None):
        env = {
            "GITHUB_API_BASE": stub.base_url(),
            "GITHUB_TOKEN": "test-token",
            "RTK_ENABLED": "0",
        }
        if extra_env:
            env.update(extra_env)
        return run_script("template-search", args, cwd=self._tmp, env_extra=env)


GOOD_REPO = {
    "stars": 1000,
    "created": _created_years_ago(1),
    "commit_date": _commit_date(5),
    "license": "mit",
    "open": 10,
    "closed": 90,
    "pubspec": _pubspec_current("good"),
    "readme": "# Shop\n\n## Install\n\n## Structure\n",
}

STALE_REPO = {
    "stars": 5,
    "created": _created_years_ago(10),
    "commit_date": _commit_date(400),
    "license": "none",
    "open": 60,
    "closed": 40,
    "pubspec": None,
    "readme": None,
}


# Note: tests below extend the base class so setUp/tearDown and helpers apply.


class TestStopRule(TemplateSearchTestBase):
    def test_specific_auto_approve_stops_at_three(self):
        """Specific category yields >=1 AUTO_APPROVE: keep collecting until 3
        are found, then STOP - the 4th candidate is never presented."""
        repos = {
            "good/shop_a": dict(GOOD_REPO),
            "good/shop_b": dict(GOOD_REPO),
            "good/shop_c": dict(GOOD_REPO),
            "good/shop_d": dict(GOOD_REPO),
        }
        stub = self._stub({"fashion pos": ["good/shop_a", "good/shop_b", "good/shop_c", "good/shop_d"]}, repos)
        r = self._run(["--specific", "women's fashion pos", "--generic", "pos"], stub)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = r.stdout
        self.assertIn("good/shop_a", out)
        self.assertIn("good/shop_b", out)
        self.assertIn("good/shop_c", out)
        self.assertNotIn("good/shop_d", out, "stop rule must halt at 3 AUTO_APPROVE candidates")
        self.assertEqual(out.count("AUTO_APPROVE"), 3, out)

    def test_fewer_than_three_presents_what_was_found(self):
        repos = {
            "good/shop_a": dict(GOOD_REPO),
            "good/shop_b": dict(GOOD_REPO),
        }
        stub = self._stub({"fashion pos": ["good/shop_a", "good/shop_b"]}, repos)
        r = self._run(["--specific", "women's fashion pos", "--generic", "pos"], stub)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("good/shop_a", r.stdout)
        self.assertIn("good/shop_b", r.stdout)


class TestSpecificNoAutoGenericFallback(TemplateSearchTestBase):
    def test_specific_50_69_and_generic_70_presented_together(self):
        """Specific yields no AUTO_APPROVE: collect specific 50-69 AND generic
        >=70, present both groups in one comparison table."""
        mid_repo = {
            "stars": 100,
            "created": _created_years_ago(5),
            "commit_date": _commit_date(5),
            "license": "mit",
            "open": 10,
            "closed": 90,
            "pubspec": None,
            "readme": "# Mid\n\n## Install\n\n## Structure\n",
        }
        repos = {
            "mid/shop_x": mid_repo,
            "good/shop_g": dict(GOOD_REPO),
        }
        stub = self._stub(
            {
                "fashion pos": ["mid/shop_x"],
                "pos": ["good/shop_g"],
            },
            repos,
        )
        r = self._run(["--specific", "women's fashion pos", "--generic", "pos"], stub)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = r.stdout
        self.assertIn("mid/shop_x", out, "specific 50-69 candidate must be presented")
        self.assertIn("good/shop_g", out, "generic >=70 candidate must be presented")
        self.assertIn("DEVELOPER_DECISION", out)
        self.assertIn("AUTO_APPROVE", out)

    def test_generic_only_presented_when_specific_group_empty(self):
        """If only the generic group has candidates, present it alone."""
        repos = {"good/shop_g": dict(GOOD_REPO)}
        stub = self._stub(
            {
                "fashion pos": [],
                "pos": ["good/shop_g"],
            },
            repos,
        )
        r = self._run(["--specific", "women's fashion pos", "--generic", "pos"], stub)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("good/shop_g", r.stdout)


class TestNoTemplate(TemplateSearchTestBase):
    def test_all_below_50_is_from_scratch(self):
        """Neither category yields anything >= 50: no template is adopted,
        the base is built from scratch (exit code signals it)."""
        repos = {"bad/shop_a": dict(STALE_REPO)}
        stub = self._stub(
            {
                "fashion pos": ["bad/shop_a"],
                "pos": ["bad/shop_a"],
            },
            repos,
        )
        r = self._run(["--specific", "women's fashion pos", "--generic", "pos"], stub)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        out = r.stdout
        self.assertNotIn("good/", out)


DATED_THRESHOLD_REPO = {
    "stars": 300,
    "created": _created_years_ago(5),
    "commit_date": _commit_date(100),
    "license": "mit",
    "open": 10,
    "closed": 90,
    "pubspec": _pubspec_dated("dated_shop"),
    "readme": "# Shop\n\n## Install\n\n## Structure\n",
}


class TestFlutterReadyDetection(TemplateSearchTestBase):
    """The suite must catch a regression of the headline flutter_ready
    feature: crossing AUTO_APPROVE (>= 70) depends on detection returning
    'dated' (10) rather than 'none' (0)."""

    def test_dated_pubspec_detected_and_totals_76(self):
        """stars 24 + recency 12 + issues 10 + sustained 10 + license 5 +
        readme 5 + flutter_ready dated 10 = 76 AUTO_APPROVE. With 'none'
        (0) the total would be 66 DEVELOPER_DECISION; with 'current' (20)
        it would be 86 - so the exact 76 pins the dated detection."""
        repos = {"mid/dated_shop": dict(DATED_THRESHOLD_REPO)}
        stub = self._stub({"fashion pos": ["mid/dated_shop"]}, repos)
        r = self._run(["--specific", "women's fashion pos", "--generic", "pos"], stub)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = r.stdout
        self.assertIn("mid/dated_shop", out)
        self.assertIn("76", out, "dated pubspec must total 76 (flutter_ready=10), got:\n" + out)
        self.assertIn("AUTO_APPROVE", out)

    def test_missing_pubspec_totals_66_developer_decision(self):
        """Same fixture with pubspec=None totals 66 (flutter_ready=0) and
        lands in the DEVELOPER_DECISION band - proves detection differs from
        the dated case."""
        repo = dict(DATED_THRESHOLD_REPO)
        repo["pubspec"] = None
        repos = {"mid/nopub_shop": repo}
        stub = self._stub({"fashion pos": ["mid/nopub_shop"]}, repos)
        r = self._run(["--specific", "women's fashion pos", "--generic", "pos"], stub)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = r.stdout
        self.assertIn("mid/nopub_shop", out)
        self.assertIn("66", out, "missing pubspec must total 66 (flutter_ready=0), got:\n" + out)
        self.assertIn("DEVELOPER_DECISION", out)


class TestUsage(TemplateSearchTestBase):
    def test_missing_arguments_is_usage(self):
        stub = self._stub({}, {})
        r = self._run(["--specific", "only-specific"], stub)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()