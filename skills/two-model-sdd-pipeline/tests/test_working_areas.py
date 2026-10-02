"""Task 3 RED: directory authority and atomic scheduling reservations."""

import json
import multiprocessing
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

try:
    import working_areas
except ImportError:
    working_areas = None


def require_module(testcase):
    testcase.assertIsNotNone(
        working_areas, "working_areas.py provides directory authority")


def areas_task(*areas, task_id=1):
    return {"id": task_id, "working_areas": list(areas)}


def legacy_task(*paths, task_id=1):
    return {"id": task_id, "touches": list(paths)}


def owner(run="run-1", family=1, task=1, **extra):
    value = {"run_id": run, "family_id": family, "task_id": task}
    value.update(extra)
    return value


def _reserve_worker(registry, scope, request_owner, queue, gate):
    try:
        import working_areas as areas
        queue.put(areas.reserve(registry, request_owner, scope))
    except Exception as exc:  # pragma: no cover - surfaced to the parent
        queue.put({"decision": "error", "error": str(exc)})
    finally:
        gate.wait(60)


class NormalizeTests(unittest.TestCase):
    def setUp(self):
        require_module(self)
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="areas-"))
        self.root = self._tmp / "repo"
        self.root.mkdir()

    def test_areas_mode_returns_canonical_roots(self):
        scope = working_areas.normalize(
            areas_task("src/a", "lib/"), str(self.root))
        self.assertEqual(scope["mode"], "areas")
        self.assertEqual(scope["roots"], ["lib", "src/a"])
        self.assertEqual(scope["exact_paths"], [])

    def test_missing_areas_keeps_legacy_mode(self):
        scope = working_areas.normalize(
            legacy_task("src/a/x.py"), str(self.root))
        self.assertEqual(scope["mode"], "legacy")
        self.assertEqual(scope["roots"], [])
        self.assertEqual(scope["exact_paths"], ["src/a/x.py"])

    def test_explicit_dot_reserves_the_repository(self):
        scope = working_areas.normalize(areas_task("."), str(self.root))
        self.assertEqual(scope["mode"], "areas")
        self.assertEqual(scope["roots"], ["."])

    def test_traversal_absolute_and_drive_paths_are_rejected(self):
        for bad in ("../escape", "/absolute", "C:/win", "a/../../b",
                    "src/./x", ""):
            with self.subTest(path=bad):
                with self.assertRaises(ValueError):
                    working_areas.normalize(
                        areas_task(bad), str(self.root))

    def test_nonexistent_descendants_are_allowed(self):
        scope = working_areas.normalize(
            areas_task("src/future/deep"), str(self.root))
        self.assertEqual(scope["roots"], ["src/future/deep"])


class OverlapTests(unittest.TestCase):
    def setUp(self):
        require_module(self)
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="areas-"))
        self.root = str(self._tmp / "repo")
        os.makedirs(self.root)

    def scopes(self, left, right):
        return (working_areas.normalize(left, self.root),
                working_areas.normalize(right, self.root))

    def test_equal_and_nested_roots_conflict(self):
        left, right = self.scopes(areas_task("src/a"), areas_task("src/a"))
        self.assertTrue(working_areas.overlap(left, right, self.root))
        left, right = self.scopes(areas_task("src"), areas_task("src/a/b"))
        self.assertTrue(working_areas.overlap(left, right, self.root))
        left, right = self.scopes(areas_task("src/a/b"), areas_task("src"))
        self.assertTrue(working_areas.overlap(left, right, self.root))

    def test_sibling_prefixes_do_not_conflict(self):
        left, right = self.scopes(areas_task("src/a"), areas_task("src/ab"))
        self.assertFalse(working_areas.overlap(left, right, self.root))

    def test_legacy_path_inside_an_area_conflicts(self):
        left, right = self.scopes(
            legacy_task("src/a/x.py"), areas_task("src/a"))
        self.assertTrue(working_areas.overlap(left, right, self.root))
        left, right = self.scopes(
            legacy_task("src/other/x.py"), areas_task("src/a"))
        self.assertFalse(working_areas.overlap(left, right, self.root))

    def test_legacy_exact_paths_keep_equality_semantics(self):
        left, right = self.scopes(
            legacy_task("src/a.py"), legacy_task("src/a.py"))
        self.assertTrue(working_areas.overlap(left, right, self.root))
        left, right = self.scopes(
            legacy_task("src/a.py"), legacy_task("src/b.py"))
        self.assertFalse(working_areas.overlap(left, right, self.root))

    def test_explicit_root_conflicts_with_everything(self):
        for other in (areas_task("src/a"), legacy_task("src/a.py")):
            left, right = self.scopes(areas_task("."), other)
            self.assertTrue(working_areas.overlap(left, right, self.root))

    def test_case_aliases_follow_platform(self):
        left, right = self.scopes(areas_task("SRC/A"), areas_task("src/a"))
        self.assertEqual(
            working_areas.overlap(left, right, self.root),
            os.path.normcase("X") != "X")

    def test_symlinked_roots_resolve_to_the_same_target(self):
        target = self._tmp / "real"
        target.mkdir()
        link = self._tmp / "linked"
        try:
            os.symlink(str(target), str(link))
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable")
        root = str(self._tmp)
        left = working_areas.normalize(areas_task("real"), root)
        right = working_areas.normalize(areas_task("linked"), root)
        self.assertTrue(working_areas.overlap(left, right, root))


class ReservationTests(unittest.TestCase):
    def setUp(self):
        require_module(self)
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="areas-"))
        self.root = str(self._tmp / "repo")
        os.makedirs(self.root)
        self.registry = str(self._tmp / "reservations.json")

    def scope(self, *areas):
        return working_areas.normalize(areas_task(*areas), self.root)

    def test_grant_returns_owner_identity(self):
        result = working_areas.reserve(
            self.registry, owner(), self.scope("src/a"))
        self.assertEqual(result["decision"], "granted")
        self.assertEqual(result["owner"]["run_id"], "run-1")
        self.assertEqual(result["owner"]["family_id"], 1)

    def test_overlapping_family_conflicts_with_owner_evidence(self):
        working_areas.reserve(self.registry, owner(), self.scope("src/a"))
        result = working_areas.reserve(
            self.registry, owner(run="run-2", family=2, task=2),
            self.scope("src/a/b"))
        self.assertEqual(result["decision"], "conflict")
        self.assertEqual(result["owner"]["family_id"], 1)

    def test_same_family_retains_its_reservation(self):
        working_areas.reserve(self.registry, owner(), self.scope("src/a"))
        result = working_areas.reserve(
            self.registry, owner(task=2), self.scope("src/a/b"))
        self.assertEqual(result["decision"], "granted")

    def test_release_requires_matching_ownership_and_completion(self):
        working_areas.reserve(self.registry, owner(), self.scope("src/a"))
        with self.assertRaises(ValueError):
            working_areas.release(
                self.registry, owner(family=2, task=2, completed=True))
        with self.assertRaises(ValueError):
            working_areas.release(self.registry, owner())
        with self.assertRaises(ValueError):
            working_areas.release(
                self.registry, owner(completed=False))
        working_areas.release(self.registry, owner(completed=True))
        result = working_areas.reserve(
            self.registry, owner(run="run-2", family=2, task=2),
            self.scope("src/a"))
        self.assertEqual(result["decision"], "granted")

    def test_live_owner_is_never_retired_by_timeout_alone(self):
        working_areas.reserve(self.registry, owner(), self.scope("src/a"))
        time.sleep(0.05)
        result = working_areas.reserve(
            self.registry, owner(run="run-2", family=2, task=2),
            self.scope("src/a"))
        self.assertEqual(result["decision"], "conflict")

    def test_exactly_one_overlapping_claim_wins_the_race(self):
        scope = self.scope("src/race")
        ctx = multiprocessing.get_context("spawn")
        queue = ctx.Queue()
        gate = ctx.Event()
        first = owner(run="run-a", family=10, task=1)
        second = owner(run="run-b", family=20, task=2)
        procs = [ctx.Process(target=_reserve_worker,
                             args=(self.registry, scope, candidate, queue,
                                   gate))
                 for candidate in (first, second)]
        for proc in procs:
            proc.start()
        try:
            outcomes = [queue.get(timeout=120) for _ in procs]
        finally:
            gate.set()
        for proc in procs:
            proc.join(60)
            if proc.is_alive():
                proc.terminate()
        granted = [o for o in outcomes if o.get("decision") == "granted"]
        conflicted = [o for o in outcomes if o.get("decision") == "conflict"]
        self.assertEqual(len(granted), 1)
        self.assertEqual(len(conflicted), 1)

    def test_dead_owner_is_retired_with_recovery_recorded(self):
        import json as _json
        import subprocess as _subprocess
        scope = self.scope("src/gone")
        planter = (
            "import json, sys; sys.path.insert(0, sys.argv[1]); "
            "import working_areas; "
            "working_areas.reserve(sys.argv[2], json.loads(sys.argv[3]), "
            "json.loads(sys.argv[4]))")
        plant = _subprocess.run(
            [sys.executable, "-c", planter, str(SCRIPTS), self.registry,
             _json.dumps(owner(run="run-dead", family=9, task=1)),
             _json.dumps(scope)],
            capture_output=True, text=True)
        self.assertEqual(plant.returncode, 0, plant.stderr)
        result = working_areas.reserve(
            self.registry, owner(run="run-2", family=2, task=2),
            self.scope("src/gone"))
        self.assertEqual(result["decision"], "granted")
        self.assertTrue(result.get("recovered", False))


def _bash():
    bash = shutil.which("bash")
    if os.name == "nt":
        git_bash = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
        bash = str(git_bash) if git_bash.exists() else bash
    return bash


class CliRoundTripTests(unittest.TestCase):
    """reserve-for-task/release-for-task CLI through a full lifecycle."""

    def test_release_frees_the_area_for_the_next_family(self):
        import json as _json
        import subprocess as _subprocess
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="areas-cli-"))
        repo = tmp / "repo"
        repo.mkdir()
        ws = tmp / "ws"
        ws.mkdir()
        (ws / "plan.json").write_text(_json.dumps({"tasks": [
            {"id": 1, "working_areas": ["src/a"]}]}), encoding="utf-8")
        (ws / ".pipeline-identity.json").write_text(_json.dumps(
            {"run_id": "run-cli", "repository_root": str(repo)}),
            encoding="utf-8")
        registry = str(tmp / "reservations.json")
        cli = str(SCRIPTS / "working_areas.py")
        first = _subprocess.run(
            [sys.executable, cli, "reserve-for-task", registry, str(ws), "1"],
            capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(_json.loads(first.stdout)["decision"], "granted")
        released = _subprocess.run(
            [sys.executable, cli, "release-for-task", registry, str(ws), "1"],
            capture_output=True, text=True)
        self.assertEqual(released.returncode, 0, released.stderr)
        self.assertEqual(_json.loads(released.stdout)["decision"], "released")
        again = _subprocess.run(
            [sys.executable, cli, "release-for-task", registry, str(ws), "1"],
            capture_output=True, text=True)
        self.assertEqual(again.returncode, 1)
        self.assertEqual(_json.loads(again.stdout)["decision"], "no_match")


class DispatchRetryAreasTests(unittest.TestCase):
    """dispatch-retry reserves opted-in task areas before worker start."""

    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="areas-dispatch-"))
        self.ws = self._tmp / "ws"
        self.ws.mkdir()
        self.repo = self._tmp / "repo"
        self.repo.mkdir()
        (self.ws / ".pipeline-identity.json").write_text(json.dumps(
            {"run_id": "run-hook", "repository_root": str(self.repo)}),
            encoding="utf-8")
        self.stub = self._tmp / "stub-dispatch"
        self.stub_calls = self._tmp / "stub-calls.log"
        self.stub.write_text(
            "#!/usr/bin/env bash\necho \"$*\" >> \"%s\"\nexit 0\n"
            % str(self.stub_calls).replace("\\", "/"), encoding="utf-8")
        if os.name == "nt":
            bash = _bash()
            if bash:
                subprocess.run(
                    [bash, "-c", "chmod +x '{}'".format(self.stub)],
                    capture_output=True)
        else:
            os.chmod(self.stub, 0o755)
        self.prompt = self.ws / "task-1-brief.md"
        self.prompt.write_text("brief", encoding="utf-8")

    def write_plan(self, tasks):
        (self.ws / "plan.json").write_text(
            json.dumps({"tasks": tasks}), encoding="utf-8")

    def run_retry(self, *args):
        bash = _bash()
        if not bash:
            self.skipTest("Bash is required for the dispatch hook")
        env = dict(os.environ, DISPATCH_BIN=str(self.stub))
        return subprocess.run(
            [bash, str(SCRIPTS / "dispatch-retry"),
             "--agent", "two-model-coder", "--task", "1",
             "--prompt-file", str(self.prompt),
             "--log", str(self.ws / "task-1-coder.log"), *args],
            capture_output=True, text=True, env=env)

    def test_opted_in_task_is_reserved_before_dispatch(self):
        self.write_plan([{"id": 1, "working_areas": ["src/a"],
                          "touches": []}])
        result = self.run_retry()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.stub_calls.is_file(), "worker must dispatch")
        registry = json.loads(
            (self.ws / "reservations.json").read_text(encoding="utf-8"))
        reservations = registry["reservations"]
        self.assertEqual(len(reservations), 1)
        self.assertEqual(reservations[0]["roots"], ["src/a"])
        self.assertEqual(reservations[0]["owner"]["run_id"], "run-hook")

    def test_conflicting_reservation_blocks_dispatch(self):
        self.write_plan([{"id": 1, "working_areas": ["src/a"],
                          "touches": []}])
        scope = working_areas.normalize(
            {"id": 2, "working_areas": ["src"]}, str(self.repo))
        working_areas.reserve(
            str(self.ws / "reservations.json"),
            {"run_id": "run-other", "family_id": 9, "task_id": 2}, scope)
        result = self.run_retry()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.stub_calls.exists(), "worker must not start")
        self.assertIn("SCOPE", result.stderr.upper())

    def test_legacy_task_keeps_exact_path_authority(self):
        self.write_plan([{"id": 1, "touches": ["src/a/x.py"]}])
        result = self.run_retry()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        registry = json.loads(
            (self.ws / "reservations.json").read_text(encoding="utf-8"))
        self.assertEqual(
            registry["reservations"][0]["exact_paths"], ["src/a/x.py"])


if __name__ == "__main__":
    unittest.main()
