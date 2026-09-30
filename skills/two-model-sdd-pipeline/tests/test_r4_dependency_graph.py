"""Behavioral contracts for the isolated Graphify dependency adapter."""

import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "two-model-sdd-pipeline" / "scripts"
BUILDER_PATH = SCRIPTS / "test_dependency_graph.py"


def load_builder(test):
    test.assertTrue(BUILDER_PATH.is_file(), "R4 requires test_dependency_graph.build")
    spec = importlib.util.spec_from_file_location("r4_test_dependency_graph", BUILDER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    test.assertTrue(callable(getattr(module, "build", None)))
    return module


def py_graph():
    return {
        "nodes": [
            {"id": "app", "label": "app.py", "file_type": "code", "source_file": "app.py", "_origin": "ast"},
            {"id": "util", "label": "util.py", "file_type": "code", "source_file": "util.py", "_origin": "ast"},
            {"id": "tests_test_app", "label": "test_app.py", "file_type": "code", "source_file": "tests/test_app.py", "_origin": "ast"},
        ],
        "edges": [
            {"source": "app", "target": "util", "relation": "imports_from", "source_file": "app.py", "_origin": "ast"},
            {"source": "app", "target": "json", "relation": "imports", "source_file": "app.py", "_origin": "ast"},
            {"source": "app", "target": "requests", "relation": "imports_from", "source_file": "app.py", "_origin": "ast"},
            {"source": "tests_test_app", "target": "app", "relation": "imports", "source_file": "tests/test_app.py", "_origin": "ast"},
        ],
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }


def dart_graph(target_package="probe", external_package="flutter_test"):
    local_target = "package:%s/app.dart" % target_package
    external_target = "package:%s/flutter_test.dart" % external_package
    return {
        "nodes": [
            {"id": "lib_app", "label": "app.dart", "file_type": "code", "source_file": "lib/app.dart", "_origin": "ast"},
            {"id": "lib_normalizer", "label": "normalizer.dart", "file_type": "code", "source_file": "lib/normalizer.dart", "_origin": "ast"},
            {"id": "test_app", "label": "app_test.dart", "file_type": "code", "source_file": "test/app_test.dart", "_origin": "ast"},
            {"id": "normalizer_dart", "label": "normalizer.dart", "file_type": "code", "source_file": None, "_origin": "ast"},
            {"id": "package_probe_app", "label": local_target, "file_type": "code", "source_file": None, "_origin": "ast"},
            {"id": "package_flutter_test", "label": external_target, "file_type": "code", "source_file": None, "_origin": "ast"},
        ],
        "edges": [
            {"source": "lib_app", "target": "normalizer_dart", "relation": "imports", "source_file": "lib/app.dart", "_origin": "ast"},
            {"source": "test_app", "target": "package_probe_app", "relation": "imports", "source_file": "test/app_test.dart", "_origin": "ast"},
            {"source": "test_app", "target": "package_flutter_test", "relation": "imports", "source_file": "test/app_test.dart", "_origin": "ast"},
        ],
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }


class GraphifyRunner:
    def __init__(self, graph, version="0.9.50", update_status=0):
        self.graph = graph
        self.version = version
        self.update_status = update_status
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), dict(kwargs)))
        if argv == ["graphify", "--version"]:
            return subprocess.CompletedProcess(argv, 0, "graphify %s\n" % self.version, "")
        if (len(argv) == 7 and argv[0:2] == ["graphify", "extract"]
                and argv[3:6] == ["--code-only", "--no-cluster", "--out"]):
            output_root = pathlib.Path(argv[6])
            output = output_root / "graphify-out" / "graph.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(self.graph), encoding="utf-8")
            return subprocess.CompletedProcess(argv, self.update_status, "raw AST graph written\n", "")
        return subprocess.CompletedProcess(argv, 2, "", "unexpected Graphify command")


class TestR4DependencyGraph(unittest.TestCase):
    def test_python_graph_maps_transitive_local_imports_and_ignores_declared_external_modules(self):
        builder = load_builder(self)
        with tempfile.TemporaryDirectory() as temp:
            snapshot = pathlib.Path(temp)
            (snapshot / "tests").mkdir()
            (snapshot / "app.py").write_text("import json\nfrom requests import get\nfrom util import clean\n", encoding="utf-8")
            (snapshot / "util.py").write_text("def clean(value): return value.strip()\n", encoding="utf-8")
            (snapshot / "tests" / "test_app.py").write_text("from app import run\n", encoding="utf-8")
            (snapshot / "pyproject.toml").write_text(
                '[project]\nname = "sample"\ndependencies = ["requests>=2"]\n', encoding="utf-8"
            )
            runner = GraphifyRunner(py_graph())
            with mock.patch.object(builder.subprocess, "run", side_effect=runner):
                result = builder.build(snapshot, "0.9.50")

            self.assertTrue(result["complete"], result["diagnostics"])
            self.assertEqual(result["reverse_edges"], {
                "app.py": ["tests/test_app.py"],
                "util.py": ["app.py"],
            })
            self.assertEqual(result["graphify_version"], "0.9.50")
            self.assertRegex(result["graph_digest"], r"^[0-9a-f]{64}$")
            self.assertEqual([call[0][1] for call in runner.calls], ["--version", "extract"])
            self.assertEqual(runner.calls[1][0], [
                "graphify", "extract", str(snapshot.resolve()), "--code-only", "--no-cluster", "--out",
                str((snapshot / ".r4-graphify-output").resolve()),
            ])
            self.assertEqual(runner.calls[1][1]["shell"], False)
            self.assertTrue((snapshot / ".r4-graphify-output" / "graphify-out" / "graph.json").is_file())

    def test_graphify_package_metadata_node_is_not_mistaken_for_missing_source_code(self):
        builder = load_builder(self)
        graph = py_graph()
        graph["nodes"].append({
            "id": "pkg_sample", "label": "sample", "file_type": "code", "type": "package",
            "source_file": "pyproject.toml", "source_location": "L1", "_origin": "ast",
        })
        with tempfile.TemporaryDirectory() as temp:
            snapshot = pathlib.Path(temp)
            (snapshot / "tests").mkdir()
            (snapshot / "app.py").write_text("from util import clean\n", encoding="utf-8")
            (snapshot / "util.py").write_text("def clean(value): return value\n", encoding="utf-8")
            (snapshot / "tests" / "test_app.py").write_text("from app import run\n", encoding="utf-8")
            (snapshot / "pyproject.toml").write_text(
                '[project]\nname = "sample"\ndependencies = ["requests>=2"]\n', encoding="utf-8"
            )
            with mock.patch.object(builder.subprocess, "run", side_effect=GraphifyRunner(graph)):
                result = builder.build(snapshot, "0.9.50")

        self.assertTrue(result["complete"], result["diagnostics"])
        self.assertEqual(result["reverse_edges"], {
            "app.py": ["tests/test_app.py"],
            "util.py": ["app.py"],
        })

    def test_dart_graph_resolves_relative_and_own_package_uri_and_ignores_declared_external_package(self):
        builder = load_builder(self)
        with tempfile.TemporaryDirectory() as temp:
            snapshot = pathlib.Path(temp)
            (snapshot / "lib").mkdir()
            (snapshot / "test").mkdir()
            (snapshot / "lib" / "app.dart").write_text("import 'normalizer.dart';\n", encoding="utf-8")
            (snapshot / "lib" / "normalizer.dart").write_text("String clean(String s) => s.trim();\n", encoding="utf-8")
            (snapshot / "test" / "app_test.dart").write_text(
                "import 'package:probe/app.dart';\nimport 'package:flutter_test/flutter_test.dart';\n", encoding="utf-8"
            )
            (snapshot / "pubspec.yaml").write_text(
                "name: probe\ndependencies:\n  collection: ^1.18.0\ndev_dependencies:\n  flutter_test:\n    sdk: flutter\n",
                encoding="utf-8",
            )
            runner = GraphifyRunner(dart_graph())
            with mock.patch.object(builder.subprocess, "run", side_effect=runner):
                result = builder.build(snapshot, "0.9.50")

            self.assertTrue(result["complete"], result["diagnostics"])
            self.assertEqual(result["reverse_edges"], {
                "lib/app.dart": ["test/app_test.dart"],
                "lib/normalizer.dart": ["lib/app.dart"],
            })

    def test_dart_unknown_package_uri_makes_entire_graph_incomplete(self):
        builder = load_builder(self)
        with tempfile.TemporaryDirectory() as temp:
            snapshot = pathlib.Path(temp)
            (snapshot / "lib").mkdir()
            (snapshot / "test").mkdir()
            (snapshot / "lib" / "app.dart").write_text("String run() => 'ok';\n", encoding="utf-8")
            (snapshot / "lib" / "normalizer.dart").write_text("String clean(String s) => s.trim();\n", encoding="utf-8")
            (snapshot / "test" / "app_test.dart").write_text("import 'package:unknown/app.dart';\n", encoding="utf-8")
            (snapshot / "pubspec.yaml").write_text("name: probe\n", encoding="utf-8")
            runner = GraphifyRunner(dart_graph(target_package="unknown"))
            with mock.patch.object(builder.subprocess, "run", side_effect=runner):
                result = builder.build(snapshot, "0.9.50")

        self.assertFalse(result["complete"])
        self.assertEqual(result["reverse_edges"], {})
        self.assertTrue(any("unknown" in item for item in result["diagnostics"]), result["diagnostics"])

    def test_python_unresolved_local_import_makes_entire_graph_incomplete(self):
        builder = load_builder(self)
        graph = py_graph()
        graph["edges"].append({
            "source": "app", "target": "missing_module", "relation": "imports",
            "source_file": "app.py", "_origin": "ast",
        })
        with tempfile.TemporaryDirectory() as temp:
            snapshot = pathlib.Path(temp)
            (snapshot / "tests").mkdir()
            (snapshot / "app.py").write_text("from missing_module import item\n", encoding="utf-8")
            (snapshot / "util.py").write_text("def clean(value): return value\n", encoding="utf-8")
            (snapshot / "tests" / "test_app.py").write_text("def test_app(): pass\n", encoding="utf-8")
            (snapshot / "pyproject.toml").write_text(
                '[project]\nname = "sample"\ndependencies = ["requests>=2"]\n', encoding="utf-8"
            )
            with mock.patch.object(builder.subprocess, "run", side_effect=GraphifyRunner(graph)):
                result = builder.build(snapshot, "0.9.50")

        self.assertFalse(result["complete"])
        self.assertEqual(result["reverse_edges"], {})
        self.assertTrue(any("missing_module" in item for item in result["diagnostics"]), result["diagnostics"])

    def test_dynamic_import_relation_makes_entire_graph_incomplete(self):
        builder = load_builder(self)
        graph = py_graph()
        graph["edges"].append({
            "source": "app", "target": "runtime", "relation": "dynamic_import",
            "source_file": "app.py", "_origin": "ast",
        })
        with tempfile.TemporaryDirectory() as temp:
            snapshot = pathlib.Path(temp)
            (snapshot / "tests").mkdir()
            (snapshot / "app.py").write_text("__import__('runtime')\n", encoding="utf-8")
            (snapshot / "util.py").write_text("pass\n", encoding="utf-8")
            (snapshot / "tests" / "test_app.py").write_text("pass\n", encoding="utf-8")
            with mock.patch.object(builder.subprocess, "run", side_effect=GraphifyRunner(graph)):
                result = builder.build(snapshot, "0.9.50")

        self.assertFalse(result["complete"])
        self.assertEqual(result["reverse_edges"], {})

    def test_failed_or_unsupported_graph_output_never_exposes_partial_edges(self):
        builder = load_builder(self)
        variants = []
        failed = py_graph()
        failed["failed_sources"] = ["broken.py"]
        variants.append(failed)
        malformed = py_graph()
        del malformed["edges"]
        variants.append(malformed)
        inferred = py_graph()
        inferred["edges"][0]["_origin"] = "semantic"
        variants.append(inferred)
        for graph in variants:
            with self.subTest(graph=graph):
                with tempfile.TemporaryDirectory() as temp:
                    snapshot = pathlib.Path(temp)
                    (snapshot / "tests").mkdir()
                    (snapshot / "app.py").write_text("from util import clean\n", encoding="utf-8")
                    (snapshot / "util.py").write_text("pass\n", encoding="utf-8")
                    (snapshot / "tests" / "test_app.py").write_text("pass\n", encoding="utf-8")
                    with mock.patch.object(builder.subprocess, "run", side_effect=GraphifyRunner(graph)):
                        result = builder.build(snapshot, "0.9.50")
                self.assertFalse(result["complete"])
                self.assertEqual(result["reverse_edges"], {})

    def test_graphify_version_mismatch_and_update_failure_are_untrusted(self):
        builder = load_builder(self)
        for runner, expected in [
            (GraphifyRunner(py_graph(), version="0.9.51"), "0.9.50"),
            (GraphifyRunner(py_graph(), update_status=1), "0.9.50"),
        ]:
            with self.subTest(runner=runner.version, status=runner.update_status):
                with tempfile.TemporaryDirectory() as temp:
                    snapshot = pathlib.Path(temp)
                    (snapshot / "app.py").write_text("pass\n", encoding="utf-8")
                    with mock.patch.object(builder.subprocess, "run", side_effect=runner):
                        result = builder.build(snapshot, expected)
                self.assertFalse(result["complete"])
                self.assertEqual(result["reverse_edges"], {})

    def test_policy_must_allow_only_raw_code_extract_mode(self):
        builder = load_builder(self)
        policy = json.loads((ROOT / "skills" / "two-model-sdd-pipeline" / "toolchains" / "test-impact-rules.json").read_text(encoding="utf-8"))
        policy["graphify"]["command"] = "update"
        with tempfile.TemporaryDirectory() as temp:
            snapshot = pathlib.Path(temp) / "snapshot"
            snapshot.mkdir()
            (snapshot / "app.py").write_text("pass\n", encoding="utf-8")
            policy_path = pathlib.Path(temp) / "policy.json"
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            runner = GraphifyRunner(py_graph())
            with mock.patch.object(builder, "RULES_PATH", policy_path):
                with mock.patch.object(builder.subprocess, "run", side_effect=runner):
                    result = builder.build(snapshot, "0.9.50")

        self.assertFalse(result["complete"])
        self.assertEqual(result["reverse_edges"], {})
        self.assertTrue(any("policy" in item for item in result["diagnostics"]))
        self.assertEqual(len(runner.calls), 0)

    def test_missing_graphify_binary_fails_closed_without_writing_outside_snapshot(self):
        builder = load_builder(self)
        with tempfile.TemporaryDirectory() as temp:
            snapshot = pathlib.Path(temp)
            (snapshot / "app.py").write_text("pass\n", encoding="utf-8")
            with mock.patch.object(builder.subprocess, "run", side_effect=FileNotFoundError("graphify")):
                result = builder.build(snapshot, "0.9.50")
            self.assertFalse(result["complete"])
            self.assertEqual(result["reverse_edges"], {})
            self.assertFalse((snapshot / ".r4-graphify-output").exists())

    def test_import_edge_source_must_match_the_file_where_the_import_occurs(self):
        builder = load_builder(self)
        graph = py_graph()
        graph["edges"][0]["source"], graph["edges"][0]["target"] = "util", "app"
        with tempfile.TemporaryDirectory() as temp:
            snapshot = pathlib.Path(temp)
            (snapshot / "tests").mkdir()
            (snapshot / "app.py").write_text("from util import clean\n", encoding="utf-8")
            (snapshot / "util.py").write_text("def clean(value): return value\n", encoding="utf-8")
            (snapshot / "tests" / "test_app.py").write_text("from app import run\n", encoding="utf-8")
            with mock.patch.object(builder.subprocess, "run", side_effect=GraphifyRunner(graph)):
                result = builder.build(snapshot, "0.9.50")

        self.assertFalse(result["complete"])
        self.assertEqual(result["reverse_edges"], {})
        self.assertTrue(any("source node" in item for item in result["diagnostics"]), result["diagnostics"])


if __name__ == "__main__":
    unittest.main()
