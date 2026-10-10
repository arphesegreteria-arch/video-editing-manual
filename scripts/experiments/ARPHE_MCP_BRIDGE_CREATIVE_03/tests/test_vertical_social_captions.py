from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class VerticalSocialCaptionTests(unittest.TestCase):
    def action(self):
        return {"action_id": "cap", "type": "CAPTIONS", "state": "APPROVED",
                "locked_edit_fingerprint": "a" * 64,
                "cues": [
                    {"cue_id": "c1", "start_frame": 0, "end_frame": 20,
                     "text": "Prima frase", "position": "LOWER"},
                    {"cue_id": "c2", "start_frame": 30, "end_frame": 60,
                     "text": "Seconda frase", "position": "UPPER"},
                ], "reason": "sottotitoli approvati"}

    def test_caption_schema_preserves_gap_and_safe_positions(self):
        from bridge.vertical_social_captions import validate_caption_action
        result = validate_caption_action(self.action(), 60)
        self.assertEqual(((0, 20), (30, 60)), tuple(cue["range"] for cue in result["cues"]))

    def test_caption_schema_rejects_overlap_long_text_and_missing_lock_fingerprint(self):
        from bridge.vertical_social_captions import validate_caption_action
        overlap = self.action(); overlap["cues"][1]["start_frame"] = 10
        with self.assertRaisesRegex(Exception, "sovrapposte"):
            validate_caption_action(overlap, 60)
        long = self.action(); long["cues"][0]["text"] = "x" * 85
        with self.assertRaisesRegex(Exception, "84"):
            validate_caption_action(long, 60)
        missing = self.action(); missing["locked_edit_fingerprint"] = ""
        with self.assertRaisesRegex(Exception, "fingerprint"):
            validate_caption_action(missing, 60)

    def test_caption_schema_allows_picture_lock_placeholder_only_during_planning(self):
        from bridge.vertical_social_captions import validate_caption_action
        pending = self.action(); pending["locked_edit_fingerprint"] = "AT_PICTURE_LOCK"
        with self.assertRaisesRegex(Exception, "fingerprint"):
            validate_caption_action(pending, 60)
        result = validate_caption_action(pending, 60, allow_picture_lock_placeholder=True)
        self.assertEqual("AT_PICTURE_LOCK", result["locked_edit_fingerprint"])

    def test_caption_executor_uses_one_full_timeline_composition(self):
        from bridge.vertical_social_captions import apply_caption_action
        cfg = SimpleNamespace(palette={"burgundy": "#6C2438", "white": "#FFFFFF"})
        with patch("bridge.vertical_social_captions.create_overlay_composition", return_value=(object(), object())) as create, \
             patch("bridge.vertical_social_captions.build_caption_graph", return_value={"cue_count": 2, "text_readback": True}) as build:
            result = apply_caption_action(object(), object(), cfg, self.action(), 60)
        create.assert_called_once()
        build.assert_called_once()
        self.assertEqual(2, result["cue_count"])

    def test_edit_fingerprint_changes_when_same_length_media_is_replaced(self):
        from bridge.vertical_social_captions import timeline_edit_fingerprint

        class Media:
            def __init__(self, unique_id): self.unique_id = unique_id
            def GetUniqueId(self): return self.unique_id
            def GetClipProperty(self): return {"File Path": f"C:/private/{self.unique_id}.mp4"}
        class Item:
            def __init__(self, unique_id): self.media = Media(unique_id)
            def GetStart(self): return 0
            def GetEnd(self): return 60
            def GetDuration(self): return 60
            def GetMediaPoolItem(self): return self.media
        class Timeline:
            def __init__(self, unique_id): self.item = Item(unique_id)
            def GetStartFrame(self): return 0
            def GetEndFrame(self): return 60
            def GetSetting(self, key):
                return {"timelineResolutionWidth": "1080", "timelineResolutionHeight": "1920",
                        "timelineFrameRate": "30", "timelinePlaybackFrameRate": "30"}[key]
            def GetTrackCount(self, kind): return 1 if kind == "video" else 0
            def GetItemListInTrack(self, kind, index): return [self.item]

        first = timeline_edit_fingerprint(Timeline("source-a"))
        second = timeline_edit_fingerprint(Timeline("source-b"))
        self.assertNotEqual(first, second)
        self.assertEqual(first, timeline_edit_fingerprint(Timeline("source-a")))
