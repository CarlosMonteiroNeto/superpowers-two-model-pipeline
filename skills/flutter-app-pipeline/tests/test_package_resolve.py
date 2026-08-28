import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from graphify_package import resolve_package_dir


def make_config(packages):
    return {"configVersion": 2, "packages": packages}


class TestResolvePackageDir(unittest.TestCase):
    def test_resolves_absolute_file_uri(self):
        config = make_config([
            {"name": "url_launcher", "rootUri": "file:///C:/Users/me/Pub/Cache/hosted/pub.dev/url_launcher-6.3.2/", "packageUri": "lib/", "languageVersion": "3.3"},
        ])
        result = resolve_package_dir(config, "url_launcher")
        expected = os.path.normpath("C:/Users/me/Pub/Cache/hosted/pub.dev/url_launcher-6.3.2")
        self.assertEqual(os.path.normpath(result), expected)

    def test_resolves_relative_root_uri_against_base(self):
        config = make_config([
            {"name": "my_pkg", "rootUri": "../packages/my_pkg/", "packageUri": "lib/", "languageVersion": "3.3"},
        ])
        base = os.path.normpath("C:/proj/app")
        result = resolve_package_dir(config, "my_pkg", base_dir=base)
        expected = os.path.normpath("C:/proj/packages/my_pkg")
        self.assertEqual(os.path.normpath(result), expected)

    def test_missing_package_raises(self):
        config = make_config([{"name": "other", "rootUri": "file:///x/", "packageUri": "lib/"}])
        with self.assertRaises(KeyError):
            resolve_package_dir(config, "does_not_exist")

    def test_plain_path_root_uri(self):
        config = make_config([
            {"name": "local", "rootUri": "C:/vendor/local/", "packageUri": "lib/", "languageVersion": "3.3"},
        ])
        result = resolve_package_dir(config, "local")
        self.assertEqual(os.path.normpath(result), os.path.normpath("C:/vendor/local"))


if __name__ == "__main__":
    unittest.main()