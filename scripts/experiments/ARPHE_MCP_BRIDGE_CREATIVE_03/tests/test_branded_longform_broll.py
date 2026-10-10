from __future__ import annotations

from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class BrandedLongformBrollTests(unittest.TestCase):
    def test_applies_exact_approved_broll_to_editorial_timeline(self):
        from bridge.branded_longform_broll import apply_provided_broll
        item = SimpleNamespace(GetDuration=lambda: 60)
        timeline = SimpleNamespace(GetName=lambda: "Original_EDITORIAL", AddTrack=lambda kind: True,
                                   GetTrackCount=lambda kind: 2)
        pool = SimpleNamespace(AppendToTimeline=lambda records: [item])
        project = SimpleNamespace(GetMediaPool=lambda: pool)
        job = SimpleNamespace(profile_id="ARPHE_LONGFORM_EDITORIAL", editorial_timeline="Original_EDITORIAL")
        proposal = {"proposal_id": "P001", "kind": "B_ROLL_PROVIDED", "asset_path": "asset.mov",
                    "source_start_frame": 10, "source_end_frame": 70, "start_frame": 30, "end_frame": 90}
        with patch("bridge.branded_longform_broll.allowed_media", return_value=Path("asset.mov")), \
             patch("bridge.branded_longform_broll.import_media_item", return_value=object()):
            result = apply_provided_broll(object(), project, timeline, SimpleNamespace(), job, proposal)
        self.assertTrue(result["ok"])
        self.assertEqual([30, 90], result["range"])
