from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class VerticalSocialWorkflowTests(unittest.TestCase):
    def _module(self):
        self.assertIsNotNone(
            importlib.util.find_spec("bridge.vertical_social_workflow"),
            "bridge.vertical_social_workflow must exist",
        )
        return importlib.import_module("bridge.vertical_social_workflow")

    def test_approval_binds_to_exact_fingerprint_and_card_is_compact(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as raw_root:
            prepared = module.prepare_vertical_social_plan(
                Path(raw_root) / "plans.json", "PC_PERSONALE",
                {"project": "ARPHE", "timeline": "ADV_V1", "fps": "30"},
                [{"action_id": "cut-1", "type": "CUT", "phase": "PROVISIONAL_EDIT"}],
            )
            card = module.compact_vertical_social_card(prepared)
            self.assertEqual(1, card["card_count"])
            self.assertEqual("PROPOSED", card["state"])
            with self.assertRaisesRegex(Exception, "fingerprint"):
                module.approve_vertical_social_plan(
                    Path(raw_root) / "plans.json", "PC_PERSONALE", prepared.plan_id, "wrong"
                )
            approved = module.approve_vertical_social_plan(
                Path(raw_root) / "plans.json", "PC_PERSONALE", prepared.plan_id, prepared.fingerprint
            )
            self.assertEqual("APPROVED", approved.state)

    def test_picture_lock_blocks_caption_without_validated_capability_and_resume_is_local(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as raw_root:
            path = Path(raw_root) / "plans.json"
            prepared = module.prepare_vertical_social_plan(
                path, "PC_PERSONALE", {"project": "ARPHE", "timeline": "ADV_V1", "fps": "30"},
                [
                    {"action_id": "cut-1", "type": "CUT", "phase": "PROVISIONAL_EDIT"},
                    {"action_id": "caption-1", "type": "CAPTIONS", "phase": "POST_LOCK"},
                ],
            )
            approved = module.approve_vertical_social_plan(path, "PC_PERSONALE", prepared.plan_id, prepared.fingerprint)
            with self.assertRaisesRegex(Exception, "picture lock"):
                module.advance_vertical_social_action(path, "PC_PERSONALE", approved.plan_id, "caption-1", "APPLIED", {})
            locked = module.mark_vertical_social_picture_lock(path, "PC_PERSONALE", approved.plan_id)
            with self.assertRaisesRegex(Exception, "non validata"):
                module.advance_vertical_social_action(path, "PC_PERSONALE", locked.plan_id, "caption-1", "APPLIED", {})
            blocked = module.advance_vertical_social_action(
                path, "PC_PERSONALE", locked.plan_id, "cut-1", "BLOCKED", {"reason": "edit decision"}
            )
            self.assertEqual("cut-1", module.inspect_vertical_social_plan(path, "PC_PERSONALE", blocked.plan_id)["next_action"])

    def test_execution_lookup_requires_exact_approved_fingerprint(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as raw_root:
            path = Path(raw_root) / "plans.json"
            prepared = module.prepare_vertical_social_plan(
                path, "PC_PERSONALE", {"project": "ARPHE", "timeline": "ADV_V1", "fps": "30"},
                [{"action_id": "cut-1", "type": "CUT", "phase": "PROVISIONAL_EDIT",
                  "range": {"start_frame": 12, "end_frame": 24}, "reason": "pausa"}],
            )
            with self.assertRaisesRegex(Exception, "approvato"):
                module.approved_vertical_social_plan(path, "PC_PERSONALE", prepared.plan_id, prepared.fingerprint)
            module.approve_vertical_social_plan(path, "PC_PERSONALE", prepared.plan_id, prepared.fingerprint)
            plan = module.approved_vertical_social_plan(path, "PC_PERSONALE", prepared.plan_id, prepared.fingerprint)
            self.assertEqual("cut-1", plan.action("cut-1").action_id)

    def test_cut_execution_marks_only_approved_cuts_with_provisional_evidence(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as raw_root:
            path = Path(raw_root) / "plans.json"
            prepared = module.prepare_vertical_social_plan(
                path, "PC_PERSONALE", {"project": "ARPHE", "timeline": "ADV_V1", "fps": "30"},
                [
                    {"action_id": "cut-1", "type": "CUT", "phase": "PROVISIONAL_EDIT"},
                    {"action_id": "broll-1", "type": "B_ROLL", "phase": "PROVISIONAL_EDIT"},
                ],
            )
            module.approve_vertical_social_plan(path, "PC_PERSONALE", prepared.plan_id, prepared.fingerprint)
            final = module.record_vertical_social_cut_execution(
                path, "PC_PERSONALE", prepared.plan_id, prepared.fingerprint,
                "__ARPHE_VERTICAL_VERTICAL_123", 60,
            )
            self.assertEqual("VERIFIED", final.action("cut-1").state)
            self.assertEqual("APPROVED", final.action("broll-1").state)
            self.assertEqual("__ARPHE_VERTICAL_VERTICAL_123", final.action("cut-1").evidence["provisional_timeline"])
            

if __name__ == "__main__":
    unittest.main()
