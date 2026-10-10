from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class Item:
    def __init__(self, start, end): self.start, self.end, self.props = start, end, {"AudioVolume": 0.0}
    def GetStart(self): return self.start
    def GetEnd(self): return self.end
    def SetProperty(self, name, value): self.props[name] = value; return True
    def GetProperty(self, name): return self.props[name]


class Timeline:
    def __init__(self, items): self.items = items
    def GetItemListInTrack(self, kind, index): return self.items if kind == "audio" else []


class VerticalSocialMusicTests(unittest.TestCase):
    def action(self):
        return {"action_id": "m1", "type": "MUSIC_DUCK", "state": "APPROVED",
                "range": {"start_frame": 0, "end_frame": 60}, "audio_track": 2,
                "gain_db": -12.0, "reason": "voce in primo piano"}

    def test_music_duck_sets_and_reads_one_exact_music_clip(self):
        from bridge.vertical_social_music import apply_music_duck
        item = Item(0, 60)
        result = apply_music_duck(Timeline([item]), self.action(), 60)
        self.assertEqual(-12.0, item.props["AudioVolume"])
        self.assertEqual(-12.0, result["gain_db"])

    def test_music_duck_rejects_partial_clip_or_unsafe_gain(self):
        from bridge.vertical_social_music import apply_music_duck
        with self.assertRaisesRegex(Exception, "confini"):
            apply_music_duck(Timeline([Item(0, 100)]), self.action(), 100)
        unsafe = self.action(); unsafe["gain_db"] = -80
        with self.assertRaisesRegex(Exception, "gain_db"):
            apply_music_duck(Timeline([Item(0, 60)]), unsafe, 60)
