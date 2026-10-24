from __future__ import annotations

import importlib
import hashlib
import inspect
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402
from bridge.registry import Registry  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402
from bridge.timeline_dialogue_cleanup import _matching_audio  # noqa: E402


class Media:
    def __init__(self, name: str, unique_id: str, path: str) -> None:
        self.name, self.unique_id, self.path = name, unique_id, path

    def GetName(self): return self.name
    def GetUniqueId(self): return self.unique_id
    def GetClipProperty(self, key=None):
        values = {"File Path": self.path, "FPS": "30"}
        return values if key is None else values.get(key)


class Item:
    def __init__(self, media: Media, start: int = 108000, end: int = 108732,
                 source_start: int = 0) -> None:
        self.media, self.start, self.end, self.source_start = media, start, end, source_start

    def GetMediaPoolItem(self): return self.media
    def GetStart(self): return self.start
    def GetEnd(self): return self.end
    def GetDuration(self): return self.end - self.start
    def GetSourceStartFrame(self): return self.source_start
    def GetSourceEndFrame(self): return self.source_start + self.GetDuration()


class Timeline:
    def __init__(self, name: str, unique_id: str, video_items=None, audio_items=None) -> None:
        self.name, self.unique_id = name, unique_id
        self.video_items = list(video_items or [])
        self.audio_items = list(audio_items or [])
        self.project = None

    def GetName(self): return self.name
    def GetUniqueId(self): return self.unique_id
    def GetStartFrame(self): return 108000
    def GetEndFrame(self): return 108732
    def GetSetting(self, key):
        return {
            "timelineFrameRate": "30",
            "timelinePlaybackFrameRate": "30",
            "timelineResolutionWidth": "1920",
            "timelineResolutionHeight": "1080",
        }.get(key)
    def GetTrackCount(self, kind): return 1 if kind in {"video", "audio"} else 0
    def GetItemListInTrack(self, kind, track):
        if track != 1:
            return []
        return list(self.video_items if kind == "video" else self.audio_items if kind == "audio" else [])
    def DuplicateTimeline(self, name):
        def copy_item(item):
            return Item(item.media, item.start, item.end, item.source_start)
        duplicate = Timeline(
            name, f"timeline-{len(self.project.timelines) + 1}",
            [copy_item(item) for item in self.video_items],
            [copy_item(item) for item in self.audio_items],
        )
        duplicate.project = self.project
        self.project.timelines.append(duplicate)
        self.project.current = duplicate
        return duplicate
    def DeleteClips(self, clips, _ripple):
        for clip in clips:
            if clip in self.video_items:
                self.video_items.remove(clip)
            if clip in self.audio_items:
                self.audio_items.remove(clip)
        return True


class Pool:
    def __init__(self, project) -> None:
        self.project = project
        self.append_return = "item"

    def CreateEmptyTimeline(self, _name): return None
    def ImportMedia(self, paths):
        return [Media(Path(paths[0]).name, "processed-media", str(Path(paths[0]).resolve()))]
    def AppendToTimeline(self, records):
        record = records[0]
        item = Item(
            record["mediaPoolItem"], record["recordFrame"],
            record["recordFrame"] + record["endFrame"] - record["startFrame"] + 1,
            record["startFrame"],
        )
        self.project.current.audio_items.append(item)
        return [] if self.append_return == "empty" else [item]


class Project:
    def __init__(self) -> None:
        video = Media("peeling.mp4", "media-video", "C:/ARPHE/peeling.mp4")
        audio = Media("peeling.wav", "media-audio", "C:/ARPHE/peeling.wav")
        self.source = Timeline("ARPHE_PEELING_STABILIZED", "timeline-source",
                               [Item(video)], [Item(audio)])
        self.other = Timeline("ARPHE_OTHER", "timeline-other")
        self.timelines = [self.source, self.other]
        for timeline in self.timelines:
            timeline.project = self
        self.current = self.other
        self.pool = Pool(self)
        self.jobs = [{"JobId": "foreign-job", "JobStatus": "Ready"}]
        self.started = []
        self.deleted = []
        self.settings_calls = []
        self.saved_presets = []
        self.loaded_presets = []
        self.deleted_presets = []
        self.rendering = False

    def GetName(self): return "ARPHE_PEELING_ADV_TEST"
    def GetCurrentTimeline(self): return self.current
    def GetTimelineCount(self): return len(self.timelines)
    def GetTimelineByIndex(self, index): return self.timelines[index - 1]
    def SetCurrentTimeline(self, timeline): self.current = timeline; return True
    def GetMediaPool(self): return self.pool
    def GetSetting(self, key): return {"timelineFrameRate": "30"}.get(key)
    def SetSetting(self, _key, _value): return True
    def GetCurrentRenderFormatAndCodec(self): return {"format": "mp4", "codec": "H264"}
    def SaveAsNewRenderPreset(self, name): self.saved_presets.append(name); return True
    def LoadRenderPreset(self, name): self.loaded_presets.append(name); return True
    def DeleteRenderPreset(self, name): self.deleted_presets.append(name); return True
    def SetCurrentRenderFormatAndCodec(self, _fmt, _codec): return True
    def SetRenderSettings(self, settings): self.settings_calls.append(dict(settings)); return True
    def GetRenderJobList(self): return [dict(job) for job in self.jobs]
    def AddRenderJob(self):
        self.jobs.append({"JobId": "dialogue-render-job", "JobStatus": "Ready"})
        return "dialogue-render-job"
    def StartRendering(self, job_ids, interactive=False):
        self.started.append((list(job_ids), interactive))
        return True
    def DeleteRenderJob(self, job_id):
        self.deleted.append(job_id)
        self.jobs = [job for job in self.jobs if job["JobId"] != job_id]
        return True
    def IsRenderingInProgress(self): return self.rendering
    def GetRenderJobStatus(self, job_id):
        job = next((value for value in self.jobs if value["JobId"] == job_id), None)
        return {"JobStatus": job["JobStatus"]} if job else {}


def make_config(root: Path) -> CreativeConfig:
    flags = dict(DEFAULT_FLAGS)
    flags.update(CAP_RENDER=True, CAP_TIMELINE=True, CAP_LONGFORM=True)
    cfg = CreativeConfig(
        path=root / "config.json", asset_root=root / "assets", render_root=root / "renders",
        state_path=root / "state.json", audit_log_path=root / "audit.jsonl",
        palette=dict(DEFAULT_PALETTE), flags=flags,
        allowed_projects=frozenset({"ARPHE_PEELING_ADV_TEST"}),
        allowed_timelines=frozenset({"ARPHE_PEELING_STABILIZED"}),
        render_format="mp4", render_codec="H264", media_roots=(root,),
        transcript_root=root / "transcripts", audio_root=root / "audio",
        audio_jobs_root=root / "audio_jobs", workstation_id="PC_PERSONALE",
        artifact_registry_path=root / "artifact_registry.json",
    )
    cfg.transcript_root.mkdir(parents=True)
    cfg.audio_root.mkdir(parents=True)
    cfg.audio_jobs_root.mkdir(parents=True)
    return cfg


def cleanup_module(test_case: unittest.TestCase):
    try:
        return importlib.import_module("bridge.timeline_dialogue_cleanup")
    except ModuleNotFoundError:
        test_case.fail("bridge.timeline_dialogue_cleanup is missing")


class TimelineDialogueCleanupTests(unittest.TestCase):
    def test_audio_matching_uses_stable_media_identity_and_exact_position(self):
        canonical = Media("voice.wav", "same-media", "C:/ARPHE/voice.wav")
        proxy = Media("voice-proxy.wav", "same-media", "C:/ARPHE/voice.wav")
        foreign = Media("foreign.wav", "foreign-media", "C:/ARPHE/foreign.wav")
        timeline = Timeline("test", "timeline-test", audio_items=[
            Item(proxy, 100, 120), Item(foreign, 100, 120), Item(proxy, 120, 140),
        ])
        self.assertEqual([timeline.audio_items[0]], _matching_audio(timeline, canonical, 100, 120))
        with self.assertRaisesRegex(ValidationError, "Identità"):
            _matching_audio(timeline, Media("unknown.wav", "", "C:/ARPHE/unknown.wav"), 100, 120)
    def test_source_end_for_rollback_is_derived_from_verified_duration(self):
        module = cleanup_module(self)
        project = Project()
        audio = project.source.audio_items[0]
        audio.GetSourceEndFrame = lambda: audio.source_start + audio.GetDuration() - 1

        structure = module._single_clip_structure(project.source)

        self.assertEqual(0, structure["audio_source_start"])
        self.assertEqual(732, structure["audio_source_end"])

    def _start(self, root: Path):
        module = cleanup_module(self)
        cfg = make_config(root)
        project = Project()
        result = module.start_timeline_dialogue_cleanup_test(
            project, cfg, Registry(cfg.state_path),
            "ARPHE_PEELING_STABILIZED", "ARPHE_PEELING_AUDIO_NATURAL_V5_TEST",
        )
        manifest_path = (cfg.audio_jobs_root / "timeline-dialogue-cleanup" /
                         cfg.workstation_id / f"{result['job_id']}.json")
        return module, cfg, project, result, manifest_path

    def _advance_to_applying(self, root: Path):
        module, cfg, project, started, manifest_path = self._start(root)
        parent = json.loads(manifest_path.read_text(encoding="utf-8"))
        sample_frames = int(48000 * 732 / 30)
        source_path = Path(parent["source_path"])
        with wave.open(str(source_path), "wb") as handle:
            handle.setnchannels(2)
            handle.setsampwidth(2)
            handle.setframerate(48000)
            handle.writeframes(b"\0\0\0\0" * sample_frames)
        project.jobs[-1]["JobStatus"] = "Complete"
        with patch.object(module, "_launch_audio_worker", return_value=1234):
            module.get_timeline_dialogue_cleanup_job(
                project, cfg, Registry(cfg.state_path), started["job_id"])
        parent = json.loads(manifest_path.read_text(encoding="utf-8"))
        output_path = Path(parent["processed_path"])
        with wave.open(str(output_path), "wb") as handle:
            handle.setnchannels(2)
            handle.setsampwidth(2)
            handle.setframerate(48000)
            handle.writeframes(b"\0\0\0\0" * sample_frames)
        worker_path = Path(parent["audio_worker_manifest"])
        worker = json.loads(worker_path.read_text(encoding="utf-8"))
        worker.update(
            status="COMPLETED", output_sha256=hashlib.sha256(output_path.read_bytes()).hexdigest(),
            sample_rate=48000, channels=2,
        )
        worker_path.write_text(json.dumps(worker), encoding="utf-8")
        applying = module.get_timeline_dialogue_cleanup_job(
            project, cfg, Registry(cfg.state_path), started["job_id"])
        self.assertEqual("APPLYING", applying["status"])
        return module, cfg, project, started, manifest_path

    def test_start_queues_one_owned_audio_render_and_restores_context(self):
        module = cleanup_module(self)
        with tempfile.TemporaryDirectory() as directory:
            cfg = make_config(Path(directory))
            project = Project()
            original = project.current
            result = module.start_timeline_dialogue_cleanup_test(
                project, cfg, Registry(cfg.state_path),
                "ARPHE_PEELING_STABILIZED", "ARPHE_PEELING_AUDIO_NATURAL_V5_TEST",
            )

            self.assertTrue(result["ok"])
            self.assertEqual("RENDERING", result["status"])
            self.assertEqual(732, result["duration_frames"])
            self.assertEqual("ARPHE_PEELING_AUDIO_NATURAL_V5_TEST", result["target_timeline"])
            self.assertIs(original, project.current)
            self.assertEqual([(["dialogue-render-job"], False)], project.started)
            self.assertEqual({"foreign-job", "dialogue-render-job"},
                             {job["JobId"] for job in project.jobs})
            self.assertEqual([], project.deleted)
            self.assertEqual(1, len(project.saved_presets))
            self.assertIn("Audio Only", project.loaded_presets)
            self.assertEqual(project.saved_presets, project.deleted_presets)
            settings = project.settings_calls[0]
            self.assertFalse(settings["ExportVideo"])
            self.assertTrue(settings["ExportAudio"])
            self.assertEqual("lpcm", settings["AudioCodec"])
            self.assertEqual(48000, settings["AudioSampleRate"])
            self.assertEqual(16, settings["AudioBitDepth"])

            manifest_path = (cfg.audio_jobs_root / "timeline-dialogue-cleanup" /
                             cfg.workstation_id / f"{result['job_id']}.json")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            source = manifest["timeline_source"]
            self.assertEqual("PC_PERSONALE", manifest["workstation_id"])
            self.assertEqual("timeline-source", source["timeline_id"])
            self.assertEqual(64, len(source["timeline_edit_fingerprint"]))
            self.assertEqual(108000, source["start_frame"])
            self.assertEqual(108732, source["end_frame"])
            self.assertEqual("dialogue-render-job", manifest["render_job_id"])
            self.assertEqual("ARPHE_DIALOGUE_DEREVERB_NATURAL_V5", manifest["preset"])

    def test_catalog_and_server_publish_only_generic_cleanup_commands(self):
        from bridge.tool_catalog import EXPOSED_TOOL_NAMES
        from bridge import server

        self.assertIn("start_timeline_dialogue_cleanup_test", EXPOSED_TOOL_NAMES)
        self.assertIn("get_timeline_dialogue_cleanup_job", EXPOSED_TOOL_NAMES)
        start_signature = inspect.signature(server.start_timeline_dialogue_cleanup_test)
        poll_signature = inspect.signature(server.get_timeline_dialogue_cleanup_job)
        self.assertEqual(["source_timeline", "target_name", "preset"],
                         list(start_signature.parameters))
        self.assertEqual(["job_id"], list(poll_signature.parameters))
        published = (str(start_signature) + str(poll_signature)
                     + (server.start_timeline_dialogue_cleanup_test.__doc__ or "")
                     + (server.get_timeline_dialogue_cleanup_job.__doc__ or "")).casefold()
        self.assertNotIn("peeling", published)

    def test_server_cleanup_wrappers_hold_resolve_lock(self):
        from bridge import server
        events = []

        class Lock:
            def __enter__(self): events.append("enter")
            def __exit__(self, *_args): events.append("exit")

        runtime = (object(), object(), object(), object(), object(), object(), None)
        with patch.object(server, "RESOLVE_ACCESS_LOCK", Lock()), \
             patch.object(server, "_runtime", return_value=runtime), \
             patch.object(server, "do_start_timeline_dialogue_cleanup_test",
                          side_effect=lambda *_args: events.append("start") or {"ok": True}), \
             patch.object(server, "do_get_timeline_dialogue_cleanup_job",
                          side_effect=lambda *_args: events.append("get") or {"ok": True}):
            self.assertTrue(server.start_timeline_dialogue_cleanup_test(
                "SOURCE", "ARPHE_TARGET")["ok"])
            self.assertTrue(server.get_timeline_dialogue_cleanup_job(
                "dialogue_cleanup_0123456789abcdef")["ok"])

        self.assertEqual(["enter", "start", "exit", "enter", "get", "exit"], events)

    def test_start_rejects_collision_concurrent_render_and_non_single_clip_before_writing(self):
        module = cleanup_module(self)
        cases = ("collision", "rendering", "structure")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                cfg = make_config(Path(directory))
                project = Project()
                if case == "collision":
                    project.timelines.append(Timeline(
                        "ARPHE_PEELING_AUDIO_NATURAL_V5_TEST", "timeline-collision"))
                elif case == "rendering":
                    project.rendering = True
                else:
                    project.source.audio_items.append(project.source.audio_items[0])

                with self.assertRaises(ValidationError):
                    module.start_timeline_dialogue_cleanup_test(
                        project, cfg, Registry(cfg.state_path),
                        "ARPHE_PEELING_STABILIZED", "ARPHE_PEELING_AUDIO_NATURAL_V5_TEST",
                    )

                self.assertEqual([], project.saved_presets)
                self.assertEqual(["foreign-job"], [job["JobId"] for job in project.jobs])

    def test_render_completion_launches_one_bound_audio_worker_and_preserves_foreign_job(self):
        with tempfile.TemporaryDirectory() as directory:
            module, cfg, project, started, manifest_path = self._start(Path(directory))
            self.assertTrue(hasattr(module, "_launch_audio_worker"))
            with patch.object(module, "_launch_audio_worker") as launch:
                pending = module.get_timeline_dialogue_cleanup_job(
                    project, cfg, Registry(cfg.state_path), started["job_id"])
                self.assertEqual("RENDERING", pending["status"])
                launch.assert_not_called()

                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                source_path = Path(manifest["source_path"])
                source_path.parent.mkdir(parents=True, exist_ok=True)
                with wave.open(str(source_path), "wb") as handle:
                    handle.setnchannels(2)
                    handle.setsampwidth(2)
                    handle.setframerate(48000)
                    handle.writeframes(b"\0\0\0\0" * int(48000 * 732 / 30))
                project.jobs[-1]["JobStatus"] = "Complete"
                launch.return_value = 4321

                processing = module.get_timeline_dialogue_cleanup_job(
                    project, cfg, Registry(cfg.state_path), started["job_id"])

            self.assertEqual("PROCESSING", processing["status"])
            launch.assert_called_once()
            self.assertEqual(["dialogue-render-job"], project.deleted)
            self.assertEqual(["foreign-job"], [job["JobId"] for job in project.jobs])
            self.assertEqual(2, len(project.timelines))
            parent = json.loads(manifest_path.read_text(encoding="utf-8"))
            worker_path = Path(parent["audio_worker_manifest"])
            worker = json.loads(worker_path.read_text(encoding="utf-8"))
            self.assertEqual("ARPHE_AUDIO_JOB_V2", worker["schema"])
            self.assertEqual("ARPHE_DIALOGUE_DEREVERB_NATURAL_V5", worker["preset"])
            self.assertEqual(hashlib.sha256(source_path.read_bytes()).hexdigest(),
                             worker["source_fingerprint"])
            self.assertEqual(parent["processed_path"], worker["output_path"])
            self.assertEqual(4321, parent["audio_worker_pid"])

    def test_render_completion_accepts_resolve_24_bit_pcm(self):
        with tempfile.TemporaryDirectory() as directory:
            module, cfg, project, started, manifest_path = self._start(Path(directory))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            source_path = Path(manifest["source_path"])
            with wave.open(str(source_path), "wb") as handle:
                handle.setnchannels(2)
                handle.setsampwidth(3)
                handle.setframerate(48000)
                handle.writeframes(b"\0" * 6 * int(48000 * 732 / 30))
            project.jobs[-1]["JobStatus"] = "Complete"

            with patch.object(module, "_launch_audio_worker", return_value=4321):
                processing = module.get_timeline_dialogue_cleanup_job(
                    project, cfg, Registry(cfg.state_path), started["job_id"])

            self.assertEqual("PROCESSING", processing["status"])

    def test_missing_owned_render_is_persisted_as_interrupted_without_touching_foreign_job(self):
        with tempfile.TemporaryDirectory() as directory:
            module, cfg, project, started, manifest_path = self._start(Path(directory))
            project.jobs = [job for job in project.jobs if job["JobId"] == "foreign-job"]

            with self.assertRaisesRegex(ValidationError, "non più presente"):
                module.get_timeline_dialogue_cleanup_job(
                    project, cfg, Registry(cfg.state_path), started["job_id"])

            parent = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual("INTERRUPTED", parent["status"])
            self.assertEqual(["foreign-job"], [job["JobId"] for job in project.jobs])
            self.assertEqual(2, len(project.timelines))

    def test_invalid_or_foreign_job_id_is_refused(self):
        module = cleanup_module(self)
        with tempfile.TemporaryDirectory() as directory:
            cfg = make_config(Path(directory))
            project = Project()
            for value in ("../escape", "dialogue_cleanup_0123456789abcdeg",
                          "dialogue_cleanup_0123456789abcdef"):
                with self.subTest(value=value), self.assertRaises(ValidationError):
                    module.get_timeline_dialogue_cleanup_job(
                        project, cfg, Registry(cfg.state_path), value)

    def test_tampered_managed_paths_are_rejected_before_render_or_worker_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module, cfg, project, started, manifest_path = self._start(root)
            parent = json.loads(manifest_path.read_text(encoding="utf-8"))
            parent["processed_path"] = str((root / "outside.wav").resolve())
            manifest_path.write_text(json.dumps(parent), encoding="utf-8")

            with self.assertRaisesRegex(ValidationError, "percorsi gestiti"):
                module.get_timeline_dialogue_cleanup_job(
                    project, cfg, Registry(cfg.state_path), started["job_id"])

            self.assertEqual([], project.deleted)
            self.assertEqual({"foreign-job", "dialogue-render-job"},
                             {job["JobId"] for job in project.jobs})

    def test_invalid_processed_pcm_interrupts_before_timeline_write(self):
        with tempfile.TemporaryDirectory() as directory:
            module, cfg, project, started, manifest_path = self._start(Path(directory))
            self.assertTrue(hasattr(module, "_launch_audio_worker"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            source_path = Path(manifest["source_path"])
            with wave.open(str(source_path), "wb") as handle:
                handle.setnchannels(2)
                handle.setsampwidth(2)
                handle.setframerate(48000)
                handle.writeframes(b"\0\0\0\0" * int(48000 * 732 / 30))
            project.jobs[-1]["JobStatus"] = "Complete"
            with patch.object(module, "_launch_audio_worker", return_value=1234):
                module.get_timeline_dialogue_cleanup_job(
                    project, cfg, Registry(cfg.state_path), started["job_id"])

            parent = json.loads(manifest_path.read_text(encoding="utf-8"))
            worker_path = Path(parent["audio_worker_manifest"])
            output_path = Path(parent["processed_path"])
            with wave.open(str(output_path), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(48000)
                handle.writeframes(b"\0\0" * int(48000 * 732 / 30))
            worker = json.loads(worker_path.read_text(encoding="utf-8"))
            worker.update(status="COMPLETED", output_sha256=hashlib.sha256(
                output_path.read_bytes()).hexdigest(), sample_rate=48000, channels=1)
            worker_path.write_text(json.dumps(worker), encoding="utf-8")

            with self.assertRaisesRegex(ValidationError, "stereo"):
                module.get_timeline_dialogue_cleanup_job(
                    project, cfg, Registry(cfg.state_path), started["job_id"])

            interrupted = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual("INTERRUPTED", interrupted["status"])
            self.assertEqual(2, len(project.timelines))

    def test_apply_duplicates_once_replaces_only_a1_and_completed_poll_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            module, cfg, project, started, manifest_path = self._advance_to_applying(Path(directory))
            source_fingerprint = module.timeline_edit_fingerprint(project.source)

            completed = module.get_timeline_dialogue_cleanup_job(
                project, cfg, Registry(cfg.state_path), started["job_id"])

            self.assertEqual("COMPLETED", completed["status"])
            self.assertFalse(completed["saved"])
            self.assertTrue(completed["source_preserved"])
            self.assertEqual(3, len(project.timelines))
            target = project.current
            self.assertEqual("ARPHE_PEELING_AUDIO_NATURAL_V5_TEST", target.GetName())
            self.assertEqual(1, len(target.video_items))
            self.assertEqual(1, len(target.audio_items))
            self.assertEqual((108000, 108732),
                             (target.video_items[0].GetStart(), target.video_items[0].GetEnd()))
            self.assertEqual((108000, 108732),
                             (target.audio_items[0].GetStart(), target.audio_items[0].GetEnd()))
            processed_path = Path(json.loads(
                manifest_path.read_text(encoding="utf-8"))["processed_path"]).resolve()
            self.assertEqual(str(processed_path),
                             target.audio_items[0].media.GetClipProperty("File Path"))
            self.assertEqual(source_fingerprint, module.timeline_edit_fingerprint(project.source))

            replay = module.get_timeline_dialogue_cleanup_job(
                project, cfg, Registry(cfg.state_path), started["job_id"])
            self.assertEqual(completed, replay)
            self.assertEqual(3, len(project.timelines))

    def test_source_edit_drift_refuses_apply_before_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            module, cfg, project, started, _manifest_path = self._advance_to_applying(Path(directory))
            project.source.audio_items[0].end -= 1

            with self.assertRaisesRegex(ValidationError, "cambiata"):
                module.get_timeline_dialogue_cleanup_job(
                    project, cfg, Registry(cfg.state_path), started["job_id"])

            self.assertEqual(2, len(project.timelines))

    def test_source_audio_slip_refuses_apply_before_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            module, cfg, project, started, _manifest_path = self._advance_to_applying(Path(directory))
            project.source.audio_items[0].source_start += 12

            with self.assertRaisesRegex(ValidationError, "cambiata"):
                module.get_timeline_dialogue_cleanup_job(
                    project, cfg, Registry(cfg.state_path), started["job_id"])

            self.assertEqual(2, len(project.timelines))

    def test_processed_audio_tamper_before_apply_blocks_without_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            module, cfg, project, started, manifest_path = self._advance_to_applying(Path(directory))
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            processed_path = Path(payload["processed_path"])
            tampered = bytearray(processed_path.read_bytes())
            tampered[-1] ^= 1
            processed_path.write_bytes(tampered)

            with self.assertRaisesRegex(ValidationError, "Fingerprint WAV dialogo"):
                module.get_timeline_dialogue_cleanup_job(
                    project, cfg, Registry(cfg.state_path), started["job_id"])

            self.assertEqual(2, len(project.timelines))

    def test_append_readback_failure_restores_duplicate_original_a1(self):
        with tempfile.TemporaryDirectory() as directory:
            module, cfg, project, started, manifest_path = self._advance_to_applying(Path(directory))
            project.pool.append_return = "empty"

            with self.assertRaisesRegex(RuntimeError, "Inserimento"):
                module.get_timeline_dialogue_cleanup_job(
                    project, cfg, Registry(cfg.state_path), started["job_id"])

            self.assertEqual(3, len(project.timelines))
            duplicate = project.current
            self.assertEqual(1, len(duplicate.audio_items))
            restored = duplicate.audio_items[0]
            self.assertEqual("media-audio", restored.media.GetUniqueId())
            self.assertEqual((108000, 108732), (restored.GetStart(), restored.GetEnd()))
            self.assertEqual("INTERRUPTED", json.loads(
                manifest_path.read_text(encoding="utf-8"))["status"])


if __name__ == "__main__":
    unittest.main()
