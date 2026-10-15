from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.audio_cta_tail import move_voiceover_tail_to_cta  # noqa: E402
from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402
from bridge.registry import Registry  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402
from bridge.tool_catalog import EXPOSED_TOOL_NAMES  # noqa: E402


class Media:
    def __init__(self, name: str, fps: str = "30"):
        self.name, self.fps = name, fps

    def GetName(self): return self.name
    def GetClipProperty(self, key): return {"FPS": self.fps}.get(key)


class Item:
    def __init__(self, media: Media, source_start: int, source_end: int, record_start: int):
        self.media, self.source_start, self.source_end, self.record_start = (
            media, source_start, source_end, record_start)

    def GetMediaPoolItem(self): return self.media
    def GetStart(self): return self.record_start
    def GetEnd(self): return self.record_start + self.GetDuration() - 1
    def GetDuration(self): return self.source_end - self.source_start + 1
    def GetSourceStartFrame(self): return self.source_start


class Timeline:
    def __init__(self, name: str, tracks: dict[int, list[Item]]):
        self.name = name
        self.tracks = {index: list(items) for index, items in tracks.items()}

    def GetName(self): return self.name
    def DuplicateTimeline(self, name):
        duplicate = Timeline(name, self.tracks)
        self.project.timelines.append(duplicate)
        self.project.current = duplicate
        return duplicate
    def GetTrackCount(self, kind): return max(self.tracks) if kind == "audio" else 1
    def GetItemListInTrack(self, kind, index):
        return list(self.tracks.get(index, [])) if kind == "audio" else []
    def DeleteClips(self, clips, _ripple):
        for clip in clips:
            for items in self.tracks.values():
                if clip in items:
                    items.remove(clip)
        return True


class Pool:
    def __init__(self, project): self.project = project
    def CreateEmptyTimeline(self, _name): return None
    def AppendToTimeline(self, records):
        record = records[0]
        item = Item(record["mediaPoolItem"], record["startFrame"], record["endFrame"],
                    record["recordFrame"])
        self.project.current.tracks.setdefault(record["trackIndex"], []).append(item)
        return [item]


class Project:
    def __init__(self):
        self.voice = Media("voiceover.wav")
        self.source = Timeline("ARPHE_ADV_V3", {
            4: [Item(self.voice, 300, 1199, 108000)],
        })
        self.source.project = self
        self.timelines = [self.source]
        self.current = self.source
        self.pool = Pool(self)
        self.settings = {"timelineFrameRate": "30"}

    def GetName(self): return "ARPHE_ADV"
    def GetCurrentTimeline(self): return self.current
    def SetCurrentTimeline(self, timeline): self.current = timeline; return True
    def GetTimelineCount(self): return len(self.timelines)
    def GetTimelineByIndex(self, index): return self.timelines[index - 1]
    def GetMediaPool(self): return self.pool
    def GetSetting(self, key): return self.settings.get(key)
    def SetSetting(self, key, value): self.settings[key] = value; return True


def config(root: Path) -> CreativeConfig:
    flags = dict(DEFAULT_FLAGS)
    flags["CAP_TIMELINE"] = True
    return CreativeConfig(
        path=root / "config.json", asset_root=root / "assets", render_root=root / "renders",
        state_path=root / "state.json", audit_log_path=root / "audit.jsonl",
        palette=dict(DEFAULT_PALETTE), flags=flags,
        allowed_projects=frozenset({"ARPHE_ADV"}),
        allowed_timelines=frozenset({"ARPHE_ADV_V3"}), render_format="mp4", render_codec="H264",
    )


class AudioCtaTailTests(unittest.TestCase):
    def test_voiceover_tail_tool_is_exposed_without_generic_audio_editing(self):
        self.assertIn("move_voiceover_tail_to_cta", EXPOSED_TOOL_NAMES)
        self.assertNotIn("move_audio_clip", EXPOSED_TOOL_NAMES)

    def test_replaces_a4_tail_at_cta_start_on_a_duplicate_timeline(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Project()
            cfg = config(Path(directory))
            result = move_voiceover_tail_to_cta(
                project, cfg, Registry(cfg.state_path), "ARPHE_ADV_V3", "ARPHE_ADV_V4_VOICEOVER_CTA",
                audio_track=4, tail_start_frame=108600, cta_start_frame=108866,
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["source_preserved"])
        self.assertEqual("ARPHE_ADV_V3", result["source_timeline"])
        self.assertEqual("ARPHE_ADV_V4_VOICEOVER_CTA", result["created_timeline"])
        self.assertEqual([108000, 108866], result["readback_record_starts"])
        self.assertEqual([108599, 109165], result["readback_record_ends"])
        self.assertEqual([300, 900], result["readback_source_starts"])
        self.assertEqual([899, 1199], result["readback_source_ends"])
        self.assertEqual(1, len(project.source.GetItemListInTrack("audio", 4)))

    def test_refuses_a_tail_boundary_outside_the_only_a4_clip_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Project()
            cfg = config(Path(directory))
            with self.assertRaisesRegex(ValidationError, "coda"):
                move_voiceover_tail_to_cta(
                    project, cfg, Registry(cfg.state_path), "ARPHE_ADV_V3", "ARPHE_ADV_V4_VOICEOVER_CTA",
                    audio_track=4, tail_start_frame=107999, cta_start_frame=108866,
                )

        self.assertEqual(["ARPHE_ADV_V3"], [timeline.GetName() for timeline in project.timelines])


if __name__ == "__main__":
    unittest.main()
