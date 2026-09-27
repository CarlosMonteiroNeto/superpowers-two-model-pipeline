"""Controller-owned durable run process registry tests."""
import importlib.util
import pathlib
import tempfile
import unittest
import json
import threading
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[3]
SCRIPT=ROOT/"skills"/"two-model-sdd-pipeline"/"scripts"/"run_control.py"
spec=importlib.util.spec_from_file_location("r35_run_control",SCRIPT)
control=importlib.util.module_from_spec(spec); spec.loader.exec_module(control)


class RunControlTests(unittest.TestCase):
    def test_registration_and_cancel_are_run_bound_and_stop_exact_process_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            path=pathlib.Path(temp)/"run.json"; control.initialize(path,"run-a")
            record={"pid":123,"start_identity":"start-a"}
            control.register_process(path,"run-a",record)
            with mock.patch.object(control.codex_process,"stop_owned_processes") as stop:
                state=control.request_cancel(path,"run-a")
            stop.assert_called_once_with([record],1.0)
            self.assertTrue(state["cancel_requested"])
            self.assertEqual(state["processes"][0]["status"],"interrupted")
            with self.assertRaisesRegex(ValueError,"identity mismatch"):
                control.request_cancel(path,"run-b")

    def test_task_run_exec_registers_owned_child_and_preserves_exit_code(self):
        with tempfile.TemporaryDirectory() as temp:
            path=pathlib.Path(temp)/"run.json"; control.initialize(path,"run-a")
            identity={"pid":456,"start_identity":"start-b"}
            with mock.patch.object(control.subprocess,"Popen") as popen, mock.patch.object(control.codex_process,"_start_identity",return_value="start-b"):
                popen.return_value.pid=456; popen.return_value.wait.return_value=7
                with mock.patch.object(control,"register_process") as register, mock.patch.object(control,"mark_process") as mark:
                    result=control.execute_owned(path,"run-a",["fake-task"])
            self.assertEqual(result,7); register.assert_called_once()
            self.assertEqual(mark.call_args.args[3],"failed")

    def test_parallel_process_registration_is_serialized_without_lost_records(self):
        with tempfile.TemporaryDirectory() as temp:
            path=pathlib.Path(temp)/"run.json"; control.initialize(path,"run-a")
            workers=[threading.Thread(target=control.register_process,args=(path,"run-a",{"pid":i+100,"start_identity":"s"+str(i)})) for i in range(24)]
            for worker in workers: worker.start()
            for worker in workers: worker.join()
            state=json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(state["processes"]),24)

    def test_resume_clears_cancel_flag_only_after_stopping_orphaned_owned_processes(self):
        with tempfile.TemporaryDirectory() as temp:
            path=pathlib.Path(temp)/"run.json"; control.initialize(path,"run-a")
            record={"pid":91,"start_identity":"start"}
            control.register_process(path,"run-a",record)
            with mock.patch.object(control.codex_process,"stop_owned_processes") as stop:
                resumed=control.initialize(path,"run-a")
            stop.assert_called_once_with([record],1.0)
            self.assertFalse(resumed["cancel_requested"])
            self.assertEqual(resumed["status"],"active")
            self.assertEqual(resumed["processes"][0]["status"],"interrupted")


if __name__=="__main__": unittest.main()
