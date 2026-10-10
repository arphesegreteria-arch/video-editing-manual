from __future__ import annotations
from pathlib import Path
import sys
import tempfile
import unittest
from dataclasses import replace
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

class BrandedLongformJobTests(unittest.TestCase):
    def test_job_binds_original_and_expected_derived_timelines(self):
        from bridge.branded_longform_jobs import new_branded_longform_job, verify_job_binding
        job = new_branded_longform_job("Project", "Original", "source-fp", "profile-fp")
        self.assertEqual("Original", job.original_timeline)
        self.assertEqual("Original_CLEANUP", job.cleanup_timeline)
        self.assertEqual("Original_EDITORIAL", job.editorial_timeline)
        verify_job_binding(job, "Project", "Original", "source-fp", "profile-fp")
        with self.assertRaisesRegex(Exception, "sorgente"):
            verify_job_binding(job, "Project", "Original", "changed", "profile-fp")

    def test_store_is_workstation_scoped_and_idempotent(self):
        from bridge.branded_longform_jobs import BrandedLongformJobStore, new_branded_longform_job
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "jobs.json"
            store = BrandedLongformJobStore(path, "PC_PERSONALE")
            job = new_branded_longform_job("Project", "Original", "source-fp", "profile-fp",
                                           workstation_id="PC_PERSONALE")
            self.assertEqual(job, store.create(job))
            self.assertEqual(job, store.create(job))
            self.assertEqual(job, store.get(job.job_id))
            proposed = store.update(replace(job, state="PROPOSED", proposal_card={"card_count": 1}), 0)
            self.assertEqual(1, proposed.revision)
            self.assertEqual("PROPOSED", store.get(job.job_id).state)
            with self.assertRaisesRegex(Exception, "revision"):
                store.update(replace(proposed, state="APPROVED"), 0)
            with self.assertRaisesRegex(Exception, "workstation"):
                BrandedLongformJobStore(path, "PC_SEGRETERIA")

    def test_store_reuses_active_job_for_same_immutable_binding(self):
        from bridge.branded_longform_jobs import BrandedLongformJobStore, new_branded_longform_job
        with tempfile.TemporaryDirectory() as raw:
            store = BrandedLongformJobStore(Path(raw) / "jobs.json", "PC_PERSONALE")
            first = store.create(new_branded_longform_job(
                "Project", "Original", "source-fp", "profile-fp",
                workstation_id="PC_PERSONALE", profile_id="ARPHE_LONGFORM_EDITORIAL"))
            self.assertEqual(first, store.find_active(
                "Project", "Original", "source-fp", "profile-fp",
                "ARPHE_LONGFORM_EDITORIAL"))
            self.assertIsNone(store.find_active(
                "Project", "Original", "changed-source", "profile-fp",
                "ARPHE_LONGFORM_EDITORIAL"))
