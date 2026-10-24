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


class OffsetTimeline(Timeline):
    def __init__(self):
        super().__init__()
        self.video = [[Item("video", 108000, 108866)]]
    def GetStartFrame(self): return 108000


class Pool:
    def __init__(self, timeline): self.timeline = timeline
    def ImportMedia(self, paths): return [object()]
    def CreateEmptyTimeline(self, _name): return None
    def AppendToTimeline(self, items):
        payload = items[0]; item = Item("source", payload["recordFrame"], payload["recordFrame"] + payload["endFrame"])
        self.timeline.audio[payload["trackIndex"] - 1].append(item)
        return [item]


class MusicBedTests(unittest.TestCase):
    def test_video_asset_uses_relative_range_on_nonzero_timeline(self):
        from bridge.asset_tools import add_asset
        from bridge.registry import Registry

        class VideoTimeline:
            def __init__(self): self.video, self.audio = [[]], [[]]
            def GetName(self): return "ARPHE_TEST"
            def GetStartFrame(self): return 108000
            def GetTrackCount(self, kind): return 1
            def GetItemListInTrack(self, kind, index):
                return (self.video if kind == "video" else self.audio)[index - 1]

        class VideoPool:
            def __init__(self, timeline): self.timeline, self.payload = timeline, None
            def ImportMedia(self, paths): return [object()]
            def CreateEmptyTimeline(self, name): return None
            def AppendToTimeline(self, entries):
                self.payload = entries[0]
                end = self.payload["recordFrame"] + self.payload["endFrame"] - self.payload.get("startFrame", 0)
                video = Item("source video", self.payload["recordFrame"], end)
                audio = Item("source audio", self.payload["recordFrame"], end)
                self.timeline.video[0].append(video); self.timeline.audio[0].append(audio)
                return [video, audio]

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); media = root / "source.mp4"; media.write_bytes(b"video")
            timeline = VideoTimeline(); pool = VideoPool(timeline)
            project = SimpleNamespace(GetName=lambda: "ARPHE_PROJECT", GetMediaPool=lambda: pool,
                                      GetMediaStorage=lambda: None, GetSetting=lambda _k: "",
                                      SetSetting=lambda _k, _v: True, SetCurrentTimeline=lambda _t: True,
                                      GetTimelineCount=lambda: 1, GetTimelineByIndex=lambda _i: timeline)
            config = SimpleNamespace(flags={**DEFAULT_FLAGS, "CAP_ASSETS": True}, asset_root=root,
                                     media_roots=(), allowed_timelines=frozenset())
            registry = Registry(root / "state.json"); registry.add_timeline("ARPHE_PROJECT", "ARPHE_TEST")

            result = add_asset(project, timeline, config, registry, str(media), "video", 0, 732, 1)

            self.assertTrue(result["ok"])
            self.assertEqual(108000, pool.payload["recordFrame"])
            self.assertEqual(0, pool.payload["startFrame"])
            self.assertEqual(732, pool.payload["endFrame"])
            self.assertNotIn("mediaType", pool.payload)
            self.assertEqual((108000, 108732),
                             (timeline.video[0][0].GetStart(), timeline.video[0][0].GetEnd()))
            self.assertEqual((108000, 108732),
                             (timeline.audio[0][0].GetStart(), timeline.audio[0][0].GetEnd()))

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

    def test_respects_nonzero_timeline_start_frame(self):
        from bridge.asset_tools import set_music_bed
        from bridge.registry import Registry
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); (root / "dreamy.mp4").write_bytes(b"music")
            timeline = OffsetTimeline(); project = SimpleNamespace(GetName=lambda: "ARPHE_PROJECT", GetMediaPool=lambda: Pool(timeline), GetMediaStorage=lambda: None, SetCurrentTimeline=lambda _t: True, GetTimelineCount=lambda: 1, GetTimelineByIndex=lambda _n: timeline, GetSetting=lambda _k: "", SetSetting=lambda _k, _v: True)
            config = SimpleNamespace(flags={**DEFAULT_FLAGS, "CAP_ASSETS": True}, asset_root=root, allowed_timelines=frozenset())
            registry = Registry(root / "state.json"); registry.add_timeline("ARPHE_PROJECT", "ARPHE_TEST")
            result = set_music_bed(project, timeline, config, registry, str(root / "dreamy.mp4"), -24.0, 12, 12)
            item = timeline.audio[1][0]
            self.assertTrue(result["ok"])
            self.assertEqual((108000, 108866), (item.start, item.end))


