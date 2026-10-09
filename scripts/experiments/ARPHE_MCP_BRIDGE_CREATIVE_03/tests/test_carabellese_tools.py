from __future__ import annotations

from dataclasses import replace
import hashlib
import inspect
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.carabellese_jobs import new_carabellese_job  # noqa: E402
from bridge.config import DEFAULT_FLAGS  # noqa: E402
from bridge.tool_catalog import EXPOSED_TOOL_NAMES  # noqa: E402
import bridge.server as server  # noqa: E402


TOOLS = {
    "inspect_carabellese_cleanup", "start_carabellese_transcription",
    "get_carabellese_transcription_job", "prepare_carabellese_cleanup",
    "inspect_carabellese_job", "submit_carabellese_review",
    "apply_carabellese_cleanup", "recover_carabellese_cleanup",
    "close_carabellese_cleanup", "inspect_carabellese_learning",
    "compile_carabellese_profile_proposal", "approve_carabellese_profile_proposal",
}


def config(root: Path, enabled: bool = False):
    flags = dict(DEFAULT_FLAGS); flags["CAP_CARABELLESE_CLEANUP"] = enabled
    return SimpleNamespace(
        flags=flags, workstation_id="PC_PERSONALE", state_path=root / "state.json",
        audit_log_path=root / "audit.jsonl", transcript_root=root / "transcripts",
        media_roots=(root / "media",), carabellese_jobs_path=root / "jobs.json",
        carabellese_journal_path=root / "journal.jsonl",
        carabellese_profile_overlay_path=root / "overlay.json",
        carabellese_profile_proposals_path=root / "proposals.json",
        carabellese_checkpoint_root=root / "checkpoints",
        audio_root=root / "audio", audio_jobs_root=root / "audio_jobs",
    )


class CarabelleseToolTests(unittest.TestCase):
    def test_prepare_pins_current_source_marks_once_and_returns_secretary_card(self):
        class Media:
            def __init__(self, path): self.path = path
            def GetClipProperty(self, key): return str(self.path) if key == "File Path" else None
        class Item:
            def __init__(self, media): self.media = media
            def GetStart(self): return 0
            def GetEnd(self): return 90
            def GetDuration(self): return 90
            def GetMediaPoolItem(self): return self.media
        class Timeline:
            def __init__(self, media):
                self.items = {"video": [Item(media)], "audio": [Item(media)]}
                self.markers = {}; self.add_calls = 0
            def GetName(self): return "PODCAST_YOUTUBE"
            def GetUniqueId(self): return "carabellese-source"
            def GetStartFrame(self): return 0
            def GetEndFrame(self): return 90
            def GetSetting(self, key):
                return {"timelineResolutionWidth": "1920", "timelineResolutionHeight": "1080",
                        "timelineFrameRate": "30", "timelinePlaybackFrameRate": "30"}.get(key)
            def GetTrackCount(self, _kind): return 1
            def GetItemListInTrack(self, kind, _index): return list(self.items[kind])
            def GetMarkers(self): return {key: dict(value) for key, value in self.markers.items()}
            def AddMarker(self, frame, color, name, note, duration, custom):
                self.add_calls += 1
                self.markers[frame] = {"color": color, "name": name, "note": note,
                                       "duration": duration, "customData": custom}
                return True
            def DeleteMarkerAtFrame(self, frame): self.markers.pop(frame, None); return True
        class Project:
            def __init__(self, timeline): self.timeline = timeline
            def GetName(self): return "STUDIO_CARABELLESE"
            def GetCurrentTimeline(self): return self.timeline

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root); cfg = config(root, enabled=True)
            for path in (*cfg.media_roots, cfg.transcript_root, cfg.audio_root, cfg.audio_jobs_root):
                path.mkdir(parents=True)
            source = cfg.media_roots[0] / "podcast.mov"; source.write_bytes(b"source")
            source_fp = hashlib.sha256(b"source").hexdigest()
            transcript = cfg.transcript_root / "podcast.json"
            transcript.write_text(json.dumps({
                "schema": "ARPHE_TRANSCRIPT_V1", "status": "complete",
                "source": {"fingerprint": source_fp, "duration_seconds": 3.0},
                "segments": [{"words": [
                    {"word": "apertura", "start": 0.0, "end": 0.4, "speaker": "A"},
                    {"word": "contenuto", "start": 2.4, "end": 2.8, "speaker": "A"},
                ]}],
            }), encoding="utf-8")
            transcript_fp = hashlib.sha256(transcript.read_bytes()).hexdigest()
            wav = cfg.audio_root / "clean.wav"; wav.write_bytes(b"RIFF")
            (cfg.audio_jobs_root / "audio_0123456789abcdef.json").write_text(json.dumps({
                "schema": "ARPHE_AUDIO_JOB_V2", "job_id": "audio_0123456789abcdef",
                "status": "COMPLETED", "preset": "NATURAL", "source_fingerprint": source_fp,
                "output_path": str(wav), "output_sha256": hashlib.sha256(b"RIFF").hexdigest(),
                "source_duration_seconds": 3.0, "output_duration_seconds": 3.0,
                "sync_delta_seconds": 0.0, "sample_rate": 48000, "channels": 2,
                "silence_windows": [{"start": 0.4, "end": 2.4}],
            }), encoding="utf-8")
            candidate = [{"candidate_id": "B01", "kind": "BOUNDARY_START",
                "start_seconds": 0.0, "end_seconds": 0.4,
                "start_anchor": {"text": "apertura"}, "end_anchor": {"text": "apertura"},
                "context_before": "apertura", "context_after": "contenuto",
                "reason": "inizio reale", "review_required": True,
                "residual_seconds": None, "speaker_turn": False}]
            timeline = Timeline(Media(source))
            timeline.items["audio"][0].media = Media(source)
            project = Project(timeline)
            runtime = (object(), object(), project, timeline, cfg, object(), None)
            with patch("bridge.server.load_config", return_value=cfg), \
                 patch("bridge.server._runtime", return_value=runtime):
                first = server.prepare_carabellese_cleanup(
                    str(transcript), transcript_fp, source_fp,
                    "audio_0123456789abcdef", candidate)
                replay = server.prepare_carabellese_cleanup(
                    str(transcript), transcript_fp, source_fp,
                    "audio_0123456789abcdef", candidate)

        self.assertTrue(first["ok"])
        self.assertEqual("MARKED", first["state"])
        self.assertEqual(1, first["instructions"]["card_count"])
        self.assertEqual(first["carabellese_job_id"], replay["carabellese_job_id"])
        self.assertTrue(replay["idempotent"])
        self.assertGreater(timeline.add_calls, 0)

    def test_catalog_is_closed_and_has_no_generic_mutation_parameters(self):
        self.assertTrue(TOOLS.issubset(EXPOSED_TOOL_NAMES))
        forbidden = {"workstation_id", "workflow_id", "project_name", "timeline_name",
                     "shell", "code", "resolve_method", "path"}
        for name in TOOLS:
            self.assertTrue(forbidden.isdisjoint(inspect.signature(getattr(server, name)).parameters))

    def test_inspections_work_default_off_and_return_one_compact_card(self):
        with tempfile.TemporaryDirectory() as raw_root:
            cfg = config(Path(raw_root), enabled=False)
            with patch("bridge.server.load_config", return_value=cfg):
                inspected = server.inspect_carabellese_cleanup()
                metrics = server.inspect_carabellese_learning()
        self.assertTrue(inspected["ok"])
        self.assertFalse(inspected["capability_enabled"])
        self.assertEqual("PC_PERSONALE", inspected["workstation_id"])
        self.assertEqual(1, inspected["card_count"])
        self.assertTrue(metrics["ok"])
        self.assertEqual(0, metrics["sample_count"])

    def test_all_writes_fail_closed_before_runtime_or_worker(self):
        cfg = config(Path("unused"), enabled=False)
        trap = AssertionError("must not call implementation while disabled")
        with patch("bridge.server.load_config", return_value=cfg), \
             patch("bridge.server._runtime", side_effect=trap), \
             patch("bridge.server.do_start_carabellese_transcription", side_effect=trap), \
             patch("bridge.server.do_submit_carabellese_review", side_effect=trap):
            results = (
                server.start_carabellese_transcription("media.mov", "a" * 64),
                server.prepare_carabellese_cleanup("tx.json", "b" * 64, "a" * 64,
                                                   "audio_0123456789abcdef", []),
                server.submit_carabellese_review("carabellese_0123456789abcdef", [],
                                                 {"outcome": "KEEP", "reason": "ok"}, [],
                                                 "tx.json", "b" * 64),
                server.apply_carabellese_cleanup("carabellese_0123456789abcdef", "c" * 64),
                server.recover_carabellese_cleanup("carabellese_0123456789abcdef"),
                server.close_carabellese_cleanup("carabellese_0123456789abcdef"),
                server.compile_carabellese_profile_proposal(),
                server.approve_carabellese_profile_proposal(
                    "proposal_0123456789abcdef", "ALESSIO", "d" * 64),
            )
        for result in results:
            self.assertFalse(result["ok"])
            self.assertIn("CAP_CARABELLESE_CLEANUP", result["error"])

    def test_marked_job_inspection_explains_exact_single_reply(self):
        job = new_carabellese_job(
            workstation_id="PC_PERSONALE", workflow_version=1, project_name="STUDIO_CARABELLESE",
            timeline_name="PODCAST_YOUTUBE", timeline_identity="resolve:one",
            timeline_fingerprint="1" * 64, source_fingerprint="2" * 64,
            transcript_fingerprint="3" * 64, contract_fingerprint="4" * 64,
            proposal_fingerprint="5" * 64,
            candidates=({"candidate_id": "B01", "kind": "BOUNDARY_START"},
                        {"candidate_id": "P01", "kind": "PAUSE_REDUCE"},
                        {"candidate_id": "C01", "kind": "EDITORIAL_CUE",
                         "review_required": True}),
        )
        marked = replace(job, state="MARKED", revision=2, markers=({"frame": 1},))
        cfg = config(Path("unused"))
        with patch("bridge.server.load_config", return_value=cfg), \
             patch("bridge.server._carabellese_store") as store:
            store.return_value.get.return_value = marked
            result = server.inspect_carabellese_job(marked.carabellese_job_id)
        self.assertTrue(result["ok"])
        self.assertEqual(1, result["instructions"]["card_count"])
        self.assertIn("un solo messaggio", result["instructions"]["instruction"])
        self.assertNotIn("candidates", result)


if __name__ == "__main__":
    unittest.main()
