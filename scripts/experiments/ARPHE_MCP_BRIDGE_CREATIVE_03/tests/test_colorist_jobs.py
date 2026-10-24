from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.colorist_jobs import (  # noqa: E402
    ColoristJobStore,
    after_version_names,
    approve_colorist_job,
    cancel_colorist_job,
    new_colorist_job,
    record_colorist_apply,
    record_colorist_apply_failure,
    record_colorist_apply_started,
    record_colorist_preview_start,
    record_colorist_review,
)
from bridge.safety import ValidationError  # noqa: E402


def job():
    return new_colorist_job(
        workstation_id="PC_PERSONALE",
        project_name="ARPHE_TEST",
        timeline_name="ARPHE_COLOR_TEST",
        timeline_identity="timeline-123",
        clip_ids=("clip-a", "clip-b"),
        reference_clip_id="clip-a",
        adjustments={"temperature": 0.1},
        preset_name="ARPHE_CLEAN_NEUTRAL",
        drx_preset_name=None,
        drx_asset_identity=None,
        before_versions={
            "clip-a": {"versionName": "Original", "versionType": 0},
            "clip-b": {"versionName": "Original", "versionType": 0},
        },
        cdl={"NodeIndex": 1, "Slope": "1 1 1", "Offset": "0 0 0",
             "Power": "1 1 1", "Saturation": "1"},
    )


class ColoristJobTests(unittest.TestCase):
    def test_cancel_is_compare_and_swap_idempotent_and_cannot_cancel_approved_work(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ColoristJobStore(Path(directory) / "colorist.json", "PC_PERSONALE")
            created = store.create(job())
            cancelled = cancel_colorist_job(
                store, created.colorist_job_id, created.plan_fingerprint, created.revision,
                "ALESSIO", "Superseded test plan",
            )
            self.assertEqual("CANCELLED", cancelled.state)
            self.assertEqual(created.revision + 1, cancelled.revision)
            self.assertEqual("Superseded test plan", cancelled.cancellation_evidence["reason"])
            self.assertEqual(
                cancelled,
                cancel_colorist_job(
                    store, created.colorist_job_id, created.plan_fingerprint, created.revision,
                    "ALESSIO", "Superseded test plan",
                ),
            )
            with self.assertRaisesRegex(ValidationError, "differenti"):
                cancel_colorist_job(
                    store, created.colorist_job_id, created.plan_fingerprint, created.revision,
                    "ALESSIO", "Other reason",
                )

            second = store.create(job())
            approved = approve_colorist_job(second, second.plan_fingerprint, "ALESSIO")
            store.save(approved, second.revision)
            with self.assertRaisesRegex(ValidationError, "PREPARED"):
                cancel_colorist_job(
                    store, second.colorist_job_id, second.plan_fingerprint, second.revision + 1,
                    "ALESSIO", "Too late",
                )

    def test_job_lifecycle_requires_fingerprint_bound_human_approval(self):
        prepared = job()
        with self.assertRaisesRegex(ValidationError, "fingerprint"):
            approve_colorist_job(prepared, "0" * 64, "ALESSIO")
        with self.assertRaisesRegex(ValidationError, "ruolo"):
            approve_colorist_job(prepared, prepared.plan_fingerprint, "BOT")

        approved = approve_colorist_job(prepared, prepared.plan_fingerprint, "COLORIST")
        self.assertEqual("APPROVED", approved.state)
        self.assertEqual("COLORIST", approved.operator_role)

        applying = record_colorist_apply_started(approved)
        names = after_version_names(applying)
        applied = record_colorist_apply(applying, tuple({
            "clip_id": clip_id, "before_version": "Original", "after_version": names[clip_id],
            "reference_clip_id": "clip-a", "cdl_applied_directly": clip_id == "clip-a",
            "drx_preset_name": None,
        } for clip_id in applying.clip_ids))
        self.assertEqual("APPLIED", applied.state)
        accepted = record_colorist_review(applied, True, "ALESSIO")
        self.assertEqual("ACCEPTED", accepted.state)
        self.assertTrue(accepted.review_accepted)

    def test_review_can_reject_but_cannot_skip_apply_or_repeat_terminal_transition(self):
        prepared = job()
        with self.assertRaises(ValidationError):
            record_colorist_review(prepared, False, "ALESSIO")
        approved = approve_colorist_job(prepared, prepared.plan_fingerprint, "ALESSIO")
        applying = record_colorist_apply_started(approved)
        names = after_version_names(applying)
        applied = record_colorist_apply(applying, tuple({
            "clip_id": clip_id, "before_version": "Original", "after_version": names[clip_id],
            "reference_clip_id": "clip-a", "cdl_applied_directly": clip_id == "clip-a",
            "drx_preset_name": None,
        } for clip_id in applying.clip_ids))
        rejected = record_colorist_review(applied, False, "ALESSIO")
        self.assertEqual("REJECTED", rejected.state)
        with self.assertRaises(ValidationError):
            record_colorist_review(rejected, True, "ALESSIO")

    def test_job_rejects_duplicate_clips_reference_outside_targets_and_incomplete_versions(self):
        common = dict(
            workstation_id="PC_PERSONALE", project_name="ARPHE_TEST",
            timeline_name="ARPHE_COLOR_TEST", timeline_identity="timeline-123",
            adjustments={}, preset_name="ARPHE_CLEAN_NEUTRAL", drx_preset_name=None,
            drx_asset_identity=None,
            cdl={"NodeIndex": 1, "Slope": "1 1 1", "Offset": "0 0 0",
                 "Power": "1 1 1", "Saturation": "1"},
        )
        for clips, reference, versions in (
            (("a", "a"), "a", {"a": {"versionName": "Original", "versionType": 0}}),
            (("a",), "b", {"a": {"versionName": "Original", "versionType": 0}}),
            (("a", "b"), "a", {"a": {"versionName": "Original", "versionType": 0}}),
        ):
            with self.subTest(clips=clips), self.assertRaises(ValidationError):
                new_colorist_job(clip_ids=clips, reference_clip_id=reference,
                                  before_versions=versions, **common)

    def test_store_round_trips_and_rejects_stale_revision_foreign_workstation_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "colorist.json"
            store = ColoristJobStore(path, "PC_PERSONALE")
            created = store.create(job())
            self.assertEqual(1, created.revision)
            self.assertEqual(created, store.get(created.colorist_job_id, "PC_PERSONALE"))
            with self.assertRaisesRegex(ValidationError, "workstation"):
                store.get(created.colorist_job_id, "PC_SEGRETERIA")

            approved = approve_colorist_job(created, created.plan_fingerprint, "ALESSIO")
            saved = store.save(approved, created.revision)
            with self.assertRaisesRegex(ValidationError, "revision"):
                store.save(replace(saved, operator_role="COLORIST"), created.revision)

            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(ValidationError):
                store.get(created.colorist_job_id, "PC_PERSONALE")

    def test_store_serializes_create_with_transition_without_losing_the_transition(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "colorist.json"
            primary = ColoristJobStore(path, "PC_PERSONALE")
            first = primary.create(job())
            second = job()
            create_reached_save = threading.Event()
            allow_create_save = threading.Event()

            class PausedCreateStore(ColoristJobStore):
                def _save(self, data):
                    create_reached_save.set()
                    if not allow_create_save.wait(5):
                        raise RuntimeError("test synchronization timeout")
                    super()._save(data)

            errors = []

            def create_second():
                try:
                    PausedCreateStore(path, "PC_PERSONALE").create(second)
                except Exception as exc:  # pragma: no cover - asserted below
                    errors.append(exc)

            create_thread = threading.Thread(target=create_second)
            create_thread.start()
            self.assertTrue(create_reached_save.wait(5))

            current = primary.get(first.colorist_job_id, "PC_PERSONALE")
            approved = approve_colorist_job(current, current.plan_fingerprint, "ALESSIO")

            def save_transition():
                try:
                    primary.save(approved, current.revision)
                except Exception as exc:  # pragma: no cover - asserted below
                    errors.append(exc)

            transition_thread = threading.Thread(target=save_transition)
            transition_thread.start()
            transition_thread.join(0.25)
            allow_create_save.set()
            create_thread.join(5)
            transition_thread.join(5)

            self.assertFalse(create_thread.is_alive())
            self.assertFalse(transition_thread.is_alive())
            self.assertEqual([], errors)
            self.assertEqual(
                "APPROVED",
                primary.get(first.colorist_job_id, "PC_PERSONALE").state,
            )
            self.assertEqual(
                "PREPARED",
                primary.get(second.colorist_job_id, "PC_PERSONALE").state,
            )

    def test_registry_rejects_foreign_workstation_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "colorist.json"
            path.write_text(json.dumps({
                "schema": "ARPHE_COLORIST_JOBS_V1",
                "workstation_id": "PC_SEGRETERIA",
                "jobs": {},
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "workstation"):
                ColoristJobStore(path, "PC_PERSONALE").list_jobs()

    def test_apply_evidence_cannot_name_an_arbitrary_version(self):
        approved = approve_colorist_job(job(), job().plan_fingerprint, "ALESSIO")
        applying = record_colorist_apply_started(approved)
        with self.assertRaisesRegex(ValidationError, "Evidenza"):
            record_colorist_apply(applying, ({
                "clip_id": "clip-a", "before_version": "Original", "after_version": "Foreign",
                "reference_clip_id": "clip-a", "cdl_applied_directly": True,
                "drx_preset_name": None,
            },))

    def test_review_requires_preview_restore_and_manual_failure_is_distinct(self):
        prepared = job()
        approved = approve_colorist_job(prepared, prepared.plan_fingerprint, "ALESSIO")
        applying = record_colorist_apply_started(approved)
        names = after_version_names(applying)
        applied = record_colorist_apply(applying, tuple({
            "clip_id": clip_id, "before_version": "Original", "after_version": names[clip_id],
            "reference_clip_id": "clip-a", "cdl_applied_directly": clip_id == "clip-a",
            "drx_preset_name": None,
        } for clip_id in applying.clip_ids))
        previewing = record_colorist_preview_start(applied, "clip-a", names["clip-a"])
        with self.assertRaisesRegex(ValidationError, "preview"):
            record_colorist_review(previewing, True, "ALESSIO")

        failed = record_colorist_apply_failure(applying, {
            "ok": False, "recoverable": False, "manual_recovery_required": True,
            "stage": "apply_colorist", "error": "restore failed",
            "created_versions": [], "restored_clip_ids": [],
        })
        self.assertEqual("FAILED_MANUAL", failed.state)


if __name__ == "__main__":
    unittest.main()
