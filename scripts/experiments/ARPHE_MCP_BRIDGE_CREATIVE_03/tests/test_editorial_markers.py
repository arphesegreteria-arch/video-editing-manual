from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.editorial_jobs import EditorialJobStore, new_editorial_job  # noqa: E402
from bridge.editorial_markers import (  # noqa: E402
    cleanup_verified_markers,
    mark_candidates,
    marker_specs,
    timeline_identity,
    verify_job_markers,
)
from bridge.editorial_selection_contract import load_selection_contract  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402


CONTRACT = load_selection_contract(ROOT / "editorial_selection_contract.json")


def candidate(index: int) -> dict[str, object]:
    return {
        "candidate_id": f"R{index:02d}",
        "source_in_frame": index * 100,
        "source_out_frame_exclusive": index * 100 + 50,
        "thesis": f"Tesi {index}",
        "indispensable_context": f"Contesto {index}",
        "final_duration_seconds": 7.0,
    }


class FakeTimeline:
    def __init__(self, *, unique_id: str = "timeline-123", markers=None,
                 fail_add_call: int | None = None, corrupt_add_call: int | None = None):
        self.unique_id = unique_id
        self.name = "ARPHE_SOURCE"
        self.markers = dict(markers or {})
        self.fail_add_call = fail_add_call
        self.corrupt_add_call = corrupt_add_call
        self.add_calls = 0
        self.calls: list[tuple] = []

    def GetUniqueId(self):
        self.calls.append(("GetUniqueId",))
        return self.unique_id

    def GetName(self):
        self.calls.append(("GetName",))
        return self.name

    def GetMarkers(self):
        self.calls.append(("GetMarkers",))
        return {frame: dict(value) for frame, value in self.markers.items()}

    def AddMarker(self, frame, color, name, note, duration, custom_data):
        self.calls.append(("AddMarker", frame, color, name, note, duration, custom_data))
        self.add_calls += 1
        if self.fail_add_call == self.add_calls:
            return False
        stored_name = "CORROTTO" if self.corrupt_add_call == self.add_calls else name
        self.markers[frame] = {
            "color": color, "name": stored_name, "note": note,
            "duration": duration, "customData": custom_data,
        }
        return True

    def DeleteMarkerAtFrame(self, frame):
        self.calls.append(("DeleteMarkerAtFrame", frame))
        if frame not in self.markers:
            return False
        del self.markers[frame]
        return True


def create_job(store: EditorialJobStore, timeline: FakeTimeline, count: int = 1):
    return store.create(new_editorial_job(
        workstation_id="PC_PERSONALE",
        workflow_version=1,
        project_name="ARPHE_TEST_PROJECT",
        timeline_name="ARPHE_SOURCE",
        timeline_identity=timeline_identity(timeline),
        source_fingerprint="a" * 64,
        transcript_fingerprint="b" * 64,
        candidate_fingerprint="c" * 64,
        candidates=tuple(candidate(index) for index in range(1, count + 1)),
    ))


class EditorialMarkerTests(unittest.TestCase):
    def test_marker_specs_create_exact_in_out_namespace_for_one_and_twenty(self):
        for count in (1, 20):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as raw_root:
                timeline = FakeTimeline()
                store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
                job = create_job(store, timeline, count)
                specs = marker_specs(job, CONTRACT)
                self.assertEqual(count * 2, len(specs))
                self.assertEqual("ARPHE_R01_IN", specs[0]["name"])
                self.assertEqual(f"ARPHE_R{count:02d}_OUT", specs[-1]["name"])
                self.assertEqual(1, specs[0]["duration"])

    def test_marking_preserves_foreign_markers_and_calls_no_edit_primitive(self):
        foreign = {10: {"color": "Green", "name": "OPERATORE", "note": "nota",
                        "duration": 1, "customData": "foreign"}}
        with tempfile.TemporaryDirectory() as raw_root:
            timeline = FakeTimeline(markers=foreign)
            store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            job = create_job(store, timeline, 1)
            marked = mark_candidates(timeline, store, job, CONTRACT)

        self.assertEqual("MARKED", marked.state)
        self.assertEqual(foreign[10], timeline.markers[10])
        self.assertEqual(3, len(timeline.markers))
        self.assertTrue(verify_job_markers(timeline, marked)["ok"])
        allowed = {"GetUniqueId", "GetName", "GetMarkers", "AddMarker", "DeleteMarkerAtFrame"}
        self.assertTrue({call[0] for call in timeline.calls} <= allowed)

    def test_collision_blocks_before_any_marker_write(self):
        collision = {100: {"color": "Red", "name": "ALTRO", "note": "", "duration": 1,
                           "customData": "foreign"}}
        with tempfile.TemporaryDirectory() as raw_root:
            timeline = FakeTimeline(markers=collision)
            store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            job = create_job(store, timeline)
            blocked = mark_candidates(timeline, store, job, CONTRACT)

        self.assertEqual("BLOCKED", blocked.state)
        self.assertEqual(0, timeline.add_calls)
        self.assertEqual(collision, timeline.markers)
        self.assertEqual(100, blocked.operations[-1]["frame"])

    def test_mid_write_failure_rolls_back_only_this_attempt(self):
        foreign = {10: {"color": "Green", "name": "OPERATORE", "note": "nota",
                        "duration": 1, "customData": "foreign"}}
        with tempfile.TemporaryDirectory() as raw_root:
            timeline = FakeTimeline(markers=foreign, fail_add_call=2)
            store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            job = create_job(store, timeline, 2)
            blocked = mark_candidates(timeline, store, job, CONTRACT)

        self.assertEqual("BLOCKED", blocked.state)
        self.assertEqual(foreign, timeline.markers)
        self.assertIn(("DeleteMarkerAtFrame", 100), timeline.calls)

    def test_readback_mismatch_rolls_back_attempt(self):
        with tempfile.TemporaryDirectory() as raw_root:
            timeline = FakeTimeline(corrupt_add_call=2)
            store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            job = create_job(store, timeline)
            blocked = mark_candidates(timeline, store, job, CONTRACT)

        self.assertEqual("BLOCKED", blocked.state)
        self.assertEqual({}, timeline.markers)

    def test_repeated_marking_verifies_without_duplicate_adds(self):
        with tempfile.TemporaryDirectory() as raw_root:
            timeline = FakeTimeline()
            store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            job = create_job(store, timeline)
            marked = mark_candidates(timeline, store, job, CONTRACT)
            first_add_count = timeline.add_calls
            replay = mark_candidates(timeline, store, marked, CONTRACT)

        self.assertEqual(marked, replay)
        self.assertEqual(first_add_count, timeline.add_calls)

    def test_wrong_timeline_identity_blocks_without_writes(self):
        with tempfile.TemporaryDirectory() as raw_root:
            expected = FakeTimeline(unique_id="expected")
            actual = FakeTimeline(unique_id="different")
            store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            job = create_job(store, expected)
            blocked = mark_candidates(actual, store, job, CONTRACT)

        self.assertEqual("BLOCKED", blocked.state)
        self.assertEqual(0, actual.add_calls)

    def test_cleanup_requires_verified_and_preserves_foreign_markers(self):
        foreign = {10: {"color": "Green", "name": "OPERATORE", "note": "nota",
                        "duration": 1, "customData": "foreign"}}
        with tempfile.TemporaryDirectory() as raw_root:
            timeline = FakeTimeline(markers=foreign)
            store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            marked = mark_candidates(timeline, store, create_job(store, timeline), CONTRACT)
            with self.assertRaisesRegex(ValidationError, "VERIFIED"):
                cleanup_verified_markers(timeline, store, marked)
            reviewed = store.save(replace(marked, state="REVIEWED"), marked.revision)
            cut = store.save(replace(reviewed, state="CUT"), reviewed.revision)
            verified = store.save(replace(cut, state="VERIFIED"), cut.revision)
            closed = cleanup_verified_markers(timeline, store, verified)

        self.assertEqual("CLOSED", closed.state)
        self.assertEqual(foreign, timeline.markers)
        self.assertEqual(2, len(closed.markers))


if __name__ == "__main__":
    unittest.main()
