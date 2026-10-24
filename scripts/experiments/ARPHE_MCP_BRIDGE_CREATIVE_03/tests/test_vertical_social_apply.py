from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class VerticalSocialApplyTests(unittest.TestCase):
    class Item:
        def __init__(self, start, end):
            self.start, self.end = start, end
        def GetStart(self): return self.start
        def GetEnd(self): return self.end

    class Timeline:
        def __init__(self, name, items, start_frame=0):
            self.name, self.items, self.start_frame = name, items, start_frame
        def GetName(self): return self.name
        def GetStartFrame(self): return self.start_frame
        def GetItemListInTrack(self, kind, index):
            return self.items if kind == "video" and index == 1 else []
        def GetSetting(self, key):
            return {"timelineResolutionWidth": "1080", "timelineResolutionHeight": "1920"}.get(key)

    class Project:
        def __init__(self, timelines): self.timelines = timelines
        def GetTimelineCount(self): return len(self.timelines)
        def GetTimelineByIndex(self, index): return self.timelines[index - 1]

    def test_finds_one_owned_provisional_timeline(self):
        from bridge.vertical_social_apply import find_provisional_timeline
        expected = self.Timeline("__ARPHE_VERTICAL_VERTICAL_ABC12345ABC12345ABC12345ABC12345", [])
        project = self.Project([self.Timeline("SOURCE", []), expected])
        self.assertIs(expected, find_provisional_timeline(project, "vertical_abc12345abc12345abc12345abc12345"))

    def test_finds_timeline_created_for_full_generated_plan_id(self):
        from bridge.vertical_social_apply import find_provisional_timeline
        plan_id = "vertical_0123456789abcdef0123456789abcdef"
        expected = self.Timeline("__ARPHE_VERTICAL_VERTICAL_0123456789ABCDEF0123456789ABCDEF", [])
        self.assertIs(expected, find_provisional_timeline(self.Project([expected]), plan_id))

    def test_reframe_requires_one_exact_clip_and_reads_back_fusion(self):
        from bridge.vertical_social_apply import apply_reframe_action
        timeline = self.Timeline("__ARPHE_VERTICAL_VERTICAL_ABC12345ABC12345ABC12345ABC12345", [self.Item(0, 40), self.Item(40, 80)])
        action = {"action_id": "r1", "type": "REFRAME", "state": "APPROVED",
                  "range": {"start_frame": 0, "end_frame": 40},
                  "target": {"kind": "person", "label": "speaker"},
                  "anchor": {"x": 0.55, "y": 0.5}, "reason": "mantieni volto",
                  "zoom": 1.03,
                  "rotation_keys": [
                      {"frame": 0, "angle": -0.4}, {"frame": 39, "angle": 0.1},
                  ]}
        with patch("bridge.vertical_social_apply.apply_fusion_reframe", return_value=True) as apply:
            result = apply_reframe_action(timeline, action, 80)
        self.assertEqual("r1", result["action_id"])
        self.assertEqual([0, 40], result["range"])
        self.assertEqual(1.03, result["zoom"])
        self.assertEqual(
            [{"frame": 0, "angle": -0.4}, {"frame": 39, "angle": 0.1}],
            result["rotation_keys"],
        )
        apply.assert_called_once()

    def test_reframe_rejects_partial_clip_geometry(self):
        from bridge.vertical_social_apply import apply_reframe_action
        timeline = self.Timeline("__ARPHE_VERTICAL_VERTICAL_ABC12345ABC12345ABC12345ABC12345", [self.Item(0, 80)])
        action = {"action_id": "r1", "type": "REFRAME", "state": "APPROVED",
                  "range": {"start_frame": 20, "end_frame": 60},
                  "target": {"kind": "person", "label": "speaker"},
                  "anchor": {"x": 0.5, "y": 0.5}, "reason": "mantieni volto"}
        with self.assertRaisesRegex(Exception, "confini di una clip"):
            apply_reframe_action(timeline, action, 80)

    def test_reframe_matches_relative_action_range_on_nonzero_timeline(self):
        from bridge.vertical_social_apply import apply_reframe_action
        timeline = self.Timeline(
            "__ARPHE_VERTICAL_VERTICAL_ABC12345ABC12345ABC12345ABC12345",
            [self.Item(108000, 108040)], start_frame=108000,
        )
        action = {"action_id": "r1", "type": "REFRAME", "state": "APPROVED",
                  "range": {"start_frame": 0, "end_frame": 40},
                  "target": {"kind": "reference_line", "label": "soffitto"},
                  "anchor": {"x": 0.5, "y": 0.5}, "reason": "linea soffitto"}
        with patch("bridge.vertical_social_apply.apply_fusion_reframe", return_value=True):
            result = apply_reframe_action(timeline, action, 40)
        self.assertTrue(result["ok"])

    def test_reframe_evidence_preserves_absolute_center_keys(self):
        from bridge.vertical_social_apply import apply_reframe_action
        timeline = self.Timeline(
            "__ARPHE_VERTICAL_VERTICAL_ABC12345ABC12345ABC12345ABC12345",
            [self.Item(108000, 108040)], start_frame=108000,
        )
        center_keys = [
            {"frame": 0, "x": 0.5, "y": 0.49},
            {"frame": 20, "x": 0.5, "y": 0.51},
            {"frame": 39, "x": 0.5, "y": 0.505},
        ]
        action = {
            "action_id": "r-center", "type": "REFRAME", "state": "APPROVED",
            "range": {"start_frame": 0, "end_frame": 40},
            "target": {"kind": "reference_line", "label": "soffitto"},
            "anchor": {"x": 0.5, "y": 0.5}, "reason": "linea soffitto",
            "center_keys": center_keys,
        }
        with patch("bridge.vertical_social_apply.apply_fusion_reframe", return_value=True):
            result = apply_reframe_action(timeline, action, 40)
        self.assertEqual(center_keys, result["center_keys"])
