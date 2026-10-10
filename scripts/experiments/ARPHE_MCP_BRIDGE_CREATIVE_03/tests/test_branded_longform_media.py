from __future__ import annotations
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class BrandedLongformMediaTests(unittest.TestCase):
    def test_obs_package_keeps_program_as_final_audio_and_requires_review_without_guides(self):
        from bridge.branded_longform_media import inspect_longform_sources, build_sync_plan
        package = inspect_longform_sources({"mode": "OBS_MULTICAM", "program": {"path": "program.mov", "fps": 30}, "cameras": [{"label": "CAM_A", "path": "a.mov", "fps": 30, "guide_audio": True}, {"label": "CAM_B", "path": "b.mov", "fps": 30, "guide_audio": False}]})
        self.assertEqual("program.mov", package.final_audio_source)
        self.assertEqual("REVIEW_REQUIRED", build_sync_plan(package)["status"])

    def test_rejects_missing_program_and_mixed_fps(self):
        from bridge.branded_longform_media import inspect_longform_sources
        with self.assertRaisesRegex(Exception, "PROGRAM"):
            inspect_longform_sources({"mode": "OBS_MULTICAM", "cameras": []})
        with self.assertRaisesRegex(Exception, "frame rate"):
            inspect_longform_sources({"mode": "OBS_MULTICAM", "program": {"path": "p", "fps": 30}, "cameras": [{"label": "CAM_A", "path": "a", "fps": 24, "guide_audio": True}]})
