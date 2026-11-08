from __future__ import annotations

import base64
import unittest

from bridge.review_export21 import export_review_frames21, validate_review_target
from bridge.safety import ValidationError


JPG = base64.b64encode(b"fake-jpeg").decode("ascii")


class Timeline:
    def __init__(self):
        self.frame_calls = []
        self.grid_calls = []

    def GetStartFrame(self): return 108000
    def GetEndFrame(self): return 108300
    def GetSetting(self, name): return "30" if name == "timelineFrameRate" else None

    def ExportFrame(self, offset, options):
        self.frame_calls.append((offset, options))
        return {"success": True, "data": JPG, "width": 720, "height": 1280}

    def ExportThumbnails(self, frames, options):
        self.grid_calls.append((frames, options))
        return {"success": True, "data": JPG, "width": 1600, "height": 900,
                "columns": 2, "rows": 1}


class ReviewExport21Tests(unittest.TestCase):
    def test_review_target_must_be_registered_or_allowlisted(self):
        project = type("Project", (), {"GetName": lambda self: "ARPHE_TEST"})()
        timeline = type("NamedTimeline", (), {"GetName": lambda self: "ARPHE_TIMELINE"})()
        config = type("Config", (), {"allowed_projects": (), "allowed_timelines": ()})()
        registry = type("Registry", (), {"timeline_allowed": lambda *_: False})()
        with self.assertRaises(ValidationError):
            validate_review_target(project, timeline, config, registry)

    def test_exports_bounded_roi_frames_without_moving_playhead(self):
        timeline = Timeline()
        result = export_review_frames21(
            timeline, [0, 90], "frames",
            {"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.4}, 1280, 88,
        )
        self.assertEqual(3, len(result))
        self.assertEqual([0, 90], [call[0] for call in timeline.frame_calls])
        self.assertEqual(0.1, timeline.frame_calls[0][1]["roiX"])
        self.assertNotIn("SetCurrentTimecode", timeline.__class__.__dict__)
        self.assertEqual(2, result[0]["capture_count"])

    def test_exports_one_labelled_grid(self):
        timeline = Timeline()
        result = export_review_frames21(timeline, [0, 30], "grid", None, 1600, 90)
        self.assertEqual(2, len(result))
        frames, options = timeline.grid_calls[0]
        self.assertEqual("01:00:00:00", frames[0]["label"])
        self.assertEqual("01:00:01:00", frames[1]["label"])
        self.assertEqual("encodedString", options["outputType"])

    def test_rejects_invalid_roi_before_resolve_call(self):
        timeline = Timeline()
        with self.assertRaises(ValidationError):
            export_review_frames21(
                timeline, [0], "frames",
                {"x": 0.8, "y": 0.0, "width": 0.3, "height": 1.0}, 1280, 90,
            )
        self.assertEqual([], timeline.frame_calls)

    def test_rejects_nan_roi_before_resolve_call(self):
        timeline = Timeline()
        with self.assertRaises(ValidationError):
            export_review_frames21(
                timeline, [0], "frames",
                {"x": float("nan"), "y": 0.0, "width": 0.3, "height": 1.0}, 1280, 90,
            )
        self.assertEqual([], timeline.frame_calls)

    def test_rejects_more_than_eight_frames(self):
        with self.assertRaises(ValidationError):
            export_review_frames21(Timeline(), list(range(9)), "frames", None, 1280, 90)

    def test_rejects_missing_native_api(self):
        class OldTimeline:
            def GetStartFrame(self): return 0
            def GetEndFrame(self): return 30
            def GetSetting(self, _): return "30"

        with self.assertRaises(ValidationError):
            export_review_frames21(OldTimeline(), [0], "frames", None, 1280, 90)


if __name__ == "__main__":
    unittest.main()
