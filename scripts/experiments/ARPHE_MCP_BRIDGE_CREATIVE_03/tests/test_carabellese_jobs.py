from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.carabellese_jobs import (  # noqa: E402
    CarabelleseJob,
    CarabelleseJobStore,
    new_carabellese_job,
)
from bridge.safety import ValidationError  # noqa: E402


def job(*, workstation: str = "PC_PERSONALE", timeline: str = "timeline-identity") -> CarabelleseJob:
    return new_carabellese_job(
        workstation_id=workstation,
        workflow_version=1,
        project_name="STUDIO_CARABELLESE",
        timeline_name="PODCAST_YOUTUBE",
        timeline_identity=timeline,
        timeline_fingerprint="0" * 64,
        source_fingerprint="1" * 64,
        transcript_fingerprint="2" * 64,
        contract_fingerprint="3" * 64,
        proposal_fingerprint="4" * 64,
        candidates=({"candidate_id": "C01", "kind": "PAUSE", "start": 10.0, "end": 12.0},),
    )


class CarabelleseJobStoreTests(unittest.TestCase):
    def test_new_job_round_trips_and_persists_all_evidence_slots(self):
        with tempfile.TemporaryDirectory() as raw_root:
            path = Path(raw_root) / "carabellese_jobs.json"
            store = CarabelleseJobStore(path, "PC_PERSONALE")
            created = store.create(job())
            loaded = store.get(created.carabellese_job_id, "PC_PERSONALE")
            persisted = json.loads(path.read_text(encoding="utf-8"))

        self.assertRegex(created.carabellese_job_id, r"^carabellese_[0-9a-f]{16}$")
        self.assertEqual(1, created.revision)
        self.assertEqual(created, loaded)
        self.assertEqual("ANALYZED", loaded.state)
        self.assertEqual("0" * 64, loaded.timeline_fingerprint)
        self.assertEqual("1" * 64, loaded.source_fingerprint)
        self.assertEqual("2" * 64, loaded.transcript_fingerprint)
        self.assertEqual("3" * 64, loaded.contract_fingerprint)
        self.assertEqual("4" * 64, loaded.proposal_fingerprint)
        self.assertIsNone(loaded.review_fingerprint)
        self.assertIsNone(loaded.checkpoint_fingerprint)
        self.assertIsNone(loaded.checkpoint_manifest)
        self.assertEqual([], persisted["jobs"][created.carabellese_job_id]["decisions"])
        self.assertEqual([], persisted["jobs"][created.carabellese_job_id]["markers"])
        self.assertEqual([], persisted["jobs"][created.carabellese_job_id]["operations"])

    def test_normal_lifecycle_accepts_every_edge_and_rejects_skips(self):
        with tempfile.TemporaryDirectory() as raw_root:
            store = CarabelleseJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            current = store.create(job())
            with self.assertRaisesRegex(ValidationError, "[Tt]ransizione"):
                store.save(
                    replace(current, state="REVIEWED", review_fingerprint="5" * 64),
                    current.revision,
                )

            updates = {
                "MARKED": {"markers": ({"candidate_id": "C01", "frame": 300},)},
                "REVIEWED": {
                    "review_fingerprint": "5" * 64,
                    "decisions": ({"candidate_id": "C01", "outcome": "SHORTEN", "reason": "ritmo"},),
                },
                "CHECKPOINTED": {
                    "checkpoint_fingerprint": "6" * 64,
                    "checkpoint_manifest": {"path": "C:/local/checkpoint.drt", "size": 128},
                },
                "APPLYING": {"operations": ({"operation_id": "OP01", "state": "PENDING"},)},
                "VERIFIED": {"operations": ({"operation_id": "OP01", "state": "VERIFIED"},)},
                "CLOSED": {},
            }
            for state, changes in updates.items():
                current = store.save(replace(current, state=state, resume_state=None, **changes), current.revision)
                self.assertEqual(state, current.state)
                self.assertIn(state, current.state_timestamps)

            with self.assertRaisesRegex(ValidationError, "terminale"):
                store.save(replace(current, state="VERIFIED"), current.revision)

    def test_blocked_returns_only_to_recorded_state_and_stale_is_terminal(self):
        with tempfile.TemporaryDirectory() as raw_root:
            store = CarabelleseJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            analyzed = store.create(job())
            blocked = store.save(
                replace(analyzed, state="BLOCKED", resume_state="ANALYZED"), analyzed.revision
            )
            with self.assertRaisesRegex(ValidationError, "resume_state"):
                store.save(replace(blocked, state="MARKED"), blocked.revision)
            resumed = store.save(
                replace(blocked, state="ANALYZED", resume_state=None), blocked.revision
            )
            stale = store.save(replace(resumed, state="STALE"), resumed.revision)
            with self.assertRaisesRegex(ValidationError, "terminale"):
                store.save(replace(stale, state="ANALYZED"), stale.revision)

    def test_failed_recoverable_resumes_only_the_interrupted_apply_stage(self):
        with tempfile.TemporaryDirectory() as raw_root:
            store = CarabelleseJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            current = store.create(job())
            current = store.save(replace(current, state="MARKED"), current.revision)
            current = store.save(
                replace(current, state="REVIEWED", review_fingerprint="5" * 64), current.revision
            )
            current = store.save(
                replace(
                    current,
                    state="CHECKPOINTED",
                    checkpoint_fingerprint="6" * 64,
                    checkpoint_manifest={"path": "C:/local/checkpoint.drt", "size": 128},
                ),
                current.revision,
            )
            applying = store.save(replace(current, state="APPLYING"), current.revision)
            failed = store.save(
                replace(applying, state="FAILED_RECOVERABLE", resume_state="APPLYING"),
                applying.revision,
            )
            with self.assertRaisesRegex(ValidationError, "riprendere"):
                store.save(replace(failed, state="VERIFIED", resume_state=None), failed.revision)
            resumed = store.save(
                replace(failed, state="APPLYING", resume_state=None), failed.revision
            )
            self.assertEqual("APPLYING", resumed.state)

    def test_reviewed_and_checkpointed_states_require_their_evidence(self):
        with tempfile.TemporaryDirectory() as raw_root:
            store = CarabelleseJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            marked = store.create(job())
            marked = store.save(replace(marked, state="MARKED"), marked.revision)
            with self.assertRaisesRegex(ValidationError, "review_fingerprint"):
                store.save(replace(marked, state="REVIEWED"), marked.revision)

            reviewed = store.save(
                replace(marked, state="REVIEWED", review_fingerprint="5" * 64), marked.revision
            )
            with self.assertRaisesRegex(ValidationError, "checkpoint"):
                store.save(replace(reviewed, state="CHECKPOINTED"), reviewed.revision)

    def test_stale_revision_rejects_changed_write_but_create_and_save_replays_are_idempotent(self):
        with tempfile.TemporaryDirectory() as raw_root:
            store = CarabelleseJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            original = job()
            created = store.create(original)
            self.assertEqual(created, store.create(original))
            marked = store.save(replace(created, state="MARKED"), created.revision)
            self.assertEqual(marked, store.save(marked, expected_revision=created.revision))
            with self.assertRaisesRegex(ValidationError, "[Rr]evision"):
                store.save(
                    replace(marked, operations=({"operation_id": "late"},)),
                    expected_revision=created.revision,
                )

    def test_registry_corruption_foreign_workstation_and_podcast_record_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw_root:
            path = Path(raw_root) / "jobs.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(ValidationError):
                CarabelleseJobStore(path, "PC_PERSONALE").active_for_timeline("timeline")

            path.write_text(json.dumps({
                "schema": "ARPHE_CARABELLESE_JOBS_V1",
                "workstation_id": "PC_SEGRETERIA",
                "jobs": {},
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "workstation"):
                CarabelleseJobStore(path, "PC_PERSONALE").active_for_timeline("timeline")

            foreign = job()
            raw_foreign = dict(foreign.__dict__)
            raw_foreign["workflow_id"] = "ARPHE_PODCAST_REELS_CTA"
            path.write_text(json.dumps({
                "schema": "ARPHE_CARABELLESE_JOBS_V1",
                "workstation_id": "PC_PERSONALE",
                "jobs": {foreign.carabellese_job_id: raw_foreign},
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "Workflow"):
                CarabelleseJobStore(path, "PC_PERSONALE").active_for_timeline("timeline")

    def test_get_and_create_reject_cross_workstation_access(self):
        with tempfile.TemporaryDirectory() as raw_root:
            store = CarabelleseJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            created = store.create(job())
            with self.assertRaisesRegex(ValidationError, "workstation"):
                store.get(created.carabellese_job_id, "PC_SEGRETERIA")
            with self.assertRaisesRegex(ValidationError, "workstation"):
                store.create(job(workstation="PC_SEGRETERIA", timeline="other"))

    def test_only_one_active_job_per_timeline_and_terminal_job_releases_it(self):
        with tempfile.TemporaryDirectory() as raw_root:
            store = CarabelleseJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            first = store.create(job())
            self.assertEqual(first.carabellese_job_id,
                             store.active_for_timeline(first.timeline_identity).carabellese_job_id)
            with self.assertRaisesRegex(ValidationError, "attivo"):
                store.create(job())

            first = store.save(replace(first, state="STALE"), first.revision)
            second = store.create(job())
            self.assertNotEqual(first.carabellese_job_id, second.carabellese_job_id)

    def test_immutable_evidence_cannot_be_rebound(self):
        with tempfile.TemporaryDirectory() as raw_root:
            store = CarabelleseJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            created = store.create(job())
            for field in (
                "timeline_fingerprint", "source_fingerprint", "transcript_fingerprint",
                "contract_fingerprint", "proposal_fingerprint", "candidates",
            ):
                changed = ("9" * 64) if field != "candidates" else ({"candidate_id": "OTHER"},)
                with self.subTest(field=field), self.assertRaisesRegex(ValidationError, "immutabile"):
                    store.save(replace(created, **{field: changed}), created.revision)


if __name__ == "__main__":
    unittest.main()
