from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.carabellese_apply import apply_or_resume_carabellese_cleanup  # noqa: E402
from bridge.carabellese_jobs import CarabelleseJobStore  # noqa: E402
from bridge.carabellese_recovery import (  # noqa: E402
    close_carabellese_cleanup,
    recover_carabellese_cleanup,
)
from bridge.safety import ValidationError  # noqa: E402
from scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_carabellese_apply import (  # noqa: E402
    Resolve,
    setup,
)


class CarabelleseRecoveryTests(unittest.TestCase):
    def test_restart_reads_failed_journal_restores_checkpoint_and_permits_new_attempt(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root); cfg, store, job, project, manager = setup(root, fail_append=2)
            failed = apply_or_resume_carabellese_cleanup(
                Resolve(), manager, cfg, store, job.carabellese_job_id, job.review_fingerprint)
            self.assertTrue(cfg.carabellese_journal_path.is_file())
            restarted_store = CarabelleseJobStore(root / "jobs.json", "PC_PERSONALE")
            project.pool.fail_append = None
            recovered = recover_carabellese_cleanup(
                Resolve(), manager, cfg, restarted_store, failed.carabellese_job_id)
            replay = recover_carabellese_cleanup(
                Resolve(), manager, cfg, restarted_store, failed.carabellese_job_id)
        self.assertEqual("CHECKPOINTED", recovered.state)
        self.assertEqual("resolve:timeline-restored", recovered.timeline_identity)
        self.assertEqual(1, len(project.timelines))
        self.assertEqual("PODCAST_YOUTUBE", project.timeline.GetName())
        self.assertEqual("restore_checkpoint", recovered.operations[-1]["operation"])
        self.assertEqual(recovered, replay)

    def test_changed_timeline_or_checkpoint_blocks_recovery(self):
        for case in ("timeline", "checkpoint"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as raw_root:
                root = Path(raw_root); cfg, store, job, project, manager = setup(root, fail_append=2)
                failed = apply_or_resume_carabellese_cleanup(
                    Resolve(), manager, cfg, store, job.carabellese_job_id, job.review_fingerprint)
                if case == "timeline":
                    project.timeline.tracks["video"][0][0].duration = 299
                else:
                    checkpoint = Path(failed.checkpoint_manifest["path"])
                    checkpoint.write_bytes(b"XXX")
                with self.assertRaises(ValidationError):
                    recover_carabellese_cleanup(Resolve(), manager, cfg, store,
                                                failed.carabellese_job_id)
                self.assertEqual(1, len(project.timelines))

    def test_close_requires_verified_removes_owned_markers_and_retains_checkpoint_metadata(self):
        foreign = {90: {"color": "Green", "name": "OPERATORE", "note": "x",
                        "duration": 1, "customData": "foreign"}}
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root); cfg, store, job, project, manager = setup(root)
            with self.assertRaisesRegex(ValidationError, "VERIFIED"):
                close_carabellese_cleanup(project.timeline, store, job)
            verified = apply_or_resume_carabellese_cleanup(
                Resolve(), manager, cfg, store, job.carabellese_job_id, job.review_fingerprint)
            project.timeline.markers.update(foreign)
            checkpoint_before = dict(verified.checkpoint_manifest)
            closed = close_carabellese_cleanup(project.timeline, store, verified)
        self.assertEqual("CLOSED", closed.state)
        self.assertEqual(checkpoint_before, closed.checkpoint_manifest)
        self.assertEqual(foreign, project.timeline.markers)
        self.assertTrue(closed.operations[-1]["checkpoint_retained"])


if __name__ == "__main__":
    unittest.main()
