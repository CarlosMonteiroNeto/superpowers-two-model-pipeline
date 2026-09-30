"""R3 publication policy behavior."""
import importlib.util
import pathlib
import subprocess
import unittest
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[3]
SCRIPT=ROOT/"skills"/"two-model-sdd-pipeline"/"scripts"/"publication.py"
spec=importlib.util.spec_from_file_location("r35_publication",SCRIPT)
publication=importlib.util.module_from_spec(spec); spec.loader.exec_module(publication)


class PublicationTests(unittest.TestCase):
    def test_local_policy_never_pushes(self):
        with mock.patch.object(publication.subprocess,"run") as run:
            result=publication.publish("repo","feature","main","local")
        self.assertEqual(result["status"],"local_only"); run.assert_not_called()

    def test_pull_request_reuses_existing_pr_without_merge(self):
        existing=subprocess.CompletedProcess([],0,'[{"number":12,"url":"https://example.invalid/pr/12"}]','')
        with mock.patch.object(publication.subprocess,"run",side_effect=[subprocess.CompletedProcess([],0,"",""),existing]) as run:
            result=publication.publish("repo","feature","main","pull_request")
        self.assertEqual(result["status"],"pull_request_exists")
        self.assertEqual(run.call_count,2)
        self.assertEqual(run.call_args_list[0].args[0], ["git","push","-u","origin","feature"])
        self.assertFalse(any("merge" in str(call.args[0]) for call in run.call_args_list))

    def test_new_pull_request_uses_recorded_target(self):
        found=subprocess.CompletedProcess([],0,"[]","")
        created=subprocess.CompletedProcess([],0,"https://example.invalid/pr/13\n","")
        with mock.patch.object(publication.subprocess,"run",side_effect=[subprocess.CompletedProcess([],0,"",""),found,created]) as run:
            result=publication.publish("repo","feature","release","pull_request")
        self.assertEqual(result["url"],"https://example.invalid/pr/13")
        self.assertEqual(run.call_args_list[-1].args[0], ["gh","pr","create","--fill","--base","release"])

    def test_publication_refuses_head_different_from_reviewed_candidate(self):
        with mock.patch.object(publication.subprocess, "run", return_value=subprocess.CompletedProcess(
                ["git", "rev-parse", "HEAD"], 0, "f" * 40 + "\n", "")) as run:
            with self.assertRaisesRegex(ValueError, "HEAD changed"):
                publication.publish("repo", "feature", "main", "pull_request",
                                    expected_head="a" * 40)
        self.assertEqual(run.call_count, 1)


if __name__=="__main__": unittest.main()
