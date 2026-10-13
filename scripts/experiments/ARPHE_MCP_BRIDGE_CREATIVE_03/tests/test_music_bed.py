from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.config import DEFAULT_FLAGS


class Item:
    def __init__(self, name, start, end):
        self.name, self.start, self.end = name, start, end
        self.props = {"AudioVolume": 0.0}
    def GetName(self): return self.name
    def SetName(self, value): self.name = value; return True
    def GetStart(self): return self.start
    def GetEnd(self): return self.end
    def GetDuration(self): return self.end - self.start
    def SetProperty(self, name, value): self.props[name] = value; return True
    def GetProperty(self, name): return self.props.get(name)


class Timeline:
    def __init__(self): self.audio = [[]]; self.video = [[Item("video", 0, 100)]]
    def GetName(self): return "ARPHE_TEST"
    def GetTrackCount(self, kind): return len(self.audio if kind == "audio" else self.video)
    def AddTrack(self, kind): self.audio.append([]); return kind == "audio"
    def GetItemListInTrack(self, kind, index): return (self.audio if kind == "audio" else self.video)[index - 1]
    def DeleteClips(self, clips, _ripple):
        for track in self.audio:
            for item in clips:
                if item in track: track.remove(item)
        return True


class Pool:
    def __init__(self, timeline): self.timeline = timeline
    def ImportMedia(self, paths): return [object()]
    def CreateEmptyTimeline(self, _name): return None
    def AppendToTimeline(self, items):
        payload = items[0]; item = Item("source", payload["recordFrame"], payload["recordFrame"] + payload["endFrame"])
        self.timeline.audio[payload["trackIndex"] - 1].append(item)
        return [item]


class MusicBedTests(unittest.TestCase):
    def test_places_owned_music_and_second_call_is_idempotent(self):
        from bridge.asset_tools import set_music_bed
        from bridge.registry import Registry
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); (root / "dreamy.mp4").write_bytes(b"music")
            timeline = Timeline(); project = SimpleNamespace(GetName=lambda: "ARPHE_PROJECT", GetMediaPool=lambda: Pool(timeline), GetMediaStorage=lambda: None, SetCurrentTimeline=lambda _t: True, GetTimelineCount=lambda: 1, GetTimelineByIndex=lambda _n: timeline, GetSetting=lambda _k: "", SetSetting=lambda _k, _v: True)
            config = SimpleNamespace(flags={**DEFAULT_FLAGS, "CAP_ASSETS": True}, asset_root=root, allowed_timelines=frozenset())
            registry = Registry(root / "state.json"); registry.add_timeline("ARPHE_PROJECT", "ARPHE_TEST")
            first = set_music_bed(project, timeline, config, registry, str(root / "dreamy.mp4"), -24.0, 12, 12)
            second = set_music_bed(project, timeline, config, registry, str(root / "dreamy.mp4"), -24.0, 12, 12)
            self.assertTrue(first["ok"]); self.assertEqual("APPLIED", first["status"])
            self.assertEqual("UNCHANGED", second["status"])
            self.assertEqual(2, timeline.GetTrackCount("audio"))
            self.assertEqual(1, len(timeline.audio[1]))
            self.assertEqual(-24.0, timeline.audio[1][0].props["AudioVolume"])

    def test_replaces_only_previously_owned_clip(self):
        from bridge.asset_tools import set_music_bed
        from bridge.registry import Registry
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); (root / "one.mp4").write_bytes(b"one"); (root / "two.mp4").write_bytes(b"two")
            timeline = Timeline(); project = SimpleNamespace(GetName=lambda: "ARPHE_PROJECT", GetMediaPool=lambda: Pool(timeline), GetMediaStorage=lambda: None, SetCurrentTimeline=lambda _t: True, GetTimelineCount=lambda: 1, GetTimelineByIndex=lambda _n: timeline, GetSetting=lambda _k: "", SetSetting=lambda _k, _v: True)
            config = SimpleNamespace(flags={**DEFAULT_FLAGS, "CAP_ASSETS": True}, asset_root=root, allowed_timelines=frozenset())
            registry = Registry(root / "state.json"); registry.add_timeline("ARPHE_PROJECT", "ARPHE_TEST")
            set_music_bed(project, timeline, config, registry, str(root / "one.mp4"), -24.0, 0, 0)
            manual = Item("manual music", 0, 100); timeline.audio[0].append(manual)
            set_music_bed(project, timeline, config, registry, str(root / "two.mp4"), -23.0, 0, 0)
            self.assertIn(manual, timeline.audio[0])
            self.assertEqual("ARPHE_MUSIC_BED", timeline.audio[1][0].name)

    def test_accepts_music_from_configured_media_root(self):
        from bridge.asset_tools import set_music_bed
        from bridge.registry import Registry
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); assets = root / "assets"; downloads = root / "Downloads"
            assets.mkdir(); downloads.mkdir(); music = downloads / "dreamy.mp4"; music.write_bytes(b"music")
            timeline = Timeline(); project = SimpleNamespace(GetName=lambda: "ARPHE_PROJECT", GetMediaPool=lambda: Pool(timeline), GetMediaStorage=lambda: None, SetCurrentTimeline=lambda _t: True, GetTimelineCount=lambda: 1, GetTimelineByIndex=lambda _n: timeline, GetSetting=lambda _k: "", SetSetting=lambda _k, _v: True)
            config = SimpleNamespace(flags={**DEFAULT_FLAGS, "CAP_ASSETS": True}, asset_root=assets, media_roots=(downloads,), allowed_timelines=frozenset())
            registry = Registry(root / "state.json"); registry.add_timeline("ARPHE_PROJECT", "ARPHE_TEST")
            result = set_music_bed(project, timeline, config, registry, str(music), -24.0, 12, 12)
            self.assertTrue(result["ok"])


