from __future__ import annotations

import inspect
import hashlib
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

from bridge.config import DEFAULT_FLAGS  # noqa: E402
from bridge.editorial_jobs import EditorialJobStore  # noqa: E402
from bridge.tool_catalog import EXPOSED_TOOL_NAMES  # noqa: E402
import bridge.server as server  # noqa: E402


TOOLS = {
    "inspect_editorial_selection", "prepare_podcast_reel_selection",
    "inspect_editorial_selection_job", "submit_podcast_reel_review",
    "apply_podcast_reel_selection", "close_podcast_reel_selection",
    "inspect_editorial_learning", "compile_editorial_profile_proposal",
    "approve_editorial_profile_proposal",
}


def config(root: Path, enabled: bool = False):
    flags = dict(DEFAULT_FLAGS); flags["CAP_EDITORIAL_SELECTION"] = enabled
    return SimpleNamespace(
        flags=flags, workstation_id="PC_PERSONALE", state_path=root / "state.json",
        audit_log_path=root / "audit.jsonl", transcript_root=root / "transcripts",
        media_roots=(root / "media",), editorial_jobs_path=root / "jobs.json",
        editorial_journal_path=root / "journal.jsonl",
        editorial_profile_overlay_path=root / "overlay.json",
        editorial_profile_proposals_path=root / "proposals.json",
    )


class EditorialSelectionToolTests(unittest.TestCase):
    def test_prepare_is_end_to_end_idempotent_without_duplicate_markers(self):
        class Timeline:
            def __init__(self): self.markers = {}; self.add_calls = 0
            def GetName(self): return "ARPHE_SOURCE"
            def GetUniqueId(self): return "source-uid"
            def GetSetting(self, key):
                return {"timelineFrameRate": "30", "timelinePlaybackFrameRate": "30"}.get(key)
            def GetMarkers(self): return dict(self.markers)
            def AddMarker(self, frame, color, name, note, duration, custom):
                self.add_calls += 1
                self.markers[frame] = {"color": color, "name": name, "note": note,
                                       "duration": duration, "customData": custom}
                return True
            def DeleteMarkerAtFrame(self, frame): self.markers.pop(frame, None); return True
            def GetItemListInTrack(self, *_args): return []

        class Pool:
            def CreateEmptyTimeline(self, _name): return object()
            def AppendToTimeline(self, _records): return True
            def GetRootFolder(self): return self

        class Project:
            def __init__(self, timeline): self.timeline = timeline; self.pool = Pool()
            def GetName(self): return "ARPHE_PROJECT"
            def GetTimelineCount(self): return 1
            def GetTimelineByIndex(self, _index): return self.timeline
            def GetMediaPool(self): return self.pool
            def SetCurrentTimeline(self, _timeline): return True
            def GetSetting(self, key):
                return {"timelineFrameRate": "30", "timelinePlaybackFrameRate": "30"}.get(key)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); cfg = config(root, enabled=True)
            cfg.transcript_root.mkdir(); (root / "media").mkdir()
            transcript = cfg.transcript_root / "podcast.json"
            transcript.write_text(json.dumps({
                "schema": "ARPHE_TRANSCRIPT_V1", "status": "complete",
                "source": {"fingerprint": "b" * 64, "duration_seconds": 60.0},
                "segments": [{"start": 10.0, "end": 14.0, "text": "apertura contenuto chiusura",
                              "words": [{"word": "apertura", "start": 10.0, "end": 10.5},
                                        {"word": "contenuto", "start": 10.5, "end": 13.5},
                                        {"word": "chiusura", "start": 13.5, "end": 14.0}]}],
            }), encoding="utf-8")
            fingerprint = hashlib.sha256(transcript.read_bytes()).hexdigest()
            candidate = [{
                "candidate_id": "R01", "thesis": "Una tesi forte",
                "start_anchor": {"text": "apertura"}, "end_anchor": {"text": "chiusura"},
                "indispensable_context": "Contesto essenziale", "source_start_seconds": 10.0,
                "source_end_seconds": 14.0, "speech_duration_seconds": 4.0,
                "cta_duration_seconds": 5.0, "final_duration_seconds": 9.0,
                "uniqueness_evidence": "Tema distinto", "quality_rationale": "Autosufficiente",
            }]
            timeline = Timeline(); project = Project(timeline)
            runtime = (object(), object(), project, timeline, cfg, object(), None)
            with patch("bridge.server._runtime", return_value=runtime):
                first = server.prepare_podcast_reel_selection(
                    str(transcript), fingerprint, "b" * 64, candidate
                )
                second = server.prepare_podcast_reel_selection(
                    str(transcript), fingerprint, "b" * 64, candidate
                )

        self.assertTrue(first["ok"])
        self.assertEqual(first["editorial_job_id"], second["editorial_job_id"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(2, timeline.add_calls)

    def test_prepare_blocks_24_fps_with_chat_flag_before_any_marker_write(self):
        class Timeline:
            def GetSetting(self, key):
                return {"timelineFrameRate": "24", "timelinePlaybackFrameRate": "24"}.get(key)

        class Project:
            def GetSetting(self, key):
                return {"timelineFrameRate": "24", "timelinePlaybackFrameRate": "24"}.get(key)

        with tempfile.TemporaryDirectory() as directory:
            cfg = config(Path(directory), enabled=True)
            runtime = (object(), object(), Project(), Timeline(), cfg, object(), None)
            with patch("bridge.server._runtime", return_value=runtime), \
                 patch("bridge.server.require_capability"), \
                 patch("bridge.server.do_mark_candidates", side_effect=AssertionError("must not mark")):
                result = server.prepare_podcast_reel_selection(
                    "missing.json", "a" * 64, "b" * 64, [],
                )

        self.assertFalse(result["ok"])
        self.assertEqual("PLAYBACK_FPS_ACTION_REQUIRED", result.get("flag"))
        self.assertEqual("24", result.get("actual_playback_fps"))
        self.assertEqual("30", result.get("required_playback_fps"))

    def test_catalog_has_only_closed_editorial_surface_and_no_override_parameters(self):
        self.assertTrue(TOOLS.issubset(EXPOSED_TOOL_NAMES))
        forbidden = {"workstation_id", "workflow_id", "max_duration", "shell", "code"}
        for name in TOOLS:
            self.assertTrue(forbidden.isdisjoint(inspect.signature(getattr(server, name)).parameters))

    def test_read_only_inspections_work_while_default_off(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = config(Path(directory))
            with patch("bridge.server.load_config", return_value=cfg):
                contract = server.inspect_editorial_selection()
                metrics = server.inspect_editorial_learning()
        self.assertTrue(contract["ok"])
        self.assertEqual("ARPHE_PODCAST_REELS_CTA", contract["workflow_id"])
        self.assertEqual(30.0, contract["required_project_fps"])
        self.assertTrue(metrics["ok"])
        self.assertEqual(0, metrics["candidate_count"])

    def test_every_default_off_write_fails_before_resolve_or_orchestrator(self):
        class Trap:
            def __getattr__(self, name):
                raise AssertionError(f"unexpected Resolve access: {name}")

        with tempfile.TemporaryDirectory() as directory:
            cfg = config(Path(directory), enabled=False)
            runtime = (Trap(), Trap(), Trap(), Trap(), cfg, Trap(), None)
            with patch("bridge.server._runtime", return_value=runtime), \
                 patch("bridge.server.load_config", return_value=cfg), \
                 patch("bridge.server.do_mark_candidates", side_effect=AssertionError("must not mark")), \
                 patch("bridge.server.do_apply_editorial_cuts", side_effect=AssertionError("must not cut")):
                results = (
                    server.prepare_podcast_reel_selection("x.json", "a" * 64, "b" * 64, []),
                    server.submit_podcast_reel_review("editorial_0123456789abcdef", [], "x.json", "a" * 64),
                    server.apply_podcast_reel_selection("editorial_0123456789abcdef", "d" * 64),
                    server.close_podcast_reel_selection("editorial_0123456789abcdef"),
                    server.compile_editorial_profile_proposal(),
                    server.approve_editorial_profile_proposal("proposal_0123456789abcdef", "ALESSIO", "f" * 64),
                )
        for result in results:
            self.assertFalse(result["ok"])
            self.assertIn("CAP_EDITORIAL_SELECTION", result["error"])

    def test_job_inspection_is_compact_and_state_specific(self):
        marked = SimpleNamespace(
            state="MARKED", project_name="ARPHE_PROJECT", timeline_name="ARPHE_SOURCE",
            candidates=({"candidate_id": "R01"},), editorial_job_id="editorial_0123456789abcdef",
            revision=2, operations=(),
        )
        blocked = SimpleNamespace(**{**marked.__dict__, "state": "BLOCKED",
                                    "operations": ({"reason": "marker_collision"},)})
        with tempfile.TemporaryDirectory() as directory:
            cfg = config(Path(directory))
            with patch("bridge.server.load_config", return_value=cfg), \
                 patch.object(EditorialJobStore, "get", side_effect=[marked, blocked]):
                first = server.inspect_editorial_selection_job(marked.editorial_job_id)
                second = server.inspect_editorial_selection_job(marked.editorial_job_id)
        self.assertIn("steps", first["instructions"])
        self.assertNotIn("candidates", first)
        self.assertEqual("recovery_required", second["next_action"])
        self.assertNotIn("marker_collision", str(second))

    def test_foreign_job_registry_is_not_read(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = config(Path(directory))
            cfg.editorial_jobs_path.write_text(json.dumps({
                "schema": "ARPHE_EDITORIAL_JOBS_V1", "workstation_id": "PC_SEGRETERIA",
                "jobs": {},
            }), encoding="utf-8")
            with patch("bridge.server.load_config", return_value=cfg):
                result = server.inspect_editorial_selection_job("editorial_0123456789abcdef")
        self.assertFalse(result["ok"])
        self.assertIn("workstation", result["error"])


if __name__ == "__main__":
    unittest.main()
