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
                                   validate_plan)  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402


def config(root: Path) -> CreativeConfig:
    media = root / "media"
    transcripts = root / "transcripts"
    media.mkdir()
    transcripts.mkdir()
    return CreativeConfig(
        path=root / "config.json", asset_root=root / "assets", render_root=root / "renders",
        state_path=root / "state.json", audit_log_path=root / "audit.jsonl",
        palette=dict(DEFAULT_PALETTE), flags=dict(DEFAULT_FLAGS), allowed_projects=frozenset(),
        allowed_timelines=frozenset(), render_format="mp4", render_codec="H264",
        media_roots=(media,), transcript_root=transcripts,
    )


class LongformTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
