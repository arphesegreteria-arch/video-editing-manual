from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class Item:
    def __init__(self, start, end, comp): self.start, self.end, self.comp, self.name = start, end, comp, "carrier"
    def GetStart(self): return self.start
    def GetEnd(self): return self.end
    def GetDuration(self): return self.end - self.start
    def SetName(self, name): self.name = name; return True
    def AddFusionComp(self): return self.comp
    def GetFusionCompByIndex(self, index): return self.comp


class Pool:
    def __init__(self, timeline, comp): self.timeline, self.comp, self.entry = timeline, comp, None
    def ImportMedia(self, paths): return [object()]
    def AppendToTimeline(self, entries):
        self.entry = entries[0]
        item = Item(self.entry["recordFrame"], self.entry["recordFrame"] + self.entry["endFrame"], self.comp)
        self.timeline.items.append(item)
        return [item]


class Timeline:
    def __init__(self): self.tracks, self.items = 1, []
    def GetName(self): return "__ARPHE_VERTICAL_VERTICAL_12345678"
    def AddTrack(self, kind): self.tracks += 1; return True
    def GetTrackCount(self, kind): return self.tracks
    def CreateFusionClip(self, items): return items[0]


class Project:
    def __init__(self, pool): self.pool = pool
    def GetMediaPool(self): return self.pool


class VerticalSocialOverlayTests(unittest.TestCase):
    def test_overlay_carrier_uses_dedicated_track_exact_range(self):
        from bridge.vertical_social_overlay import create_overlay_composition
        timeline = Timeline(); comp = object(); pool = Pool(timeline, comp); project = Project(pool)
        with tempfile.TemporaryDirectory() as raw:
            carrier = Path(raw) / "arphe_fusion_carrier_5m.mp4"; carrier.write_bytes(b"x")
            cfg = SimpleNamespace(asset_root=Path(raw))
            item, returned = create_overlay_composition(project, timeline, cfg, 30, 90, "GRAPHIC_G1")
        self.assertIs(comp, returned)
        self.assertEqual(2, pool.entry["trackIndex"])
        self.assertEqual(30, pool.entry["recordFrame"])
        self.assertEqual(60, item.GetDuration())

    def test_graphic_and_cta_executor_builds_then_reads_back(self):
        from bridge.vertical_social_overlay import apply_graphic_or_cta
        timeline = Timeline(); item = Item(0, 30, object())
        cfg = SimpleNamespace(palette={"cream": "#EFE3CF", "burgundy": "#6C2438",
                                      "white": "#FFFFFF", "black": "#000000"})
        action = {"action_id": "g1", "type": "GRAPHIC", "state": "APPROVED",
                  "graphic_kind": "TITLE", "text": "Titolo", "style_role": "cream",
                  "range": {"start_frame": 0, "end_frame": 30}, "reason": "richiesta"}
        with patch("bridge.vertical_social_overlay.create_overlay_composition", return_value=(item, object())), \
             patch("bridge.vertical_social_overlay.build_graphic_graph", return_value={"text_readback": True}) as build:
            result = apply_graphic_or_cta(object(), timeline, cfg, action, 60)
        self.assertEqual("g1", result["action_id"])
        build.assert_called_once()
