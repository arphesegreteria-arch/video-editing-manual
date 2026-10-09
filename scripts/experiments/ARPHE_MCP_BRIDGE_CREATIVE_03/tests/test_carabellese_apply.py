from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.carabellese_apply import (  # noqa: E402
    apply_or_resume_carabellese_cleanup,
    inspect_carabellese_apply_support,
    verify_carabellese_timeline,
)
from bridge.carabellese_checkpoint import timeline_content_fingerprint  # noqa: E402
from bridge.carabellese_contract import (carabellese_contract_fingerprint,
                                         load_carabellese_contract)  # noqa: E402
from bridge.carabellese_jobs import CarabelleseJobStore, new_carabellese_job  # noqa: E402
from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402
from bridge.editorial_markers import timeline_identity  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402


CONTRACT = load_carabellese_contract(ROOT / "carabellese_cleanup_contract.json")


class Media:
    def __init__(self, path): self.path = path
    def GetClipProperty(self, key):
        return {"File Path": str(self.path), "FPS": "30", "Frames": "300"}.get(key)


class Item:
    def __init__(self, media, start, duration, source_start=0):
        self.media, self.start, self.duration, self.source_start = media, start, duration, source_start
    def GetStart(self): return self.start
    def GetEnd(self): return self.start + self.duration
    def GetDuration(self): return self.duration
    def GetMediaPoolItem(self): return self.media
    def GetSourceStartFrame(self): return self.source_start


class Timeline:
    def __init__(self, media, foreign_marker=False, extra_track=False,
                 unique_id="timeline-carabellese"):
        self.name = "PODCAST_YOUTUBE"
        self.unique_id = unique_id
        self.settings = {"timelineResolutionWidth": "1920", "timelineResolutionHeight": "1080",
                         "timelineFrameRate": "30", "timelinePlaybackFrameRate": "30"}
        self.tracks = {"video": [[Item(media, 0, 300)]], "audio": [[Item(media, 0, 300)]]}
        if extra_track: self.tracks["video"].append([])
        custom = "foreign" if foreign_marker else "CARABELLESE:owned:C01:IN"
        self.markers = {60: {"color": "Cyan", "name": "m", "note": "n", "duration": 1,
                             "customData": custom}}
        self.delete_calls = 0
    def GetUniqueId(self): return self.unique_id
    def GetName(self): return self.name
    def SetName(self, value): self.name = value; return True
    def GetStartFrame(self): return 0
    def GetEndFrame(self):
        items = [item for tracks in self.tracks.values() for track in tracks for item in track]
        return max((item.GetEnd() for item in items), default=0)
    def GetSetting(self, key): return self.settings.get(key)
    def GetTrackCount(self, kind): return len(self.tracks[kind])
    def GetItemListInTrack(self, kind, index): return list(self.tracks[kind][index - 1])
    def GetMarkers(self): return {frame: dict(value) for frame, value in self.markers.items()}
    def AddMarker(self, frame, color, name, note, duration, custom_data):
        self.markers[frame] = {"color": color, "name": name, "note": note,
                               "duration": duration, "customData": custom_data}
        return True
    def DeleteMarkerAtFrame(self, frame):
        if frame not in self.markers: return False
        del self.markers[frame]
        return True
    def AddTrack(self, kind): self.tracks[kind].append([]); return True
    def DeleteClips(self, items, _ripple=False):
        self.delete_calls += 1
        for item in items:
            for tracks in self.tracks.values():
                for track in tracks:
                    if item in track: track.remove(item)
        return True
    def DeleteTrack(self, kind, index): del self.tracks[kind][index - 1]; return True


class Pool:
    def __init__(self, project, fail_append=None):
        self.project, self.fail_append, self.append_calls = project, fail_append, []
    def AppendToTimeline(self, records):
        for record in records:
            self.append_calls.append(dict(record))
            if self.fail_append == len(self.append_calls): return False
            kind = "video" if record.get("mediaType") == 1 else "audio"
            duration = int(record["endFrame"]) - int(record["startFrame"]) + 1
            item = Item(record["mediaPoolItem"], int(record["recordFrame"]), duration,
                        int(record["startFrame"]))
            self.project.timeline.tracks[kind][int(record["trackIndex"]) - 1].append(item)
        return True
    def ImportTimelineFromFile(self, path, options):
        del path
        media = self.project.timelines[0].tracks["video"][0][0].GetMediaPoolItem()
        imported = Timeline(media, unique_id="timeline-restored")
        imported.name = options["timelineName"]
        self.project.timelines.append(imported)
        return imported
    def DeleteTimelines(self, timelines):
        for timeline in timelines:
            if timeline in self.project.timelines: self.project.timelines.remove(timeline)
        return True


class Project:
    def __init__(self, timeline, fail_append=None):
        self.timeline, self.timelines, self.pool = timeline, [timeline], None
        self.pool = Pool(self, fail_append)
    def GetName(self): return "STUDIO_CARABELLESE"
    def GetCurrentTimeline(self): return self.timeline
    def SetCurrentTimeline(self, timeline): self.timeline = timeline; return True
    def GetMediaPool(self): return self.pool
    def GetTimelineCount(self): return len(self.timelines)
    def GetTimelineByIndex(self, index): return self.timelines[index - 1]
    def GetSetting(self, key): return self.timeline.GetSetting(key)


class Manager:
    def __init__(self, project): self.project = project
    def GetCurrentProject(self): return self.project


class Resolve: pass


def config(root, media_root, transcript_root):
    flags = dict(DEFAULT_FLAGS); flags["CAP_CARABELLESE_CLEANUP"] = True
    return CreativeConfig(path=root / "config.json", asset_root=root / "assets",
        render_root=root / "renders", state_path=root / "state.json", audit_log_path=root / "audit.jsonl",
        palette=dict(DEFAULT_PALETTE), flags=flags, allowed_projects=frozenset(),
        allowed_timelines=frozenset(), render_format="mp4", render_codec="H264",
        media_roots=(media_root,), transcript_root=transcript_root, workstation_id="PC_PERSONALE",
        carabellese_journal_path=root / "carabellese_journal.jsonl")


def setup(root, *, foreign_marker=False, extra_track=False, fail_append=None):
    media_root, transcript_root = root / "media", root / "transcripts"
    media_root.mkdir(); transcript_root.mkdir()
    source = media_root / "podcast.mov"; source.write_bytes(b"source")
    media = Media(source); timeline = Timeline(media, foreign_marker, extra_track)
    project = Project(timeline, fail_append); manager = Manager(project)
    tx = {"schema": "ARPHE_TRANSCRIPT_V1", "status": "complete",
          "source": {"fingerprint": hashlib.sha256(b"source").hexdigest(), "duration_seconds": 10.0},
          "segments": [{"words": [{"word": "x", "start": 0.0, "end": 0.2}]}]}
    tx_path = transcript_root / "podcast.transcript.json"
    tx_path.write_text(json.dumps(tx), encoding="utf-8")
    tx_fp = hashlib.sha256(tx_path.read_bytes()).hexdigest()
    candidates = (
        {"candidate_id": "C01", "kind": "EDITORIAL_CUE", "start_seconds": 2.0,
         "end_seconds": 3.0, "review_required": True},
        {"candidate_id": "P01", "kind": "PAUSE_REDUCE", "start_seconds": 6.0,
         "end_seconds": 7.0, "review_required": False},
    )
    proposal_fp = hashlib.sha256(json.dumps(list(candidates), ensure_ascii=False, sort_keys=True,
                                            separators=(",", ":")).encode()).hexdigest()
    store = CarabelleseJobStore(root / "jobs.json", "PC_PERSONALE")
    created = store.create(new_carabellese_job(
        workstation_id="PC_PERSONALE", workflow_version=CONTRACT.version,
        project_name="STUDIO_CARABELLESE", timeline_name="PODCAST_YOUTUBE",
        timeline_identity=timeline_identity(timeline), timeline_fingerprint=timeline_content_fingerprint(timeline),
        source_fingerprint=hashlib.sha256(b"source").hexdigest(), transcript_fingerprint=tx_fp,
        contract_fingerprint=carabellese_contract_fingerprint(CONTRACT),
        proposal_fingerprint=proposal_fp, candidates=candidates))
    if not foreign_marker:
        timeline.markers[60]["customData"] = f"CARABELLESE:{created.carabellese_job_id}:C01:IN"
    marker_record = {"frame": 60, **timeline.markers[60]}
    marked = store.save(replace(created, state="MARKED", markers=(marker_record,)), created.revision)
    decisions = ({"candidate_id": "C01", "outcome": "REMOVE", "reason": "serio",
                  "start_seconds": 2.0, "end_seconds": 3.0},
                 {"candidate_id": "P01", "outcome": "SHORTEN", "reason": "ritmo",
                  "start_seconds": 6.0, "end_seconds": 7.0, "residual_seconds": 0.7})
    reviewed = store.save(replace(marked, state="REVIEWED", review_fingerprint="5" * 64,
                                  decisions=decisions), marked.revision)
    drt = root / "checkpoint.drt"; drt.write_bytes(b"DRT")
    digest = hashlib.sha256(b"DRT").hexdigest()
    manifest = {"path": str(drt), "sha256": digest, "size_bytes": 3,
                "timeline_fingerprint": reviewed.timeline_fingerprint,
                "source_fingerprint": reviewed.source_fingerprint,
                "review_fingerprint": reviewed.review_fingerprint, "exported_at": "now"}
    checkpointed = store.save(replace(reviewed, state="CHECKPOINTED", checkpoint_fingerprint=digest,
                                      checkpoint_manifest=manifest), reviewed.revision)
    return config(root, media_root, transcript_root), store, checkpointed, project, manager


class CarabelleseApplyTests(unittest.TestCase):
    def test_bound_input_and_api_preflight_matrix_is_zero_write(self):
        cases = ("project", "identity", "source", "transcript", "contract", "review",
                 "checkpoint", "timeline", "api")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as raw_root:
                root = Path(raw_root); cfg, store, job, project, manager = setup(root)
                expected_review = job.review_fingerprint
                if case == "project":
                    project.GetName = lambda: "ALTRO_PROGETTO"
                elif case == "identity":
                    project.timeline.GetUniqueId = lambda: "foreign"
                elif case == "source":
                    (root / "media" / "podcast.mov").write_bytes(b"changed-source")
                elif case == "transcript":
                    (root / "transcripts" / "podcast.transcript.json").write_text("{}", encoding="utf-8")
                elif case == "contract":
                    registry = json.loads((root / "jobs.json").read_text(encoding="utf-8"))
                    registry["jobs"][job.carabellese_job_id]["contract_fingerprint"] = "9" * 64
                    (root / "jobs.json").write_text(json.dumps(registry), encoding="utf-8")
                elif case == "review":
                    expected_review = "9" * 64
                elif case == "checkpoint":
                    unsupported = replace(job, checkpoint_fingerprint=None, checkpoint_manifest=None)
                    result = inspect_carabellese_apply_support(Resolve(), project, project.timeline, unsupported)
                    self.assertFalse(result["supported"])
                    continue
                elif case == "timeline":
                    project.timeline.tracks["video"][0][0].duration = 299
                elif case == "api":
                    project.timeline.AddTrack = None
                with self.assertRaises(ValidationError):
                    apply_or_resume_carabellese_cleanup(Resolve(), manager, cfg, store,
                                                        job.carabellese_job_id, expected_review)
                self.assertEqual(0, project.timeline.delete_calls)
                self.assertEqual(0, len(project.pool.append_calls))

    def test_preflight_rejects_foreign_tracks_markers_and_playback_without_writes(self):
        for case in ("tracks", "markers", "playback"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as raw_root:
                root = Path(raw_root)
                cfg, store, job, project, _ = setup(root, extra_track=case == "tracks",
                                                    foreign_marker=case == "markers")
                if case == "playback": project.timeline.settings["timelinePlaybackFrameRate"] = "24"
                before = project.timeline.delete_calls
                result = inspect_carabellese_apply_support(Resolve(), project, project.timeline, job)
                self.assertFalse(result["supported"])
                self.assertEqual(before, project.timeline.delete_calls)
                self.assertEqual(0, len(project.pool.append_calls))

    def test_blocked_failed_preflight_is_persisted_byte_equivalent(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root); cfg, store, job, project, manager = setup(root)
            blocked = store.save(replace(job, state="BLOCKED", resume_state="CHECKPOINTED"), job.revision)
            before = (root / "jobs.json").read_bytes()
            with self.assertRaises(ValidationError):
                apply_or_resume_carabellese_cleanup(Resolve(), manager, cfg, store,
                                                    blocked.carabellese_job_id, "wrong")
            self.assertEqual(before, (root / "jobs.json").read_bytes())

    def test_apply_orders_removals_latest_first_is_idempotent_and_verifies_duration(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root); cfg, store, job, project, manager = setup(root)
            verified = apply_or_resume_carabellese_cleanup(
                Resolve(), manager, cfg, store, job.carabellese_job_id, job.review_fingerprint)
            append_count = len(project.pool.append_calls)
            replay = apply_or_resume_carabellese_cleanup(
                Resolve(), manager, cfg, store, job.carabellese_job_id, job.review_fingerprint)
            evidence = verify_carabellese_timeline(project, project.timeline, verified)
        cuts = [op for op in verified.operations if op.get("operation") == "remove"]
        self.assertEqual(["P01", "C01"], [op["candidate_id"] for op in cuts])
        self.assertEqual("VERIFIED", verified.state)
        self.assertEqual(append_count, len(project.pool.append_calls))
        self.assertEqual(verified, replay)
        self.assertEqual(240, evidence["final_frames"])
        self.assertEqual(1, project.timeline.GetTrackCount("video"))
        self.assertEqual(1, project.timeline.GetTrackCount("audio"))
        self.assertFalse(evidence["transitions_verified"])

    def test_staging_failure_keeps_original_and_stops_later_work(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root); cfg, store, job, project, manager = setup(root, fail_append=2)
            failed = apply_or_resume_carabellese_cleanup(
                Resolve(), manager, cfg, store, job.carabellese_job_id, job.review_fingerprint)
        self.assertEqual("FAILED_RECOVERABLE", failed.state)
        self.assertEqual(0, project.timeline.delete_calls)
        self.assertEqual(2, len(project.pool.append_calls))
        self.assertEqual(300, project.timeline.GetItemListInTrack("video", 1)[0].GetDuration())


if __name__ == "__main__":
    unittest.main()
