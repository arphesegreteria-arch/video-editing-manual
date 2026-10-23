from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402
from bridge.registry import Registry  # noqa: E402


class Timeline:
    def __init__(self, name: str = "Timeline 1") -> None:
        self.name = name

    def GetName(self): return self.name
    def GetUniqueId(self): return "timeline-advbeppe-1"
    def GetStartFrame(self): return 108000
    def GetEndFrame(self): return 108645
    def GetSetting(self, key): return {"timelineFrameRate": "30"}.get(key)
    def GetTrackCount(self, kind): return 1 if kind in {"video", "audio"} else 0
    def GetItemListInTrack(self, kind, track): return []


class Project:
    def __init__(self) -> None:
        self.timeline = Timeline()
        self.jobs = [{"JobId": "foreign-job", "JobStatus": "Ready"}]
        self.started = []
        self.deleted = []
        self.settings_calls = []
        self.format_calls = []

    def GetName(self): return "advbeppe"
    def GetCurrentTimeline(self): return self.timeline
    def GetTimelineCount(self): return 1
    def GetTimelineByIndex(self, index): return self.timeline if index == 1 else None
    def SetCurrentTimeline(self, timeline): self.timeline = timeline; return True
    def GetCurrentRenderFormatAndCodec(self): return {"format": "mp4", "codec": "H264"}
    def GetRenderSettings(self): return {"TargetDir": "C:/previous", "CustomName": "previous"}
    def SetCurrentRenderFormatAndCodec(self, fmt, codec): self.format_calls.append((fmt, codec)); return True
    def SetRenderSettings(self, settings): self.settings_calls.append(dict(settings)); return True
    def GetRenderJobList(self): return [dict(job) for job in self.jobs]
    def AddRenderJob(self): self.jobs.append({"JobId": "timeline-audio-job", "JobStatus": "Ready"}); return "timeline-audio-job"
    def StartRendering(self, job_ids, interactive=False): self.started.append((job_ids, interactive)); return True
    def DeleteRenderJob(self, job_id): self.deleted.append(job_id); self.jobs = [j for j in self.jobs if j["JobId"] != job_id]; return True
    def IsRenderingInProgress(self): return False
    def GetRenderJobStatus(self, job_id):
        job = next((entry for entry in self.jobs if entry["JobId"] == job_id), None)
        return {"JobStatus": job["JobStatus"]} if job else {}


def setup(root: Path):
    flags = dict(DEFAULT_FLAGS)
    flags["CAP_RENDER"] = True
    cfg = CreativeConfig(
        path=root / "config.json", asset_root=root / "assets", render_root=root / "renders",
        state_path=root / "state.json", audit_log_path=root / "audit.jsonl",
        palette=dict(DEFAULT_PALETTE), flags=flags,
        allowed_projects=frozenset({"advbeppe"}), allowed_timelines=frozenset({"Timeline 1"}),
        render_format="mp4", render_codec="H264", media_roots=(root,),
        transcript_root=root / "transcripts", audio_root=root / "audio",
        audio_jobs_root=root / "audio_jobs", workstation_id="PC_PERSONALE",
    )
    cfg.transcript_root.mkdir(parents=True)
    cfg.audio_root.mkdir(parents=True)
    registry = Registry(cfg.state_path)
    project = Project()
    return cfg, registry, project


class TimelineTranscriptionTests(unittest.TestCase):
    def test_public_catalog_exposes_generic_timeline_transcription_tools(self):
        from bridge.tool_catalog import EXPOSED_TOOL_NAMES
        self.assertIn("start_timeline_audio_transcription", EXPOSED_TOOL_NAMES)
        self.assertIn("get_timeline_audio_transcription_job", EXPOSED_TOOL_NAMES)

    def test_public_wrappers_hold_resolve_lock(self):
        from bridge import server
        events = []

        class Lock:
            def __enter__(self): events.append("enter")
            def __exit__(self, *_args): events.append("exit")

        runtime = (object(), object(), object(), object(), object(), object(), None)
        with patch.object(server, "RESOLVE_ACCESS_LOCK", Lock()), \
             patch.object(server, "_runtime", return_value=runtime), \
             patch.object(server, "do_start_timeline_audio_transcription",
                          side_effect=lambda *_args: events.append("start") or {"ok": True}), \
             patch.object(server, "do_get_timeline_audio_transcription_job",
                          side_effect=lambda *_args: events.append("get") or {"ok": True}):
            self.assertTrue(server.start_timeline_audio_transcription("Timeline 1")["ok"])
            self.assertTrue(server.get_timeline_audio_transcription_job("timeline_tx_0123456789abcdef")["ok"])

        self.assertEqual(["enter", "start", "exit", "enter", "get", "exit"], events)

    def test_start_renders_only_selected_timeline_audio_and_restores_render_context(self):
        from bridge.timeline_transcription import start_timeline_audio_transcription

        with tempfile.TemporaryDirectory() as directory:
            cfg, registry, project = setup(Path(directory))
            result = start_timeline_audio_transcription(
                project, cfg, registry, "Timeline 1", model="small", language="it")

            self.assertTrue(result["ok"])
            self.assertEqual("RENDERING", result["status"])
            self.assertEqual("Timeline 1", result["source_timeline"])
            self.assertEqual(645, result["duration_frames"])
            self.assertEqual([(["timeline-audio-job"], False)], project.started)
            self.assertEqual([], project.deleted)
            self.assertEqual({"foreign-job", "timeline-audio-job"},
                             {job["JobId"] for job in project.jobs})
            render_settings = project.settings_calls[0]
            self.assertFalse(render_settings["ExportVideo"])
            self.assertTrue(render_settings["ExportAudio"])
            self.assertEqual(48000, render_settings["AudioSampleRate"])
            self.assertEqual("LinearPCM", render_settings["AudioCodec"])
            self.assertEqual(("wav", "LinearPCM"), project.format_calls[0])
            self.assertEqual(("mp4", "H264"), project.format_calls[-1])
            self.assertEqual({"TargetDir": "C:/previous", "CustomName": "previous"},
                             project.settings_calls[-1])

    def test_start_refuses_ambiguous_new_render_job_and_preserves_foreign_job(self):
        from bridge.safety import ValidationError
        from bridge.timeline_transcription import start_timeline_audio_transcription

        with tempfile.TemporaryDirectory() as directory:
            cfg, registry, project = setup(Path(directory))
            def ambiguous():
                project.jobs.extend([
                    {"JobId": "new-a", "JobStatus": "Ready"},
                    {"JobId": "new-b", "JobStatus": "Ready"},
                ])
                return "new-a"
            project.AddRenderJob = ambiguous

            with self.assertRaises(ValidationError):
                start_timeline_audio_transcription(project, cfg, registry, "Timeline 1")

            self.assertNotIn("foreign-job", project.deleted)
            self.assertEqual([], project.started)

    def test_start_fails_closed_when_previous_render_settings_cannot_be_read(self):
        from bridge.safety import ValidationError
        from bridge.timeline_transcription import start_timeline_audio_transcription

        with tempfile.TemporaryDirectory() as directory:
            cfg, registry, project = setup(Path(directory))
            project.GetRenderSettings = lambda: None

            with self.assertRaises(ValidationError):
                start_timeline_audio_transcription(project, cfg, registry, "Timeline 1")

            self.assertEqual(["foreign-job"], [job["JobId"] for job in project.jobs])
            self.assertEqual([], project.started)

    def test_poll_verifies_rendered_wav_and_launches_one_bound_transcription(self):
        from bridge.timeline_transcription import (
            get_timeline_audio_transcription_job,
            start_timeline_audio_transcription,
        )

        with tempfile.TemporaryDirectory() as directory:
            cfg, registry, project = setup(Path(directory))
            started = start_timeline_audio_transcription(project, cfg, registry, "Timeline 1")
            manifest_path = next((cfg.transcript_root / ".timeline_jobs" / "PC_PERSONALE").glob("*.json"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            wav_path = Path(manifest["source_path"])
            wav_path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(wav_path), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(48000)
                handle.writeframes(b"\0\0" * 1_032_000)  # 645 / 30 = 21.5 seconds.
            project.jobs[-1]["JobStatus"] = "Complete"

            with patch("bridge.timeline_transcription._launch", return_value=4321) as launch:
                result = get_timeline_audio_transcription_job(
                    project, cfg, registry, started["job_id"])

            self.assertEqual("TRANSCRIBING", result["status"])
            self.assertEqual(["timeline-audio-job"], project.deleted)
            self.assertEqual(["foreign-job"], [job["JobId"] for job in project.jobs])
            launch.assert_called_once_with(manifest_path)
            updated = json.loads(manifest_path.read_text(encoding="utf-8"))
            digest = hashlib.sha256(wav_path.read_bytes()).hexdigest()
            self.assertEqual(digest, updated["source_fingerprint"])
            self.assertEqual(digest, updated["timeline_source"]["audio_fingerprint"])
            self.assertEqual(21.5, updated["timeline_source"]["audio_duration_seconds"])

    def test_poll_rejects_wrong_wav_duration_before_worker_launch(self):
        from bridge.safety import ValidationError
        from bridge.timeline_transcription import (
            get_timeline_audio_transcription_job,
            start_timeline_audio_transcription,
        )

        with tempfile.TemporaryDirectory() as directory:
            cfg, registry, project = setup(Path(directory))
            started = start_timeline_audio_transcription(project, cfg, registry, "Timeline 1")
            manifest_path = next((cfg.transcript_root / ".timeline_jobs" / "PC_PERSONALE").glob("*.json"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            wav_path = Path(manifest["source_path"])
            wav_path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(wav_path), "wb") as handle:
                handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(48000)
                handle.writeframes(b"\0\0" * 48_000)
            project.jobs[-1]["JobStatus"] = "Complete"

            with patch("bridge.timeline_transcription._launch") as launch, self.assertRaises(ValidationError):
                get_timeline_audio_transcription_job(project, cfg, registry, started["job_id"])

            launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
