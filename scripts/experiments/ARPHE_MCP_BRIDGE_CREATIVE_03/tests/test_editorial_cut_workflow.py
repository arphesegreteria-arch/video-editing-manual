from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.audio_provenance import file_sha256, media_fingerprint  # noqa: E402
from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402
from bridge.editorial_cut_workflow import (  # noqa: E402
    _set_and_verify_format,
    apply_or_resume_editorial_cuts,
    verify_editorial_outputs,
)
from bridge.editorial_jobs import EditorialJobStore, new_editorial_job  # noqa: E402
from bridge.editorial_selection_contract import load_selection_contract  # noqa: E402
from bridge.safety import PlaybackFpsActionRequired, ValidationError  # noqa: E402


CONTRACT = load_selection_contract(ROOT / "editorial_selection_contract.json")


class FakeMediaItem:
    def __init__(self, name: str, frames: int, path: Path | None = None, fps: str = "24"):
        self.name, self.frames, self.path, self.fps = name, frames, path, fps

    def GetName(self): return self.name
    def GetClipProperty(self, key):
        return {"Frames": str(self.frames), "File Path": "" if self.path is None else str(self.path),
                "FPS": self.fps}.get(key)


class FakeTimelineItem:
    def __init__(self, media_item, source_start, source_end, record_start, timeline_fps="24"):
        self.media_item = media_item
        self.source_start = source_start
        self.source_end = source_end
        self.record_start = record_start
        self.timeline_fps = Fraction(str(timeline_fps))

    def _scaled(self, frames):
        return int(Fraction(frames, 1) * self.timeline_fps / Fraction(str(self.media_item.fps)))

    def GetMediaPoolItem(self): return self.media_item
    def GetStart(self): return self.record_start
    def GetEnd(self): return self.record_start + self._scaled(self.source_end - self.source_start + 1) - 1
    def GetLeftOffset(self): return self._scaled(self.source_start)
    def GetRightOffset(self): return self._scaled(self.media_item.frames - self.source_end - 1)


class FakeTimeline:
    def __init__(self, name: str, unique_id: str, settings: dict[str, str]):
        self.name, self.unique_id, self.settings = name, unique_id, dict(settings)
        self.video: list[FakeTimelineItem] = []
        self.audio: list[FakeTimelineItem] = []

    def GetName(self): return self.name
    def GetUniqueId(self): return self.unique_id
    def GetSetting(self, key): return self.settings.get(key)
    def SetSetting(self, key, value): self.settings[key] = str(value); return True
    def GetStartFrame(self): return 0
    def GetEndFrame(self):
        items = self.video + self.audio
        return max((item.GetEnd() for item in items), default=0)
    def GetTrackCount(self, kind): return 1 if (self.video if kind == "video" else self.audio) else 0
    def GetItemListInTrack(self, kind, track):
        if track != 1: return []
        return list(self.video if kind == "video" else self.audio)


class FakeFolder:
    def __init__(self, clips): self.clips = clips
    def GetClipList(self): return list(self.clips)
    def GetSubFolderList(self): return []


class FakePool:
    def __init__(self, project, clips):
        self.project, self.root = project, FakeFolder(clips)
        self.fail_name: str | None = None

    def GetRootFolder(self): return self.root
    def CreateEmptyTimeline(self, name):
        self.project.calls.append(("CreateEmptyTimeline", name))
        if name == self.fail_name: return None
        timeline = FakeTimeline(name, f"uid:{name}", dict(self.project.settings))
        self.project.timelines.append(timeline)
        return timeline
    def AppendToTimeline(self, records):
        record = records[0]
        item = record["mediaPoolItem"]
        self.project.calls.append(("AppendToTimeline", self.project.current.name, item.name,
                                   record["startFrame"], record["endFrame"],
                                   record.get("mediaType")))
        target = FakeTimelineItem(item, record["startFrame"], record["endFrame"], record["recordFrame"],
                                  self.project.current.settings["timelineFrameRate"])
        media_type = record.get("mediaType")
        if media_type in (None, 1): self.project.current.video.append(target)
        if media_type in (None, 2): self.project.current.audio.append(target)
        return True
    def ImportMedia(self, paths):
        path = Path(paths[0])
        item = FakeMediaItem(path.name, 2400, path)
        self.root.clips.append(item)
        return [item]


class FakeProject:
    def __init__(self, source_item, cta_item):
        self.settings = {"timelineResolutionWidth": "1920", "timelineResolutionHeight": "1080",
                         "timelineFrameRate": "30", "timelinePlaybackFrameRate": "30"}
        self.calls: list[tuple] = []
        self.source = FakeTimeline("ARPHE_SOURCE", "source-uid", self.settings)
        source_clip = FakeTimelineItem(source_item, 0, source_item.frames - 1, 0)
        self.source.video.append(source_clip); self.source.audio.append(source_clip)
        self.timelines = [self.source]
        self.current = self.source
        self.pool = FakePool(self, [source_item, cta_item])

    def GetName(self): return "ARPHE_TEST_PROJECT"
    def GetCurrentTimeline(self): return self.current
    def SetCurrentTimeline(self, timeline): self.calls.append(("SetCurrentTimeline", timeline.name)); self.current = timeline; return True
    def GetTimelineCount(self): return len(self.timelines)
    def GetTimelineByIndex(self, index): return self.timelines[index - 1]
    def GetMediaPool(self): return self.pool
    def GetSetting(self, key): return self.settings.get(key)


class FakeManager:
    def __init__(self, project): self.project = project
    def GetCurrentProject(self): return self.project


class FakeResolve:
    pass


def config(root: Path) -> CreativeConfig:
    for name in ("media", "audio", "jobs"):
        (root / name).mkdir()
    return CreativeConfig(
        path=root / "config.json", asset_root=root / "assets", render_root=root / "renders",
        state_path=root / "state.json", audit_log_path=root / "audit.jsonl",
        palette=dict(DEFAULT_PALETTE), flags=dict(DEFAULT_FLAGS),
        allowed_projects=frozenset(), allowed_timelines=frozenset(),
        render_format="mp4", render_codec="H264", media_roots=(root / "media",),
        audio_root=root / "audio", audio_jobs_root=root / "jobs", workstation_id="PC_PERSONALE",
        editorial_jobs_path=root / "editorial_jobs.json",
    )


def candidate(index, start, end):
    return {"candidate_id": f"R{index:02d}", "source_start_seconds": start,
            "source_end_seconds": end, "source_in_frame": int(start * 24),
            "source_out_frame_exclusive": int(end * 24), "thesis": f"Tesi {index}",
            "indispensable_context": f"Contesto {index}", "final_duration_seconds": end-start+5}


def reviewed_job(store, source_fingerprint, candidates=None, decisions=None):
    candidates = tuple(candidates or (candidate(1, 10, 14), candidate(2, 20, 26), candidate(3, 30, 34)))
    decisions = tuple(decisions or (
        {"candidate_id": "R01", "outcome": "APPROVE", "source_start_seconds": 10.0,
         "source_end_seconds": 14.0, "final_duration_seconds": 9.0, "reason": "forte"},
        {"candidate_id": "R02", "outcome": "MODIFY", "source_start_seconds": 21.0,
         "source_end_seconds": 25.0, "final_duration_seconds": 9.0, "reason": "più diretto"},
        {"candidate_id": "R03", "outcome": "REJECT", "source_start_seconds": 30.0,
         "source_end_seconds": 34.0, "final_duration_seconds": 9.0, "reason": "ripete"},
    ))
    created = store.create(new_editorial_job(
        workstation_id="PC_PERSONALE", workflow_version=1,
        project_name="ARPHE_TEST_PROJECT", timeline_name="ARPHE_SOURCE",
        timeline_identity="resolve:source-uid", source_fingerprint=source_fingerprint,
        transcript_fingerprint="b" * 64, candidate_fingerprint="c" * 64,
        candidates=candidates,
    ))
    marked = store.save(replace(created, state="MARKED", markers=({"name": "m", "frame": 1},)),
                        created.revision)
    return store.save(replace(marked, state="REVIEWED", decisions=decisions,
                              review_fingerprint="d" * 64), marked.revision)


def environment(root: Path):
    cfg = config(root)
    source_path = cfg.media_roots[0] / "podcast.mov"
    source_path.write_bytes(b"podcast-source")
    source_item = FakeMediaItem("podcast.mov", 24 * 3600, source_path)
    cta_item = FakeMediaItem(CONTRACT.cta_media_pool_name, 120)
    project = FakeProject(source_item, cta_item)
    store = EditorialJobStore(cfg.editorial_jobs_path, cfg.workstation_id)
    job = reviewed_job(store, media_fingerprint(source_path))
    return cfg, project, store, job


class EditorialCutWorkflowTests(unittest.TestCase):
    def test_cut_blocks_24_fps_before_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg, project, store, job = environment(Path(directory))
            project.settings["timelineFrameRate"] = "24"
            project.settings["timelinePlaybackFrameRate"] = "24"
            project.source.settings.update(project.settings)

            with self.assertRaises(PlaybackFpsActionRequired):
                apply_or_resume_editorial_cuts(
                    FakeResolve(), FakeManager(project), cfg, store,
                    job.editorial_job_id, "d" * 64,
                )

        self.assertFalse(any(call[0] == "CreateEmptyTimeline" for call in project.calls))

    def test_format_setup_trusts_readback_when_resolve_returns_false(self):
        timeline = FakeTimeline("OUTPUT", "output-uid", {
            "timelineResolutionWidth": "1920", "timelineResolutionHeight": "1080",
            "timelineFrameRate": "24", "timelinePlaybackFrameRate": "24",
        })

        def false_but_unchanged(key, value):
            return False

        timeline.SetSetting = false_but_unchanged
        _set_and_verify_format(timeline, {
            "width": 1920, "height": 1080, "fps": "24", "playback_fps": "24",
        })

    def test_format_setup_rejects_false_return_with_wrong_readback(self):
        timeline = FakeTimeline("OUTPUT", "output-uid", {
            "timelineResolutionWidth": "1280", "timelineResolutionHeight": "720",
            "timelineFrameRate": "24", "timelinePlaybackFrameRate": "24",
        })

        def false_and_stale(key, value):
            return False

        timeline.SetSetting = false_and_stale
        with self.assertRaisesRegex(ValidationError, "Read-back"):
            _set_and_verify_format(timeline, {
                "width": 1920, "height": 1080, "fps": "24", "playback_fps": "24",
            })

    def test_media_and_timeline_frame_rates_are_converted_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = config(root)
            source_path = cfg.media_roots[0] / "podcast.mov"
            source_path.write_bytes(b"source-30-fps")
            source = FakeMediaItem("podcast.mov", 25 * 3600, source_path, "25")
            cta = FakeMediaItem(CONTRACT.cta_media_pool_name, 25 * 10, fps="25")
            project = FakeProject(source, cta)
            store = EditorialJobStore(cfg.editorial_jobs_path, cfg.workstation_id)
            selected = (candidate(1, 10, 14),)
            decisions = ({"candidate_id": "R01", "outcome": "APPROVE",
                          "source_start_seconds": 10.0, "source_end_seconds": 14.0,
                          "final_duration_seconds": 9.0, "reason": "forte"},)
            job = reviewed_job(store, media_fingerprint(source_path), selected, decisions)

            result = apply_or_resume_editorial_cuts(
                FakeResolve(), FakeManager(project), cfg, store, job.editorial_job_id, "d" * 64,
            )

        self.assertEqual("VERIFIED", result.state)
        appends = [call for call in project.calls if call[0] == "AppendToTimeline"]
        self.assertEqual((250, 349), appends[0][3:5])
        self.assertEqual((0, 124), appends[1][3:5])
        output = next(timeline for timeline in project.timelines if timeline.name.endswith("_R01"))
        self.assertEqual(120, output.video[1].record_start)
        self.assertEqual(270, output.GetEndFrame() - output.GetStartFrame() + 1)

    def test_approve_modify_reject_create_two_verified_timelines_in_order(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg, project, store, job = environment(Path(directory))
            result = apply_or_resume_editorial_cuts(
                FakeResolve(), FakeManager(project), cfg, store, job.editorial_job_id,
                "d" * 64,
            )

        self.assertEqual("VERIFIED", result.state)
        self.assertEqual(["R01", "R02", "R03"], [op["candidate_id"] for op in result.operations])
        self.assertEqual(["VERIFIED", "VERIFIED", "REJECTED"], [op["status"] for op in result.operations])
        created = [call[1] for call in project.calls if call[0] == "CreateEmptyTimeline"]
        self.assertEqual([f"ARPHE_{job.editorial_job_id[-8:]}_R01",
                          f"ARPHE_{job.editorial_job_id[-8:]}_R02"], created)
        appends = [call for call in project.calls if call[0] == "AppendToTimeline"]
        self.assertEqual(["podcast.mov", CONTRACT.cta_media_pool_name,
                          "podcast.mov", CONTRACT.cta_media_pool_name], [call[2] for call in appends])
        self.assertTrue(verify_editorial_outputs(project, result, CONTRACT)["ok"])

    def test_duration_defense_accepts_180_and_blocks_180_01_before_create(self):
        for final_seconds, accepted in ((180.0, True), (180.01, False)):
            with self.subTest(final_seconds=final_seconds), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                cfg = config(root)
                source_path = cfg.media_roots[0] / "podcast.mov"; source_path.write_bytes(b"source")
                project = FakeProject(FakeMediaItem("podcast.mov", 10000, source_path),
                                      FakeMediaItem(CONTRACT.cta_media_pool_name, 120))
                store = EditorialJobStore(cfg.editorial_jobs_path, cfg.workstation_id)
                speech = final_seconds - 5.0
                selected = (candidate(1, 0, speech),)
                decisions = ({"candidate_id": "R01", "outcome": "APPROVE",
                              "source_start_seconds": 0.0, "source_end_seconds": speech,
                              "final_duration_seconds": final_seconds, "reason": "completo"},)
                job = reviewed_job(store, media_fingerprint(source_path), selected, decisions)
                if accepted:
                    result = apply_or_resume_editorial_cuts(FakeResolve(), FakeManager(project), cfg,
                                                           store, job.editorial_job_id, "d" * 64)
                    self.assertEqual("VERIFIED", result.state)
                else:
                    with self.assertRaisesRegex(ValidationError, "180"):
                        apply_or_resume_editorial_cuts(FakeResolve(), FakeManager(project), cfg,
                                                       store, job.editorial_job_id, "d" * 64)
                    self.assertFalse(any(call[0] == "CreateEmptyTimeline" for call in project.calls))

    def test_stale_review_wrong_source_or_wrong_timeline_are_zero_write(self):
        for case in ("review", "source", "timeline"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                cfg, project, store, job = environment(Path(directory))
                fingerprint = "e" * 64 if case == "review" else "d" * 64
                if case == "source":
                    next(path for path in cfg.media_roots[0].iterdir()).write_bytes(b"changed")
                if case == "timeline": project.source.unique_id = "wrong"
                with self.assertRaises(ValidationError):
                    apply_or_resume_editorial_cuts(FakeResolve(), FakeManager(project), cfg, store,
                                                   job.editorial_job_id, fingerprint)
                self.assertFalse(any(call[0] == "CreateEmptyTimeline" for call in project.calls))

    def test_foreign_audio_manifest_blocks_before_create(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg, project, store, job = environment(Path(directory))
            output = cfg.audio_root / "enhanced.wav"; output.write_bytes(b"RIFF")
            audio_id = "audio_0123456789abcdef"
            (cfg.audio_jobs_root / f"{audio_id}.json").write_text(json.dumps({
                "schema": "ARPHE_AUDIO_JOB_V2", "job_id": audio_id, "status": "COMPLETED",
                "preset": "ARPHE_DIALOGUE_NATURAL_V4", "source_fingerprint": "f" * 64,
                "output_path": str(output), "output_sha256": file_sha256(output),
                "source_duration_seconds": 60.0, "output_duration_seconds": 60.0,
                "sync_delta_seconds": 0.0, "sample_rate": 48000, "channels": 2,
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "sorgente"):
                apply_or_resume_editorial_cuts(FakeResolve(), FakeManager(project), cfg, store,
                                               job.editorial_job_id, "d" * 64,
                                               audio_job_id=audio_id)
            self.assertFalse(any(call[0] == "CreateEmptyTimeline" for call in project.calls))

    def test_partial_failure_resumes_without_duplicate_timeline(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg, project, store, job = environment(Path(directory))
            second_name = f"ARPHE_{job.editorial_job_id[-8:]}_R02"
            project.pool.fail_name = second_name
            failed = apply_or_resume_editorial_cuts(FakeResolve(), FakeManager(project), cfg, store,
                                                    job.editorial_job_id, "d" * 64)
            self.assertEqual("FAILED_RECOVERABLE", failed.state)
            self.assertEqual("R01", failed.operations[0]["candidate_id"])
            project.pool.fail_name = None
            resumed = apply_or_resume_editorial_cuts(FakeResolve(), FakeManager(project), cfg, store,
                                                     job.editorial_job_id, "d" * 64)

        self.assertEqual("VERIFIED", resumed.state)
        first_name = f"ARPHE_{job.editorial_job_id[-8:]}_R01"
        creates = [call[1] for call in project.calls if call[0] == "CreateEmptyTimeline"]
        self.assertEqual(1, creates.count(first_name))

    def test_tampered_registered_output_blocks_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg, project, store, job = environment(Path(directory))
            project.pool.fail_name = f"ARPHE_{job.editorial_job_id[-8:]}_R02"
            failed = apply_or_resume_editorial_cuts(FakeResolve(), FakeManager(project), cfg, store,
                                                    job.editorial_job_id, "d" * 64)
            first = next(t for t in project.timelines if t.name.endswith("_R01"))
            first.video.clear()
            project.pool.fail_name = None
            blocked = apply_or_resume_editorial_cuts(FakeResolve(), FakeManager(project), cfg, store,
                                                     job.editorial_job_id, "d" * 64)

        self.assertEqual("BLOCKED", blocked.state)
        self.assertIn("tampered", blocked.operations[-1]["reason"])

    def test_foreign_expected_name_collision_is_not_adopted(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg, project, store, job = environment(Path(directory))
            name = f"ARPHE_{job.editorial_job_id[-8:]}_R01"
            project.timelines.append(FakeTimeline(name, "foreign-uid", project.settings))
            blocked = apply_or_resume_editorial_cuts(FakeResolve(), FakeManager(project), cfg, store,
                                                     job.editorial_job_id, "d" * 64)

        self.assertEqual("BLOCKED", blocked.state)
        self.assertFalse(any(call[0] == "CreateEmptyTimeline" for call in project.calls))


if __name__ == "__main__":
    unittest.main()
