from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class EditPointInspectionTests(unittest.TestCase):
    def test_reports_exact_audio_boundaries_and_detects_a_gap(self):
        from bridge.edit_point_inspection import inspect_edit_points

        class Item:
            def __init__(self, start, end, source_start, name):
                self.start = start
                self.end = end
                self.source_start = source_start
                self.name = name
            def GetStart(self): return self.start
            def GetEnd(self): return self.end
            def GetDuration(self): return self.end - self.start
            def GetSourceStartFrame(self): return self.source_start
            def GetMediaPoolItem(self): return self
            def GetClipProperty(self, key): return self.name if key == "File Name" else ""

        class Timeline:
            def GetTrackCount(self, kind): return 1
            def GetItemListInTrack(self, kind, index):
                return [Item(100, 150, 20, "source-a.mp4"), Item(153, 200, 90, "source-a.mp4")]

        result = inspect_edit_points(Timeline())

        self.assertEqual((150, 153), result["audio"]["edit_points"][0]["timeline_range"])
        self.assertEqual("gap", result["audio"]["edit_points"][0]["relationship"])
        self.assertEqual(3, result["audio"]["edit_points"][0]["delta_frames"])
        self.assertEqual("source-a.mp4", result["audio"]["clips"][0]["source_name"])

    def test_marks_contiguous_video_items_without_inventing_an_audio_fix(self):
        from bridge.edit_point_inspection import inspect_edit_points

        class Item:
            def __init__(self, start, end): self.start, self.end = start, end
            def GetStart(self): return self.start
            def GetEnd(self): return self.end
            def GetDuration(self): return self.end - self.start
            def GetSourceStartFrame(self): return 0
            def GetMediaPoolItem(self): return None

        class Timeline:
            def GetTrackCount(self, kind): return 1
            def GetItemListInTrack(self, kind, index): return [Item(0, 30), Item(30, 60)]

        result = inspect_edit_points(Timeline())

        self.assertEqual("contiguous", result["video"]["edit_points"][0]["relationship"])
        self.assertEqual(0, result["video"]["edit_points"][0]["delta_frames"])

