from __future__ import annotations

from pathlib import Path
import sys
from dataclasses import replace
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.control_plane import WorkflowJobStore, approve_workflow_job, new_workflow_job  # noqa: E402
from bridge.workflow_control import (advance_workflow_job, control_plan_fingerprint,
                                     load_native_binding, native_binding,
                                     native_plan_fingerprint, workflow_job_card)  # noqa: E402
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

    def test_new_native_operation_can_advance_after_review_ready(self):
        import tempfile
        with tempfile.TemporaryDirectory() as raw:
            store = WorkflowJobStore(Path(raw) / "jobs.json", "PC_PERSONALE")
            job = approve_workflow_job(store, store.create(self.job).workflow_job_id, "a" * 64, "SECRETARY")
            first = advance_workflow_job(
                store, job.workflow_job_id, "a" * 64,
                lambda: {"native": "verified"}, operation_key="REVIEWED:EXECUTE")
            calls = []
            second = advance_workflow_job(
                store, job.workflow_job_id, "a" * 64,
                lambda: calls.append(True) or {"state": "CLOSED"}, operation_key="VERIFIED:CLOSE")
            repeated = advance_workflow_job(
                store, job.workflow_job_id, "a" * 64,
                lambda: calls.append(False), operation_key="VERIFIED:CLOSE")
            self.assertEqual("REVIEW_READY", first["state"])
            self.assertEqual("CLOSED", second["state"])
            self.assertEqual(second, repeated)
            self.assertEqual([True], calls)

    def test_interrupted_executing_job_becomes_recoverable_before_resume(self):
        import tempfile
        with tempfile.TemporaryDirectory() as raw:
            store = WorkflowJobStore(Path(raw) / "jobs.json", "PC_PERSONALE")
            job = approve_workflow_job(store, store.create(self.job).workflow_job_id, "a" * 64, "SECRETARY")
            with self.assertRaises(KeyboardInterrupt):
                advance_workflow_job(
                    store, job.workflow_job_id, "a" * 64,
                    lambda: (_ for _ in ()).throw(KeyboardInterrupt("process stopped")),
                    operation_key="PODCAST_REELS:REVIEWED:EXECUTE",
                )
            recovered = advance_workflow_job(
                store, job.workflow_job_id, "a" * 64,
                lambda: self.fail("must not rerun while recovery is being recorded"),
                operation_key="PODCAST_REELS:REVIEWED:EXECUTE",
            )
            self.assertEqual("FAILED_RECOVERABLE", recovered["state"])
            resumed = advance_workflow_job(
                store, job.workflow_job_id, "a" * 64,
                lambda: {"native": "reconciled"},
                operation_key="PODCAST_REELS:REVIEWED:EXECUTE",
            )
            self.assertEqual("REVIEW_READY", resumed["state"])

    def test_native_review_changes_control_plan_fingerprint(self):
        marked = SimpleNamespace(workstation_id="PC_PERSONALE", state="MARKED",
                                 project_name="ARPHE", timeline_name="MASTER",
                                 candidate_fingerprint="b" * 64, review_fingerprint=None)
        reviewed = SimpleNamespace(workstation_id="PC_PERSONALE", state="REVIEWED",
                                   project_name="ARPHE", timeline_name="MASTER",
                                   candidate_fingerprint="b" * 64, review_fingerprint="c" * 64)
        self.assertEqual("b" * 64, native_plan_fingerprint("PODCAST_REELS", marked))
        before = control_plan_fingerprint(
            "PC_PERSONALE", "PODCAST_REELS", "editorial_0123456789abcdef",
            {"project_name": "ARPHE", "timeline_name": "MASTER"}, marked)
        after = control_plan_fingerprint(
            "PC_PERSONALE", "PODCAST_REELS", "editorial_0123456789abcdef",
            {"project_name": "ARPHE", "timeline_name": "MASTER"}, reviewed)
        self.assertNotEqual(before, after)

    def test_branded_approval_change_invalidates_control_fingerprint(self):
        before = SimpleNamespace(workstation_id="PC_PERSONALE", state="APPROVED",
                                 project_name="ARPHE", original_timeline="MASTER",
                                 source_fingerprint="a" * 64, profile_fingerprint="b" * 64,
                                 proposal_card={"fingerprint": "c" * 64},
                                 approval={"approved_ids": ["P001"], "modified": {}})
        after = SimpleNamespace(**{**before.__dict__, "approval": {
            "approved_ids": ["P002"], "modified": {"P002": "testo aggiornato"},
        }})
        target = {"project_name": "ARPHE", "timeline_name": "MASTER"}
        self.assertNotEqual(
            control_plan_fingerprint("PC_PERSONALE", "BRANDED_LONGFORM", "job-1", target, before),
            control_plan_fingerprint("PC_PERSONALE", "BRANDED_LONGFORM", "job-1", target, after),
        )

    def test_native_binding_rejects_same_name_different_timeline_identity(self):
        job = replace(self.job, target={
            "project_name": "ARPHE", "timeline_name": "MASTER", "timeline_identity": "resolve:old",
        })
        replacement = SimpleNamespace(workstation_id="PC_PERSONALE", state="REVIEWED",
                                      project_name="ARPHE", timeline_name="MASTER",
                                      timeline_identity="resolve:replacement", candidate_fingerprint="b" * 64)
        with self.assertRaisesRegex(ValidationError, "identità"):
            native_binding(job, replacement)

    def test_card_marks_changed_native_plan_stale(self):
        native = SimpleNamespace(workstation_id="PC_PERSONALE", state="REVIEWED",
                                 project_name="ARPHE", timeline_name="MASTER",
                                 candidate_fingerprint="b" * 64, review_fingerprint="c" * 64)
        card = workflow_job_card(replace(self.job, approved_plan_fingerprint="a" * 64), native)
        self.assertEqual("STALE", card["state"])
        self.assertEqual("PREPARE_NEW_PLAN", card["next_safe_action"])

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
