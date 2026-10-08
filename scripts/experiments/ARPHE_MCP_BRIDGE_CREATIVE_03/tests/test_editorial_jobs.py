from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.config import load_config  # noqa: E402
from bridge.editorial_jobs import (  # noqa: E402
    EditorialJob,
    EditorialJobStore,
    new_editorial_job,
)
from bridge.safety import ValidationError  # noqa: E402


def job(*, workstation: str = "PC_PERSONALE", timeline: str = "timeline-fingerprint") -> EditorialJob:
    return new_editorial_job(
        workstation_id=workstation,
        workflow_version=1,
        project_name="ARPHE_TEST_PROJECT",
        timeline_name="ARPHE_SOURCE",
        timeline_identity=timeline,
        source_fingerprint="a" * 64,
        transcript_fingerprint="b" * 64,
        candidate_fingerprint="c" * 64,
        candidates=({"candidate_id": "R01", "source_in_frame": 0,
                     "source_out_frame_exclusive": 100},),
    )


class EditorialJobStoreTests(unittest.TestCase):
    def test_new_job_round_trips_with_random_valid_id_and_revision(self):
        with tempfile.TemporaryDirectory() as raw_root:
            store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            created = store.create(job())
            loaded = store.get(created.editorial_job_id, "PC_PERSONALE")

        self.assertRegex(created.editorial_job_id, r"^editorial_[0-9a-f]{16}$")
        self.assertEqual(1, created.revision)
        self.assertEqual(created, loaded)
        self.assertEqual("ANALYZED", loaded.state)
        self.assertIn("ANALYZED", loaded.state_timestamps)

    def test_normal_lifecycle_accepts_each_transition_and_rejects_skips(self):
        with tempfile.TemporaryDirectory() as raw_root:
            store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            current = store.create(job())
            with self.assertRaisesRegex(ValidationError, "[Tt]ransizione"):
                store.save(replace(current, state="REVIEWED"), current.revision)

            for state in ("MARKED", "REVIEWED", "CUT", "VERIFIED", "CLOSED"):
                markers = current.markers
                if state == "MARKED":
                    markers = ({"name": "ARPHE_R01_IN", "frame": 0},
                               {"name": "ARPHE_R01_OUT", "frame": 100})
                current = store.save(
                    replace(current, state=state, markers=markers, resume_state=None),
                    current.revision,
                )
                self.assertEqual(state, current.state)
                self.assertIn(state, current.state_timestamps)

    def test_blocked_job_returns_only_to_recorded_resume_state(self):
        with tempfile.TemporaryDirectory() as raw_root:
            store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            analyzed = store.create(job())
            blocked = store.save(replace(analyzed, state="BLOCKED", resume_state="ANALYZED"),
                                 analyzed.revision)
            with self.assertRaisesRegex(ValidationError, "resume_state"):
                store.save(replace(blocked, state="MARKED"), blocked.revision)
            resumed = store.save(replace(blocked, state="ANALYZED", resume_state=None), blocked.revision)
            self.assertEqual("ANALYZED", resumed.state)

    def test_failed_recoverable_can_repeat_or_finish_cut_but_stale_is_terminal(self):
        with tempfile.TemporaryDirectory() as raw_root:
            store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            reviewed = store.create(job())
            reviewed = store.save(replace(reviewed, state="MARKED", markers=({"name": "m", "frame": 1},)),
                                  reviewed.revision)
            reviewed = store.save(replace(reviewed, state="REVIEWED"), reviewed.revision)
            failed = store.save(replace(reviewed, state="FAILED_RECOVERABLE", resume_state="REVIEWED"),
                                reviewed.revision)
            again = store.save(replace(failed, state="FAILED_RECOVERABLE"), failed.revision)
            cut = store.save(replace(again, state="CUT", resume_state=None), again.revision)
            stale = store.save(replace(cut, state="STALE", resume_state=None), cut.revision)
            with self.assertRaisesRegex(ValidationError, "terminale"):
                store.save(replace(stale, state="CUT"), stale.revision)

    def test_stale_revision_rejects_changed_write_but_exact_replay_is_idempotent(self):
        with tempfile.TemporaryDirectory() as raw_root:
            store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            created = store.create(job())
            marked = store.save(replace(created, state="MARKED", markers=({"name": "m", "frame": 1},)),
                                created.revision)
            replay = store.save(marked, expected_revision=created.revision)
            self.assertEqual(marked, replay)
            with self.assertRaisesRegex(ValidationError, "[Rr]evision"):
                store.save(replace(marked, operations=({"candidate_id": "R01"},)),
                           expected_revision=created.revision)

    def test_corrupt_registry_and_foreign_workstation_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw_root:
            path = Path(raw_root) / "jobs.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(ValidationError):
                EditorialJobStore(path, "PC_PERSONALE").active_for_timeline("timeline")

            path.write_text(json.dumps({
                "schema": "ARPHE_EDITORIAL_JOBS_V1",
                "workstation_id": "PC_SEGRETERIA",
                "jobs": {},
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "workstation"):
                EditorialJobStore(path, "PC_PERSONALE").active_for_timeline("timeline")

    def test_get_rejects_foreign_caller_even_when_job_id_exists(self):
        with tempfile.TemporaryDirectory() as raw_root:
            store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            created = store.create(job())
            with self.assertRaisesRegex(ValidationError, "workstation"):
                store.get(created.editorial_job_id, "PC_SEGRETERIA")

    def test_only_one_nonclosed_job_may_own_markers_on_a_timeline(self):
        with tempfile.TemporaryDirectory() as raw_root:
            store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            first = store.create(job())
            first = store.save(replace(first, state="MARKED", markers=({"name": "m", "frame": 1},)),
                               first.revision)
            self.assertEqual(first.editorial_job_id,
                             store.active_for_timeline(first.timeline_identity).editorial_job_id)

            second = store.create(job())
            with self.assertRaisesRegex(ValidationError, "marker"):
                store.save(replace(second, state="MARKED", markers=({"name": "n", "frame": 2},)),
                           second.revision)

            for state in ("REVIEWED", "CUT", "VERIFIED", "CLOSED"):
                first = store.save(replace(first, state=state), first.revision)
            marked_second = store.save(
                replace(second, state="MARKED", markers=({"name": "n", "frame": 2},)),
                second.revision,
            )
            self.assertEqual(second.editorial_job_id, marked_second.editorial_job_id)


class EditorialJobConfigTests(unittest.TestCase):
    def test_default_editorial_paths_are_workstation_local_beside_state(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            config_path = root / "creative_config.json"
            config_path.write_text(json.dumps({
                "runtime_id": "ARPHE_MCP_BRIDGE_CREATIVE_03",
                "workstation_id": "PC_PERSONALE",
                "state_path": str(root / "state" / "creative_state.json"),
                "feature_flags": {},
            }), encoding="utf-8")
            config = load_config(config_path)

        expected = (root / "state").resolve()
        self.assertEqual(expected / "editorial_jobs.json", config.editorial_jobs_path)
        self.assertEqual(expected / "editorial_journal.jsonl", config.editorial_journal_path)
        self.assertEqual(expected / "editorial_profile_overlay.json", config.editorial_profile_overlay_path)
        self.assertEqual(expected / "editorial_profile_proposals.json", config.editorial_profile_proposals_path)


if __name__ == "__main__":
    unittest.main()
