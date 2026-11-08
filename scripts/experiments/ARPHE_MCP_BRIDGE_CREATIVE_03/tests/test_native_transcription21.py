from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from bridge.native_transcription21 import (
    read_native_transcription21,
    start_native_transcription21,
)
from bridge.safety import ValidationError


EMPTY_TRANSCRIPT = {"language": "it", "segments": []}
FRESH_TRANSCRIPT = {"language": "it", "segments": [
    {"start": "01:00:00:00", "end": "01:00:01:00", "text": "Prima",
     "speaker": "Speaker 1", "words": []},
    {"start": "01:00:01:00", "end": "01:00:02:00", "text": "Seconda",
     "speaker": None, "words": []},
]}


class Media:
    def __init__(self, transcription=None, name="source.mov"):
        self.calls = 0
        self.transcription = EMPTY_TRANSCRIPT if transcription is None else transcription
        self.name = name

    def GetUniqueId(self): return "media-123"
    def GetName(self): return self.name
    def GetClipProperty(self, name): return {"File Path": "C:/media/source.mov"}.get(name)
    def TranscribeAudio(self, speakers=True):
        self.calls += 1
        return True
    def GetTranscription(self): return self.transcription


class Clip:
    def __init__(self, media): self.media = media
    def GetMediaPoolItem(self): return self.media


class Timeline:
    def __init__(self, media): self.media = media
    def GetName(self): return "ARPHE_TIMELINE"
    def GetTrackCount(self, _): return 1
    def GetItemListInTrack(self, kind, _): return [Clip(self.media)] if kind == "video" else []


class Project:
    def GetName(self): return "ARPHE_PROJECT"


class Registry:
    def timeline_allowed(self, *_): return True


class NativeTranscription21Tests(unittest.TestCase):
    def config(self, root: Path):
        return type("Config", (), {
            "state_path": root / "registry.json",
            "workstation_id": "PC_PERSONALE",
            "allowed_projects": (),
            "allowed_timelines": (),
        })()

    def manifest(self, root: Path, job_id: str) -> Path:
        return root / "resolve21-native-transcription" / "PC_PERSONALE" / f"{job_id}.json"

    def test_start_is_persistent_and_idempotent(self):
        with tempfile.TemporaryDirectory() as raw:
            media = Media()
            cfg = self.config(Path(raw))
            first = start_native_transcription21(Project(), Timeline(media), cfg, Registry(),
                                                 "media-123", True)
            second = start_native_transcription21(Project(), Timeline(media), cfg, Registry(),
                                                  "media-123", True)
            self.assertEqual(first["job_id"], second["job_id"])
            self.assertEqual(1, media.calls)
            self.assertEqual("TRANSCRIBING", first["status"])

    def test_job_identity_includes_speaker_mode_and_source_fingerprint(self):
        with tempfile.TemporaryDirectory() as raw:
            media = Media()
            cfg = self.config(Path(raw))
            with_speakers = start_native_transcription21(
                Project(), Timeline(media), cfg, Registry(), "media-123", True)
            without_speakers = start_native_transcription21(
                Project(), Timeline(media), cfg, Registry(), "media-123", False)
            media.name = "replacement.mov"
            replacement = start_native_transcription21(
                Project(), Timeline(media), cfg, Registry(), "media-123", True)
            self.assertEqual(3, len({with_speakers["job_id"], without_speakers["job_id"],
                                     replacement["job_id"]}))

    def test_unchanged_preexisting_transcript_is_not_false_completion(self):
        with tempfile.TemporaryDirectory() as raw:
            media = Media(FRESH_TRANSCRIPT)
            cfg = self.config(Path(raw))
            job = start_native_transcription21(Project(), Timeline(media), cfg, Registry(),
                                               "media-123", False)
            result = read_native_transcription21(Project(), Timeline(media), cfg, Registry(),
                                                 job["job_id"], 0, 50)
            self.assertEqual("TRANSCRIBING", result["status"])
            self.assertEqual([], result["segments"])

    def test_read_returns_fresh_bounded_timecoded_segments_without_writing_manifest(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            media = Media()
            cfg = self.config(root)
            job = start_native_transcription21(Project(), Timeline(media), cfg, Registry(),
                                               "media-123", True)
            manifest = self.manifest(root, job["job_id"])
            before = manifest.read_bytes()
            media.transcription = FRESH_TRANSCRIPT
            result = read_native_transcription21(Project(), Timeline(media), cfg, Registry(),
                                                 job["job_id"], 1, 1)
            self.assertEqual("COMPLETED", result["status"])
            self.assertEqual(2, result["segment_count"])
            self.assertEqual(["Seconda"], [item["text"] for item in result["segments"]])
            self.assertEqual(before, manifest.read_bytes())

    def test_unchanged_empty_result_times_out_without_manifest_write(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            media = Media()
            cfg = self.config(root)
            job = start_native_transcription21(Project(), Timeline(media), cfg, Registry(),
                                               "media-123", False)
            manifest = self.manifest(root, job["job_id"])
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["created_at"] = "2000-01-01T00:00:00Z"
            manifest.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            before = manifest.read_bytes()
            result = read_native_transcription21(Project(), Timeline(media), cfg, Registry(),
                                                 job["job_id"], 0, 50)
            self.assertEqual("TIMED_OUT", result["status"])
            self.assertEqual(before, manifest.read_bytes())

    def test_read_rejects_malformed_transcription(self):
        with tempfile.TemporaryDirectory() as raw:
            media = Media()
            cfg = self.config(Path(raw))
            job = start_native_transcription21(Project(), Timeline(media), cfg, Registry(),
                                               "media-123", True)
            media.transcription = {"language": "it", "segments": [{"text": "senza timecode"}]}
            with self.assertRaises(ValidationError):
                read_native_transcription21(Project(), Timeline(media), cfg, Registry(),
                                            job["job_id"], 0, 50)


if __name__ == "__main__":
    unittest.main()
