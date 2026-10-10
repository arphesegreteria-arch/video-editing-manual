from __future__ import annotations
from pathlib import Path
import sys
import tempfile
import unittest
from dataclasses import replace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.branded_longform_jobs import BrandedLongformJobStore, new_branded_longform_job  # noqa: E402


class BrandedLongformWorkflowTests(unittest.TestCase):
    def test_propose_approve_and_build_application_are_fingerprint_bound(self):
        from bridge.branded_longform_workflow import propose_batch, approve_batch, application_for_job
        with tempfile.TemporaryDirectory() as raw:
            store = BrandedLongformJobStore(Path(raw) / "jobs.json", "PC_PERSONALE")
            job = store.create(new_branded_longform_job(
                "Project", "Original", "source", "profile", profile_id="ARPHE_LONGFORM_EDITORIAL"))
            proposed = propose_batch(store, job.job_id, [
                {"class": "ARGUE", "start": 1, "end": 2, "fps": 30}
            ])
            fingerprint = proposed.proposal_card["fingerprint"]
            approved = approve_batch(store, job.job_id, fingerprint,
                                     [{"proposal_id": "P001", "decision": "APPROVE"}], "ALESSIO")
            application = application_for_job(approved)
            self.assertEqual("P001", application[0]["proposal_id"])
            with self.assertRaisesRegex(Exception, "fingerprint"):
                approve_batch(store, job.job_id, "0" * 64,
                              [{"proposal_id": "P001", "decision": "APPROVE"}], "ALESSIO")

    def test_retry_skips_already_verified_operations(self):
        from bridge.branded_longform_workflow import propose_batch, approve_batch, application_for_job
        with tempfile.TemporaryDirectory() as raw:
            store = BrandedLongformJobStore(Path(raw) / "jobs.json", "PC_PERSONALE")
            job = store.create(new_branded_longform_job(
                "Project", "Original", "source", "profile", profile_id="ARPHE_LONGFORM_EDITORIAL"))
            proposed = propose_batch(store, job.job_id, [
                {"class": "ARGUE", "start": 1, "end": 2, "fps": 30},
                {"class": "EXPLAIN", "start": 3, "end": 4, "fps": 30},
            ])
            approved = approve_batch(
                store, job.job_id, proposed.proposal_card["fingerprint"],
                [{"proposal_id": "P001", "decision": "APPROVE"},
                 {"proposal_id": "P002", "decision": "APPROVE"}], "ALESSIO")
            resumed = replace(approved, state="BLOCKED", operations=(
                {"proposal_id": "P001", "status": "VERIFIED"},
            ))
            self.assertEqual(["P002"], [item["proposal_id"] for item in application_for_job(resumed)])

    def test_retry_does_not_duplicate_a_recorded_block(self):
        from bridge.branded_longform_workflow import propose_batch, approve_batch, application_for_job
        with tempfile.TemporaryDirectory() as raw:
            store = BrandedLongformJobStore(Path(raw) / "jobs.json", "PC_PERSONALE")
            job = store.create(new_branded_longform_job(
                "Project", "Original", "source", "profile", profile_id="CARABELLESE_LONGFORM_EDITORIAL"))
            proposed = propose_batch(store, job.job_id, [
                {"class": "ARGUE", "start": 1, "end": 2, "fps": 30},
            ])
            approved = approve_batch(
                store, job.job_id, proposed.proposal_card["fingerprint"],
                [{"proposal_id": "P001", "decision": "APPROVE"}], "ALESSIO")
            blocked = replace(approved, state="BLOCKED", operations=(
                {"proposal_id": "P001", "status": "BLOCKED", "reason": "KIT_PENDING"},
            ))
            self.assertEqual((), application_for_job(blocked))
