from __future__ import annotations
import importlib
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

class VerticalSocialCutPolicyTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec("bridge.vertical_social_cuts"))
        return importlib.import_module("bridge.vertical_social_cuts")

    def test_only_approved_cut_actions_become_non_overlapping_ranges(self):
        module = self.module()
        plan = {
            "actions": [
                {"action_id": "cut-1", "type": "CUT", "state": "APPROVED",
                 "phase": "PROVISIONAL_EDIT", "range": {"start_frame": 20, "end_frame": 40},
                 "reason": "ripetizione"},
                {"action_id": "cut-2", "type": "CUT", "state": "APPROVED",
                 "phase": "PROVISIONAL_EDIT", "range": {"start_frame": 60, "end_frame": 80},
                 "reason": "pausa"},
                {"action_id": "broll", "type": "B_ROLL", "state": "APPROVED",
                 "phase": "PROVISIONAL_EDIT"},
            ]
        }
        self.assertEqual(((20, 40), (60, 80)), module.approved_cut_ranges(plan, 100))

    def test_invalid_or_overlapping_ranges_fail_closed(self):
        module = self.module()
        with self.assertRaisesRegex(Exception, "overlap"):
            module.approved_cut_ranges({"actions": [
                {"type": "CUT", "state": "APPROVED", "reason": "ripetizione", "range": {"start_frame": 20, "end_frame": 50}},
                {"type": "CUT", "state": "APPROVED", "reason": "pausa", "range": {"start_frame": 40, "end_frame": 60}},
            ]}, 100)

    def test_provisional_timeline_keeps_non_cut_ranges_and_leaves_source_untouched(self):
        module = self.module()

        class SourceItem:
            def __init__(self, media): self.media = media
            def GetMediaPoolItem(self): return self.media
            def GetStart(self): return 0
            def GetDuration(self): return 100

        class SourceTimeline:
            def __init__(self, media): self.media = media
            def GetTrackCount(self, kind): return 1
            def GetItemListInTrack(self, kind, index): return [SourceItem(self.media)]

        class ProvisionalTimeline:
            def __init__(self, name): self.name, self.appended = name, []
            def GetName(self): return self.name
            def GetTrackCount(self, kind): return 1
            def GetItemListInTrack(self, kind, index):
                media_type = 1 if kind == "video" else 2
                return [type("Item", (), {"GetDuration": lambda item, entry=entry: entry["endFrame"] - entry["startFrame"]})()
                        for entry in self.appended if entry["mediaType"] == media_type]

        class Pool:
            def __init__(self): self.current = None
            def CreateEmptyTimeline(self, name): return ProvisionalTimeline(name)
            def AppendToTimeline(self, entries):
                self.current.appended.extend(entries)
                return True

        class Project:
            def __init__(self, pool): self.pool, self.current, self.timelines = pool, None, []
            def GetMediaPool(self): return self.pool
            def SetCurrentTimeline(self, timeline):
                self.current = timeline
                self.pool.current = timeline
                if timeline not in self.timelines: self.timelines.append(timeline)
                return True
            def GetTimelineCount(self): return len(self.timelines)
            def GetTimelineByIndex(self, index): return self.timelines[index - 1]

        media = object()
        pool = Pool()
        project = Project(pool)
        source = SourceTimeline(media)
        result = module.create_provisional_cut_timeline(project, source, {
            "plan_id": "vertical_12345678123456781234567812345678",
            "actions": [
                {"type": "CUT", "state": "APPROVED", "reason": "pausa",
                 "range": {"start_frame": 20, "end_frame": 40}},
                {"type": "CUT", "state": "APPROVED", "reason": "ripetizione",
                 "range": {"start_frame": 60, "end_frame": 80}},
            ],
        }, total_frames=100)

        self.assertEqual("__ARPHE_VERTICAL_VERTICAL_12345678123456781234567812345678", result.GetName())
        self.assertIs(project.current, result)
        self.assertEqual(6, len(result.appended))
        self.assertEqual([(0, 20), (40, 60), (80, 100)], [
            (entry["startFrame"], entry["endFrame"]) for entry in result.appended[::2]
        ])
        self.assertTrue(all(entry["mediaPoolItem"] is media for entry in result.appended))
        self.assertEqual([0, 0, 20, 20, 40, 40], [entry["recordFrame"] for entry in result.appended])

    def test_existing_valid_provisional_timeline_is_reused_idempotently(self):
        module = self.module()

        class Item:
            def __init__(self, media, duration=100): self.media, self.duration = media, duration
            def GetMediaPoolItem(self): return self.media
            def GetStart(self): return 0
            def GetDuration(self): return self.duration

        class Timeline:
            def __init__(self, name, media, durations): self.name, self.media, self.durations = name, media, durations
            def GetName(self): return self.name
            def GetTrackCount(self, kind): return 1
            def GetItemListInTrack(self, kind, index):
                return [Item(self.media, duration) for duration in self.durations]

        class Pool:
            def CreateEmptyTimeline(self, name): raise AssertionError("must reuse")

        class Project:
            def __init__(self, pool, existing): self.pool, self.existing, self.current = pool, existing, None
            def GetMediaPool(self): return self.pool
            def GetTimelineCount(self): return 1
            def GetTimelineByIndex(self, index): return self.existing
            def SetCurrentTimeline(self, timeline): self.current = timeline; return True

        media = object()
        existing = Timeline("__ARPHE_VERTICAL_VERTICAL_12345678123456781234567812345678", media, [20, 20, 20])
        project = Project(Pool(), existing)
        source = Timeline("ORIGINAL", media, [100])
        result = module.create_provisional_cut_timeline(project, source, {
            "plan_id": "vertical_12345678123456781234567812345678",
            "actions": [
                {"type": "CUT", "state": "APPROVED", "reason": "pausa", "range": {"start_frame": 20, "end_frame": 40}},
                {"type": "CUT", "state": "APPROVED", "reason": "ripetizione", "range": {"start_frame": 60, "end_frame": 80}},
            ],
        }, total_frames=100)
        self.assertIs(existing, result)
        self.assertIs(existing, project.current)

if __name__ == "__main__":
    unittest.main()
