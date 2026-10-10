from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.control_plane import WorkflowJobStore, approve_workflow_job, new_workflow_job  # noqa: E402
from bridge.workflow_control import (advance_workflow_job, load_native_binding, native_binding,
                                     workflow_job_card)  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402


class WorkflowControlTests(unittest.TestCase):
    def setUp(self):
        self.job = new_workflow_job("PC_PERSONALE", "PODCAST_REELS", "editorial_0123456789abcdef",
                                    {"project_name": "ARPHE", "timeline_name": "MASTER"}, "a" * 64)

    def test_podcast_marked_maps_to_review_ready_with_submit_review_action(self):
        native = SimpleNamespace(workstation_id="PC_PERSONALE", state="MARKED", project_name="ARPHE",
                                 timeline_name="MASTER", candidate_fingerprint="b" * 64)
        card = workflow_job_card(self.job, native)
        self.assertEqual("REVIEW_READY", card["state"])
        self.assertEqual("SUBMIT_REVIEW", card["next_safe_action"])

    def test_foreign_workstation_or_changed_target_is_rejected(self):
        foreign = SimpleNamespace(workstation_id="PC_SEGRETERIA", state="MARKED", project_name="ARPHE",
                                  timeline_name="MASTER", candidate_fingerprint="b" * 64)
        with self.assertRaisesRegex(ValidationError, "workstation"):
            native_binding(self.job, foreign)
        changed = SimpleNamespace(workstation_id="PC_PERSONALE", state="MARKED", project_name="ARPHE",
                                  timeline_name="OTHER", candidate_fingerprint="b" * 64)
        with self.assertRaisesRegex(ValidationError, "target"):
            native_binding(self.job, changed)

    def test_no_verified_delivery_never_fabricates_delivery_action(self):
        native = SimpleNamespace(workstation_id="PC_PERSONALE", state="VERIFIED", project_name="ARPHE",
                                 timeline_name="MASTER", candidate_fingerprint="b" * 64)
        card = workflow_job_card(self.job, native)
        self.assertEqual("REVIEW_READY", card["state"])
        self.assertEqual("NONE", card["next_safe_action"])

    def test_advance_requires_persisted_approval_before_delegate(self):
        import tempfile
        with tempfile.TemporaryDirectory() as raw:
            store = WorkflowJobStore(Path(raw) / "jobs.json", "PC_PERSONALE")
            job = store.create(self.job)
            calls = []
            with self.assertRaisesRegex(ValidationError, "approvazione"):
                advance_workflow_job(store, job.workflow_job_id, "a" * 64, lambda: calls.append(True))
            self.assertEqual([], calls)

    def test_repeated_advance_returns_recorded_evidence_without_second_delegate(self):
        import tempfile
        with tempfile.TemporaryDirectory() as raw:
            store = WorkflowJobStore(Path(raw) / "jobs.json", "PC_PERSONALE")
            job = approve_workflow_job(store, store.create(self.job).workflow_job_id, "a" * 64, "SECRETARY")
            calls = []
            first = advance_workflow_job(store, job.workflow_job_id, "a" * 64, lambda: {"native": "done"})
            second = advance_workflow_job(store, job.workflow_job_id, "a" * 64, lambda: calls.append(True))
            self.assertEqual({"native": "done"}, first["evidence"])
            self.assertEqual(first, second)
            self.assertEqual([], calls)

    def test_load_native_binding_uses_editorial_store_and_rejects_unknown_family(self):
        from bridge.editorial_jobs import EditorialJobStore, new_editorial_job
        import tempfile
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "editorial.json"
            native = EditorialJobStore(path, "PC_PERSONALE").create(new_editorial_job(
                workstation_id="PC_PERSONALE", workflow_version=1, project_name="ARPHE",
                timeline_name="MASTER", timeline_identity="timeline-1", source_fingerprint="a" * 64,
                transcript_fingerprint="b" * 64, candidate_fingerprint="c" * 64,
                candidates=[{"candidate_id": "R01"}]))
            config = SimpleNamespace(workstation_id="PC_PERSONALE", editorial_jobs_path=path)
            loaded = load_native_binding(config, "PODCAST_REELS", native.editorial_job_id)
            self.assertEqual(native.editorial_job_id, loaded.editorial_job_id)
            with self.assertRaisesRegex(ValidationError, "workflow_family"):
                load_native_binding(config, "UNKNOWN", native.editorial_job_id)


if __name__ == "__main__":
    unittest.main()
