from __future__ import annotations

from dataclasses import replace
import multiprocessing
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.control_plane import (WorkflowJobStore, approve_workflow_job, new_workflow_job)  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402


def _create_delayed_job_in_process(path_text: str, native_reference: str, fingerprint: str,
                                   start: object, output: object) -> None:
    """Spawn-safe helper: force a read/write overlap unless the registry locks cross-process."""
    store = WorkflowJobStore(Path(path_text), "PC_PERSONALE")
    original_read = store._read

    def delayed_read():
        data = original_read()
        time.sleep(0.15)
        return data

    store._read = delayed_read  # type: ignore[method-assign]
    start.wait(5)
    job = new_workflow_job("PC_PERSONALE", "PODCAST_REELS", native_reference,
                           {"project_name": "ARPHE", "timeline_name": "MASTER"}, fingerprint)
    output.put(store.create(job).workflow_job_id)


class ControlPlaneTests(unittest.TestCase):
    def test_same_binding_is_idempotent_but_changed_binding_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            store = WorkflowJobStore(Path(raw) / "jobs.json", "PC_PERSONALE")
            job = new_workflow_job("PC_PERSONALE", "PODCAST_REELS", "editorial_0123456789abcdef",
                                   {"project_name": "ARPHE", "timeline_name": "MASTER"}, "a" * 64)
            self.assertEqual(job, store.create(job))
            self.assertEqual(job, store.create(job))
            with self.assertRaisesRegex(ValidationError, "contenuto differente"):
                store.create(replace(job, target={"project_name": "ARPHE", "timeline_name": "OTHER"}))

    def test_approval_requires_exact_plan_fingerprint(self):
        with tempfile.TemporaryDirectory() as raw:
            store = WorkflowJobStore(Path(raw) / "jobs.json", "PC_PERSONALE")
            job = store.create(new_workflow_job(
                "PC_PERSONALE", "PODCAST_REELS", "editorial_0123456789abcdef",
                {"project_name": "ARPHE", "timeline_name": "MASTER"}, "a" * 64))
            with self.assertRaisesRegex(ValidationError, "fingerprint"):
                approve_workflow_job(store, job.workflow_job_id, "0" * 64, "SECRETARY")
            approved = approve_workflow_job(store, job.workflow_job_id, "a" * 64, "SECRETARY")
            self.assertEqual("AWAITING_APPROVAL", approved.state)
            self.assertEqual("a" * 64, approved.approved_plan_fingerprint)

    def test_registry_refuses_foreign_workstation_and_corruption(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "jobs.json"
            store = WorkflowJobStore(path, "PC_PERSONALE")
            job = new_workflow_job("PC_PERSONALE", "PODCAST_REELS", "editorial_0123456789abcdef",
                                   {"project_name": "ARPHE", "timeline_name": "MASTER"}, "a" * 64)
            store.create(job)
            with self.assertRaisesRegex(ValidationError, "un'altra workstation"):
                WorkflowJobStore(path, "PC_SEGRETERIA")
            path.write_text("not json", encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "non leggibile"):
                store.get(job.workflow_job_id)

    def test_find_binding_and_active_list_do_not_create_duplicates(self):
        with tempfile.TemporaryDirectory() as raw:
            store = WorkflowJobStore(Path(raw) / "jobs.json", "PC_PERSONALE")
            job = store.create(new_workflow_job(
                "PC_PERSONALE", "PODCAST_REELS", "editorial_0123456789abcdef",
                {"project_name": "ARPHE", "timeline_name": "MASTER"}, "a" * 64))
            found = store.find_binding("PODCAST_REELS", job.native_reference, job.target, job.plan_fingerprint)
            self.assertEqual(job.workflow_job_id, found.workflow_job_id)
            self.assertEqual([job.workflow_job_id], [item.workflow_job_id for item in store.active()])

    def test_concurrent_binding_creation_preserves_both_jobs(self):
        """A second MCP worker cannot replace an unrelated job's registry update."""
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "jobs.json"
            first = new_workflow_job("PC_PERSONALE", "PODCAST_REELS", "editorial_first",
                                     {"project_name": "ARPHE", "timeline_name": "MASTER"}, "a" * 64)
            second = new_workflow_job("PC_PERSONALE", "PODCAST_REELS", "editorial_second",
                                      {"project_name": "ARPHE", "timeline_name": "MASTER"}, "b" * 64)
            entered = threading.Event()
            original_read = WorkflowJobStore._read

            def delayed_first_read(store):
                data = original_read(store)
                if not entered.is_set():
                    entered.set()
                    threading.Event().wait(0.15)
                return data

            results = []
            with patch.object(WorkflowJobStore, "_read", delayed_first_read):
                threads = [threading.Thread(target=lambda job=job: results.append(
                    WorkflowJobStore(path, "PC_PERSONALE").create(job)
                )) for job in (first, second)]
                for thread in threads: thread.start()
                for thread in threads: thread.join()
            self.assertEqual(2, len(results))
            self.assertEqual({first.workflow_job_id, second.workflow_job_id}, {
                job.workflow_job_id for job in WorkflowJobStore(path, "PC_PERSONALE").active()
            })

    def test_independent_processes_preserve_both_jobs(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "jobs.json"
            context = multiprocessing.get_context("spawn")
            start, output = context.Event(), context.Queue()
            processes = [
                context.Process(target=_create_delayed_job_in_process,
                                args=(str(path), native_reference, fingerprint, start, output))
                for native_reference, fingerprint in (
                    ("editorial_process_one", "a" * 64),
                    ("editorial_process_two", "b" * 64),
                )
            ]
            for process in processes:
                process.start()
            start.set()
            for process in processes:
                process.join(10)
                self.assertEqual(0, process.exitcode)
            created_ids = {output.get(timeout=2), output.get(timeout=2)}
            self.assertEqual(2, len(created_ids))
            self.assertEqual(2, len(WorkflowJobStore(path, "PC_PERSONALE").active()))


if __name__ == "__main__":
    unittest.main()
