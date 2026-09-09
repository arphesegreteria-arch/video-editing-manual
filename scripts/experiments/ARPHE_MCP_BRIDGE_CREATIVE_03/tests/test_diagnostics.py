from __future__ import annotations

from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.diagnostic_tools import (capture_timeline_frames, _validate_offsets,
                                     frame_to_timecode)  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402


class FakeTimeline:
    def __init__(self):
        self.timecode = "01:00:00:10"

    def GetName(self):
        return "ARPHE_TEST_TIMELINE"

    def GetStartFrame(self):
        return 108000

    def GetEndFrame(self):
        return 108150

    def GetSetting(self, name):
        return "30" if name == "timelineFrameRate" else None

    def GetCurrentTimecode(self):
        return self.timecode

    def SetCurrentTimecode(self, value):
        self.timecode = value
        return True


class FakeResolve:
    def __init__(self):
        self.page = "fusion"

    def GetCurrentPage(self):
        return self.page

    def OpenPage(self, page):
        self.page = page
        return True


class FakeProject:
    def GetName(self):
        return "ARPHE_TEST_PROJECT"

    def ExportCurrentFrameAsStill(self, path):
        Path(path).write_bytes(b"fake-png")
        return True


class FakeRegistry:
    def timeline_allowed(self, project, timeline):
        return project == "ARPHE_TEST_PROJECT" and timeline == "ARPHE_TEST_TIMELINE"


class DiagnosticTests(unittest.TestCase):
    def test_frame_to_timecode_uses_absolute_timeline_frame(self):
        self.assertEqual("01:00:00:00", frame_to_timecode(108000, 30))
        self.assertEqual("01:00:04:29", frame_to_timecode(108149, 30))

    def test_offsets_are_bounded_and_deduplicated(self):
        start, fps, offsets = _validate_offsets(FakeTimeline(), [0, 1, 1, 149])
        self.assertEqual(108000, start)
        self.assertEqual(30, fps)
        self.assertEqual([0, 1, 149], offsets)

    def test_batch_and_range_limits(self):
        for invalid in ([], list(range(9)), [-1], [150], [True], [1.5]):
            with self.assertRaises(ValidationError):
                _validate_offsets(FakeTimeline(), invalid)

    def test_capture_restores_page_and_playhead_and_returns_images(self):
        resolve = FakeResolve()
        timeline = FakeTimeline()
        original_timecode = timeline.timecode
        with tempfile.TemporaryDirectory() as directory:
            config = SimpleNamespace(render_root=Path(directory), allowed_timelines=[])
            result = capture_timeline_frames(
                resolve, FakeProject(), timeline, config, FakeRegistry(), [0, 2]
            )
            self.assertEqual(3, len(result))
            self.assertTrue(result[0]["ok"])
            self.assertEqual([0, 2], [entry["frame_offset"] for entry in result[0]["captures"]])
            self.assertTrue(result[0]["playhead_restored"])
            self.assertEqual("fusion", resolve.page)
            self.assertEqual(original_timecode, timeline.timecode)
            self.assertEqual(2, len(list((Path(directory) / "diagnostics").glob("*.jpg"))))


if __name__ == "__main__":
    unittest.main()
