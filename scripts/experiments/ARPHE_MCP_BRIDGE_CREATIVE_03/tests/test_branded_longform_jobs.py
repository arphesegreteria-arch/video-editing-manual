from __future__ import annotations
from pathlib import Path
import sys
import unittest
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
