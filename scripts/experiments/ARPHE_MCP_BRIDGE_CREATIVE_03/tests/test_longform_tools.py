from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402
from bridge.longform_tools import (allowed_media, transcript_chunk, transcript_metadata,
                                   apply_plan, validate_plan)  # noqa: E402
from bridge.registry import Registry  # noqa: E402
from bridge.feature_flags import availability  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402
from bridge.server import mcp  # noqa: E402


def config(root: Path) -> CreativeConfig:
    media = root / "media"
    transcripts = root / "transcripts"
    audio = root / "audio"
    audio_jobs = root / "audio_jobs"
    media.mkdir()
    transcripts.mkdir()
    audio.mkdir()
    audio_jobs.mkdir()
    return CreativeConfig(
        path=root / "config.json", asset_root=root / "assets", render_root=root / "renders",
        state_path=root / "state.json", audit_log_path=root / "audit.jsonl",
        palette=dict(DEFAULT_PALETTE), flags=dict(DEFAULT_FLAGS), allowed_projects=frozenset(),
        allowed_timelines=frozenset(), render_format="mp4", render_codec="H264",
        media_roots=(media,), transcript_root=transcripts, audio_root=audio,
        audio_jobs_root=audio_jobs,
    )


class LongformTests(unittest.TestCase):
    def test_apply_selects_master_and_each_clip_before_append(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = config(root)
            cfg.flags["CAP_LONGFORM"] = True
            media = cfg.media_roots[0] / "source.mp4"
            audio = cfg.audio_root / "clean.wav"
            media.write_bytes(b"video")
            audio.write_bytes(b"audio")

            class Timeline:
                def __init__(self, name): self.name, self.entries = name, []
                def GetName(self): return self.name
                def GetStartFrame(self): return 108000

            class Pool:
                def __init__(self, project): self.project = project
                def CreateEmptyTimeline(self, name):
                    item = Timeline(name)
                    self.project.timelines.append(item)
                    self.project.current = item
                    return item
                def ImportMedia(self, _paths): return [object()]
                def AppendToTimeline(self, entries):
                    self.project.current.entries.extend(entries)
                    return entries

            class Project:
                def __init__(self):
                    self.timelines, self.current = [], None
                    self.pool = Pool(self)
                def GetMediaPool(self): return self.pool
                def GetCurrentTimeline(self): return self.current
                def SetCurrentTimeline(self, timeline): self.current = timeline; return True
                def SetSetting(self, *_): return True
                def GetSetting(self, *_): return "30"
                def GetTimelineCount(self): return len(self.timelines)
                def GetTimelineByIndex(self, index): return self.timelines[index - 1]

            initial, created = Project(), Project()
            class Manager:
                def GetCurrentProject(self): return initial
                def CreateProject(self, _name): return created
                def LoadProject(self, *_): return True
                def SaveProject(self, *_): return True
                def GetProjectListInCurrentFolder(self): return []
            class Storage:
                def AddItemListToMediaPool(self, _path): return [object()]
            class Resolve:
                def GetMediaStorage(self): return Storage()

            result = apply_plan(Resolve(), Manager(), cfg, Registry(cfg.state_path), str(media),
                                "ARPHE_TEST_PROJECT", "ARPHE_TEST_MASTER", [
                                    {"clip_id": "ARPHE_CLIP_01", "start_second": 1, "end_second": 2},
                                    {"clip_id": "ARPHE_CLIP_02", "start_second": 3, "end_second": 4},
                                ], 30, str(audio))
            self.assertTrue(result["ok"])
            by_name = {item.name: item for item in created.timelines}
            self.assertEqual(4, len(by_name["ARPHE_TEST_MASTER"].entries))
            self.assertEqual(2, len(by_name["ARPHE_CLIP_01"].entries))
            self.assertEqual(2, len(by_name["ARPHE_CLIP_02"].entries))

    def test_longform_is_technically_available_from_current_project(self):
        class Api:
            def __getattr__(self, _name):
                return lambda *args: None

        manager = Api()
        project = Api()
        pool = Api()
        project.GetMediaPool = lambda: pool
        state = availability(manager, project, Api())
        self.assertTrue(state["CAP_LONGFORM"])

    def test_plan_converts_seconds_to_exclusive_frames(self):
        result = validate_plan([{"clip_id": "CLIP_01", "title": "Test",
                                 "start_second": 10.0, "end_second": 12.5}], 30)
        self.assertEqual(300, result[0]["source_in_frame"])
        self.assertEqual(375, result[0]["source_out_frame_exclusive"])
        self.assertEqual(75, result[0]["duration_frames"])

    def test_plan_rejects_over_three_minutes_and_duplicate_ids(self):
        with self.assertRaises(ValidationError):
            validate_plan([{"start_second": 0, "end_second": 180.001}], 30)
        with self.assertRaisesRegex(ValidationError, "duplicato"):
            validate_plan([{"clip_id": "SAME", "start_second": 0, "end_second": 1},
                           {"clip_id": "SAME", "start_second": 2, "end_second": 3}], 30)

    def test_media_and_transcript_are_path_allowlisted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = config(root)
            video = cfg.media_roots[0] / "source.mp4"
            video.write_bytes(b"video")
            self.assertEqual(video.resolve(), allowed_media(str(video), cfg))
            outside = root / "outside.mp4"
            outside.write_bytes(b"video")
            with self.assertRaises(ValidationError):
                allowed_media(str(outside), cfg)

            transcript = cfg.transcript_root / "source.transcript.json"
            transcript.write_text(json.dumps({
                "schema": "ARPHE_TRANSCRIPT_V1", "status": "complete",
                "source": {"name": "source.mp4", "duration_seconds": 10},
                "transcription": {"model": "small"}, "summary": {"segment_count": 1},
                "segments": [{"start": 1.0, "end": 2.0, "text": "test", "words": []}],
            }), encoding="utf-8")
            self.assertTrue(transcript_metadata(str(transcript), cfg)["ok"])
            self.assertEqual(1, len(transcript_chunk(str(transcript), cfg, 0, 3)["segments"]))


class LongformMcpTests(unittest.IsolatedAsyncioTestCase):
    async def test_validation_returns_compact_summary_not_expanded_plan(self):
        result = await mcp.call_tool("validate_longform_edit_plan", {"clips": [
            {"clip_id": "ARPHE_TEST_01", "start_second": 10, "end_second": 12},
        ], "fps": 30})
        payload = result.structured_content
        self.assertTrue(payload["ok"])
        self.assertNotIn("clips", payload)
        self.assertEqual(1, payload["clip_count"])
        self.assertEqual(60, payload["total_frames"])
        self.assertEqual(64, len(payload["plan_sha256"]))


if __name__ == "__main__":
    unittest.main()
