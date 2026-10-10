from __future__ import annotations
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.branded_longform_jobs import new_branded_longform_job  # noqa: E402


class FakeTimeline:
    def __init__(self, project, name):
        self.project = project; self.name = name; self.markers = {}; self.items = []
    def GetName(self): return self.name
    def DuplicateTimeline(self, name):
        duplicate = FakeTimeline(self.project, name); self.project.timelines.append(duplicate); return duplicate
    def AddMarker(self, frame, color, name, note, duration, custom):
        if frame in self.markers: return False
        self.markers[frame] = {"color": color, "name": name, "note": note, "duration": duration, "customData": custom}
        return True
    def GetMarkers(self): return dict(self.markers)
    def GetTrackCount(self, kind): return 1 if kind == "video" else 0
    def GetItemListInTrack(self, kind, index): return list(self.items)


class FakeClip:
    def __init__(self, start, end, name="clip"): self.start = start; self.end = end; self.name = name
    def GetStart(self): return self.start
    def GetEnd(self): return self.end
    def GetName(self): return self.name


class FakeProject:
    def __init__(self):
        original = FakeTimeline(self, "Original")
        self.timelines = [original]; self.current = original
    def GetName(self): return "Project"
    def GetCurrentTimeline(self): return self.current
    def GetTimelineCount(self): return len(self.timelines)
    def GetTimelineByIndex(self, index): return self.timelines[index - 1]
    def SetCurrentTimeline(self, timeline): self.current = timeline; return True


class BrandedLongformResolveTests(unittest.TestCase):
    def test_cleanup_and_editorial_are_created_without_mutating_original(self):
        from bridge.branded_longform_resolve import create_cleanup_timeline, create_editorial_timeline
        project = FakeProject()
        job = new_branded_longform_job("Project", "Original", "source", "profile")
        cleanup = create_cleanup_timeline(project, job)
        self.assertEqual("Original_CLEANUP", cleanup["created_timeline"])
        self.assertEqual("Original", project.current.GetName())
        editorial = create_editorial_timeline(project, job)
        self.assertEqual("Original_EDITORIAL", editorial["created_timeline"])
        self.assertEqual("Original", project.current.GetName())
        self.assertEqual(3, len(project.timelines))

    def test_proposal_markers_are_idempotent_and_source_bound(self):
        from bridge.branded_longform_resolve import create_cleanup_timeline, add_proposal_markers
        project = FakeProject(); job = new_branded_longform_job("Project", "Original", "source", "profile")
        create_cleanup_timeline(project, job)
        proposals = [{"proposal_id": "P001", "start_frame": 30, "kind": "KEYWORD_BOX", "rationale": "tesi"}]
        first = add_proposal_markers(project, job, proposals)
        second = add_proposal_markers(project, job, proposals)
        self.assertEqual(1, first["added"])
        self.assertEqual(0, second["added"])

    def test_original_timeline_content_change_invalidates_job(self):
        from bridge.branded_longform_resolve import timeline_structure_fingerprint, create_cleanup_timeline
        project = FakeProject(); original = project.current
        original.items.append(FakeClip(0, 100))
        fingerprint = timeline_structure_fingerprint(original)
        job = new_branded_longform_job(
            "Project", "Original", "source", "profile",
            original_timeline_fingerprint=fingerprint)
        original.items[0].end = 101
        with self.assertRaisesRegex(Exception, "modificata"):
            create_cleanup_timeline(project, job)
