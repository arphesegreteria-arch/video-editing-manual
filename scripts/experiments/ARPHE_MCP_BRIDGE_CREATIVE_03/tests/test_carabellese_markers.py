from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.carabellese_contract import load_carabellese_contract  # noqa: E402
from bridge.carabellese_jobs import CarabelleseJobStore, new_carabellese_job  # noqa: E402
from bridge.carabellese_markers import (  # noqa: E402
    carabellese_marker_specs,
    cleanup_carabellese_markers,
    mark_carabellese_review,
    verify_carabellese_markers,
)
from bridge.editorial_markers import timeline_identity  # noqa: E402


CONTRACT = load_carabellese_contract(ROOT / "carabellese_cleanup_contract.json")


def candidate(candidate_id: str, kind: str, start: float, end: float,
              review_required: bool) -> dict[str, object]:
    return {"candidate_id": candidate_id, "kind": kind, "start_seconds": start,
            "end_seconds": end, "start_anchor": "prima", "end_anchor": "dopo",
            "context_before": "prima", "context_after": "dopo", "reason": "test",
            "review_required": review_required, "residual_seconds": 0.7,
            "speaker_turn": False}


class FakeTimeline:
    def __init__(self, markers=None, fail_add: int | None = None):
        self.name = "PODCAST_YOUTUBE"
        self.markers = dict(markers or {})
        self.fail_add = fail_add
        self.add_calls = 0

    def GetUniqueId(self): return "carabellese-timeline"
    def GetName(self): return self.name
    def GetSetting(self, key): return "30" if key == "timelineFrameRate" else None
    def GetMarkers(self): return {frame: dict(value) for frame, value in self.markers.items()}
    def AddMarker(self, frame, color, name, note, duration, custom):
        self.add_calls += 1
        if self.fail_add == self.add_calls:
            return False
        self.markers[frame] = {"color": color, "name": name, "note": note,
                               "duration": duration, "customData": custom}
        return True
    def DeleteMarkerAtFrame(self, frame):
        if frame not in self.markers: return False
        del self.markers[frame]
        return True


def create_job(store: CarabelleseJobStore, timeline: FakeTimeline):
    candidates = (
        candidate("B01", "BOUNDARY_START", 1.0, 2.0, True),
        candidate("P01", "PAUSE_REDUCE", 3.0, 3.8, False),
        candidate("C01", "EDITORIAL_CUE", 5.0, 6.0, True),
    )
    return store.create(new_carabellese_job(
        workstation_id="PC_PERSONALE", workflow_version=1, project_name="STUDIO_CARABELLESE",
        timeline_name=timeline.name, timeline_identity=timeline_identity(timeline),
        timeline_fingerprint="0" * 64, source_fingerprint="1" * 64,
        transcript_fingerprint="2" * 64, contract_fingerprint="3" * 64,
        proposal_fingerprint="4" * 64, candidates=candidates,
    ))


class CarabelleseMarkerTests(unittest.TestCase):
    def test_specs_include_only_boundaries_and_individually_reviewed_exceptions(self):
        with tempfile.TemporaryDirectory() as raw_root:
            timeline = FakeTimeline()
            store = CarabelleseJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            specs = carabellese_marker_specs(create_job(store, timeline), CONTRACT)
        self.assertEqual(["B01", "B01", "C01", "C01"], [item["candidate_id"] for item in specs])
        self.assertNotIn("frame", specs[0])
        self.assertTrue(str(specs[0]["customData"]).startswith("CARABELLESE:"))

    def test_marking_converts_source_fps_preserves_foreign_and_retry_is_idempotent(self):
        foreign = {10: {"color": "Green", "name": "OPERATORE", "note": "x",
                        "duration": 1, "customData": "foreign"}}
        with tempfile.TemporaryDirectory() as raw_root:
            timeline = FakeTimeline(foreign)
            store = CarabelleseJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            marked = mark_carabellese_review(timeline, store, create_job(store, timeline), CONTRACT)
            count = timeline.add_calls
            replay = mark_carabellese_review(timeline, store, marked, CONTRACT)
        self.assertEqual("MARKED", marked.state)
        self.assertEqual(count, timeline.add_calls)
        self.assertEqual(marked, replay)
        self.assertEqual(foreign[10], timeline.markers[10])
        self.assertEqual([30, 60, 150, 180], [item["frame"] for item in marked.markers])
        self.assertTrue(verify_carabellese_markers(timeline, marked)["ok"])

    def test_collision_blocks_before_writes(self):
        collision = {30: {"color": "Red", "name": "ALTRO", "note": "", "duration": 1,
                          "customData": "foreign"}}
        with tempfile.TemporaryDirectory() as raw_root:
            timeline = FakeTimeline(collision)
            store = CarabelleseJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            blocked = mark_carabellese_review(timeline, store, create_job(store, timeline), CONTRACT)
        self.assertEqual("BLOCKED", blocked.state)
        self.assertEqual(0, timeline.add_calls)
        self.assertEqual(collision, timeline.markers)

    def test_add_failure_rolls_back_only_owned_attempt(self):
        foreign = {10: {"color": "Green", "name": "OPERATORE", "note": "x",
                        "duration": 1, "customData": "foreign"}}
        with tempfile.TemporaryDirectory() as raw_root:
            timeline = FakeTimeline(foreign, fail_add=2)
            store = CarabelleseJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            blocked = mark_carabellese_review(timeline, store, create_job(store, timeline), CONTRACT)
        self.assertEqual("BLOCKED", blocked.state)
        self.assertEqual(foreign, timeline.markers)

    def test_cleanup_deletes_only_owned_markers(self):
        foreign = {10: {"color": "Green", "name": "OPERATORE", "note": "x",
                        "duration": 1, "customData": "foreign"}}
        with tempfile.TemporaryDirectory() as raw_root:
            timeline = FakeTimeline(foreign)
            store = CarabelleseJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            marked = mark_carabellese_review(timeline, store, create_job(store, timeline), CONTRACT)
            result = cleanup_carabellese_markers(timeline, marked)
        self.assertTrue(result["ok"])
        self.assertEqual(foreign, timeline.markers)


if __name__ == "__main__":
    unittest.main()
