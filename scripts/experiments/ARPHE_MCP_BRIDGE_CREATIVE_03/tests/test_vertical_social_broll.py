from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class BrollPlanTests(unittest.TestCase):
    def test_provided_broll_requires_explicit_asset_and_ranges(self):
        from bridge.vertical_social_broll import validate_provided_broll
        result = validate_provided_broll({
            "type": "B_ROLL_PROVIDED", "state": "APPROVED", "reason": "mostrare studio",
            "timeline_range": {"start_frame": 30, "end_frame": 90},
            "source_range": {"start_frame": 0, "end_frame": 60},
            "asset_path": "C:/allowed/studio.mov",
        }, 300)
        self.assertEqual((30, 90), result["timeline_range"])

    def test_generated_broll_stays_blocked_without_provider_gate(self):
        from bridge.vertical_social_broll import validate_generated_broll
        with self.assertRaisesRegex(Exception, "bloccato"):
            validate_generated_broll({"type": "B_ROLL_GENERATED"})

    def test_apply_provided_broll_writes_only_provisional_track_and_reads_duration(self):
        from bridge.vertical_social_broll import apply_provided_broll

        class Appended:
            def GetDuration(self): return 60

        class Timeline:
            def __init__(self): self.tracks = 1
            def GetName(self): return "__ARPHE_VERTICAL_PLAN"
            def AddTrack(self, kind): self.tracks += 1; return kind == "video"
            def GetTrackCount(self, kind): return self.tracks

        class Pool:
            def __init__(self): self.payload = None
            def AppendToTimeline(self, payload): self.payload = payload; return [Appended()]

        class Project:
            def __init__(self, pool): self.pool = pool
            def GetMediaPool(self): return self.pool

        action = {
            "type": "B_ROLL_PROVIDED", "state": "APPROVED", "reason": "mostrare studio",
            "timeline_range": {"start_frame": 30, "end_frame": 90},
            "source_range": {"start_frame": 0, "end_frame": 60},
            "asset_path": "C:/allowed/studio.mov",
        }
        pool = Pool()
        with tempfile.TemporaryDirectory() as raw, \
                patch("bridge.vertical_social_broll.allowed_media", return_value=Path(raw) / "studio.mov"), \
                patch("bridge.vertical_social_broll.import_media_item", return_value=object()):
            result = apply_provided_broll(object(), Project(pool), Timeline(), SimpleNamespace(), action, 300)
        self.assertTrue(result["ok"])
        self.assertEqual(2, result["track_index"])
        self.assertEqual(2, pool.payload[0]["trackIndex"])
