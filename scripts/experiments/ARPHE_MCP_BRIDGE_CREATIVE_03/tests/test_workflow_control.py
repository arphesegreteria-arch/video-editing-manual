from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.control_plane import new_workflow_job  # noqa: E402
from bridge.workflow_control import native_binding, workflow_job_card  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402


class WorkflowControlTests(unittest.TestCase):
    def setUp(self):
        self.job = new_workflow_job("PC_PERSONALE", "PODCAST_REELS", "editorial_0123456789abcdef",
                                    {"project_name": "ARPHE", "timeline_name": "MASTER"}, "a" * 64)

    def test_podcast_marked_maps_to_review_ready_with_submit_review_action(self):
        native = SimpleNamespace(workstation_id="PC_PERSONALE", state="MARKED", project_name="ARPHE",
                                 timeline_name="MASTER", candidate_fingerprint="b" * 64)
        card = workflow_job_card(self.job, native)
        self.assertEqual("REVIEW_READY", card["state"])
        self.assertEqual("SUBMIT_REVIEW", card["next_safe_action"])

    def test_foreign_workstation_or_changed_target_is_rejected(self):
        foreign = SimpleNamespace(workstation_id="PC_SEGRETERIA", state="MARKED", project_name="ARPHE",
                                  timeline_name="MASTER", candidate_fingerprint="b" * 64)
        with self.assertRaisesRegex(ValidationError, "workstation"):
            native_binding(self.job, foreign)
        changed = SimpleNamespace(workstation_id="PC_PERSONALE", state="MARKED", project_name="ARPHE",
                                  timeline_name="OTHER", candidate_fingerprint="b" * 64)
        with self.assertRaisesRegex(ValidationError, "target"):
            native_binding(self.job, changed)

    def test_no_verified_delivery_never_fabricates_delivery_action(self):
        native = SimpleNamespace(workstation_id="PC_PERSONALE", state="VERIFIED", project_name="ARPHE",
                                 timeline_name="MASTER", candidate_fingerprint="b" * 64)
        card = workflow_job_card(self.job, native)
        self.assertEqual("REVIEW_READY", card["state"])
        self.assertEqual("NONE", card["next_safe_action"])


if __name__ == "__main__":
    unittest.main()
