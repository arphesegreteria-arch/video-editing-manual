from __future__ import annotations
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class Timeline:
    def GetName(self): return "Original_EDITORIAL"


class Project:
    def __init__(self, current): self.current = current
    def GetCurrentTimeline(self): return self.current
    def SetCurrentTimeline(self, timeline): self.current = timeline; return True


class DeletingTimeline(Timeline):
    def __init__(self): self.deleted = []
    def DeleteClips(self, clips, ripple):
        self.deleted.append((clips, ripple))
        return True


class CarrierItem:
    def AddFusionComp(self): return None
    def GetFusionCompByIndex(self, index): return None
    def GetFusionCompCount(self): return 0
    def GetName(self): return "carrier"


class MediaPool:
    def __init__(self, item): self.item = item
    def ImportMedia(self, paths): return [object()]
    def AppendToTimeline(self, records): return [self.item]


class CompositionProject:
    def __init__(self, pool): self.pool = pool
    def GetMediaPool(self): return self.pool


class CompositionTimeline(DeletingTimeline):
    def __init__(self): super().__init__(); self.deleted_tracks = []
    def AddTrack(self, kind): return True
    def GetTrackCount(self, kind): return 2
    def CreateFusionClip(self, items): return None
    def DeleteTrack(self, kind, index): self.deleted_tracks.append((kind, index)); return True


class EmptyAppendPool(MediaPool):
    def AppendToTimeline(self, records): return []


class TrackRollbackTimeline(CompositionTimeline):
    pass


class BrandedLongformGraphicsTests(unittest.TestCase):
    def test_arphe_proposal_is_mapped_to_verified_graphic(self):
        from bridge.branded_longform_graphics import apply_editorial_graphic
        job = SimpleNamespace(editorial_timeline="Original_EDITORIAL", profile_id="ARPHE_LONGFORM_EDITORIAL")
        proposal = {"proposal_id": "P001", "kind": "PROGRESSIVE_LIST", "start_frame": 30,
                    "end_frame": 90, "rationale": "Tre elementi", "executable": True,
                    "operator_modification": "Uno\nDue\nTre"}
        cfg = SimpleNamespace(palette={"cream": "#EFE3CF"})
        original = object(); timeline = Timeline(); project = Project(original)
        def create(*args):
            self.assertIs(timeline, project.current)
            return object(), object()
        with patch("bridge.branded_longform_graphics.create_longform_overlay_composition",
                   side_effect=create), \
             patch("bridge.branded_longform_graphics.build_graphic_graph",
                   return_value={"text_readback": True, "font": "Satoshi"}) as build:
            result = apply_editorial_graphic(project, timeline, cfg, job, proposal)
        self.assertTrue(result["ok"])
        self.assertEqual("P001", result["proposal_id"])
        self.assertIn("Uno", build.call_args.args[1]["text"])
        self.assertIs(original, project.current)

    def test_pending_kit_never_executes_graphic(self):
        from bridge.branded_longform_graphics import apply_editorial_graphic
        job = SimpleNamespace(editorial_timeline="Original_EDITORIAL", profile_id="CARABELLESE_LONGFORM_EDITORIAL")
        with self.assertRaisesRegex(Exception, "pending"):
            apply_editorial_graphic(object(), Timeline(), SimpleNamespace(), job,
                                    {"proposal_id": "P", "executable": False})

    def test_failed_graph_build_deletes_partial_overlay_and_restores_timeline(self):
        from bridge.branded_longform_graphics import apply_editorial_graphic
        job = SimpleNamespace(editorial_timeline="Original_EDITORIAL", profile_id="ARPHE_LONGFORM_EDITORIAL")
        proposal = {"proposal_id": "P001", "kind": "TITLE", "start_frame": 30,
                    "end_frame": 90, "copy": "Titolo", "executable": True}
        cfg = SimpleNamespace(palette={"cream": "#EFE3CF"})
        original = object(); timeline = DeletingTimeline(); project = Project(original)
        partial_item = object()
        with patch("bridge.branded_longform_graphics.create_longform_overlay_composition",
                   return_value=(partial_item, object())), \
             patch("bridge.branded_longform_graphics.build_graphic_graph",
                   side_effect=RuntimeError("fusion failed")):
            with self.assertRaisesRegex(RuntimeError, "fusion failed"):
                apply_editorial_graphic(project, timeline, cfg, job, proposal)
        self.assertEqual([([partial_item], False)], timeline.deleted)
        self.assertIs(original, project.current)

    def test_failed_composition_creation_deletes_inserted_carrier(self):
        from bridge.branded_longform_graphics import create_longform_overlay_composition
        with tempfile.TemporaryDirectory() as raw:
            from bridge.fusion_tools import CARRIER_ASSET_NAME
            carrier_path = Path(raw) / CARRIER_ASSET_NAME
            carrier_path.write_bytes(b"carrier")
            item = CarrierItem(); timeline = CompositionTimeline()
            project = CompositionProject(MediaPool(item))
            cfg = SimpleNamespace(asset_root=Path(raw))
            with self.assertRaisesRegex(Exception, "Composizione Fusion"):
                create_longform_overlay_composition(
                    project, timeline, cfg, "Original_EDITORIAL", 0, 30, "test")
            self.assertEqual([([item], False)], timeline.deleted)
            self.assertEqual([("video", 2)], timeline.deleted_tracks)

    def test_failed_carrier_append_removes_new_overlay_track(self):
        from bridge.branded_longform_graphics import create_longform_overlay_composition
        with tempfile.TemporaryDirectory() as raw:
            from bridge.fusion_tools import CARRIER_ASSET_NAME
            (Path(raw) / CARRIER_ASSET_NAME).write_bytes(b"carrier")
            timeline = TrackRollbackTimeline()
            project = CompositionProject(EmptyAppendPool(CarrierItem()))
            with self.assertRaisesRegex(Exception, "Inserimento carrier"):
                create_longform_overlay_composition(
                    project, timeline, SimpleNamespace(asset_root=Path(raw)),
                    "Original_EDITORIAL", 0, 30, "test")
            self.assertEqual([("video", 2)], timeline.deleted_tracks)
