from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.control_plane import (WorkflowJobStore, approve_workflow_job, new_workflow_job)  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
