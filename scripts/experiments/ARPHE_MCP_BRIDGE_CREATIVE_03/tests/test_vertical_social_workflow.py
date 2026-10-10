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

    def test_picture_lock_blocks_caption_until_locked_and_resume_is_local(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as raw_root:
            path = Path(raw_root) / "plans.json"
            prepared = module.prepare_vertical_social_plan(
                path, "PC_PERSONALE", {"project": "ARPHE", "timeline": "ADV_V1", "fps": "30",
                                       "total_frames": 60, "locked_edit_fingerprint": "a" * 64},
                [
                    {"action_id": "cut-1", "type": "CUT", "phase": "PROVISIONAL_EDIT"},
                    {"action_id": "caption-1", "type": "CAPTIONS", "phase": "POST_LOCK",
                     "state": "APPROVED", "locked_edit_fingerprint": "a" * 64,
                     "reason": "caption approvate", "cues": [
                         {"cue_id": "c1", "start_frame": 0, "end_frame": 30,
                          "text": "Testo", "position": "LOWER"}]},
                ],
            )
            approved = module.approve_vertical_social_plan(path, "PC_PERSONALE", prepared.plan_id, prepared.fingerprint)
            with self.assertRaisesRegex(Exception, "picture lock"):
                module.advance_vertical_social_action(path, "PC_PERSONALE", approved.plan_id, "caption-1", "APPLIED", {})
            locked = module.mark_vertical_social_picture_lock(
                path, "PC_PERSONALE", approved.plan_id, "a" * 64)
            with self.assertRaisesRegex(Exception, "esecutore dedicato"):
                module.advance_vertical_social_action(path, "PC_PERSONALE", locked.plan_id, "caption-1", "APPLIED", {})
            blocked = module.advance_vertical_social_action(
                path, "PC_PERSONALE", locked.plan_id, "cut-1", "BLOCKED", {"reason": "edit decision"}
            )
            self.assertEqual("cut-1", module.inspect_vertical_social_plan(path, "PC_PERSONALE", blocked.plan_id)["next_action"])

    def test_picture_lock_records_exact_edit_fingerprint_for_pending_captions(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as raw_root:
            path = Path(raw_root) / "plans.json"
            prepared = module.prepare_vertical_social_plan(
                path, "PC_PERSONALE",
                {"project": "ARPHE", "timeline": "ADV_V1", "fps": "30", "total_frames": 60},
                [{"action_id": "caption-1", "type": "CAPTIONS", "phase": "POST_LOCK",
                  "state": "APPROVED", "locked_edit_fingerprint": "AT_PICTURE_LOCK",
                  "reason": "caption approvate", "cues": [
                      {"cue_id": "c1", "start_frame": 0, "end_frame": 30,
                       "text": "Testo", "position": "LOWER"}]}],
            )
            module.approve_vertical_social_plan(
                path, "PC_PERSONALE", prepared.plan_id, prepared.fingerprint)
            locked = module.mark_vertical_social_picture_lock(
                path, "PC_PERSONALE", prepared.plan_id, "b" * 64)
            inspected = module.inspect_vertical_social_plan(
                path, "PC_PERSONALE", locked.plan_id)
            self.assertTrue(inspected["picture_locked"])
            self.assertEqual("b" * 64, inspected["locked_edit_fingerprint"])

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
                path, "PC_PERSONALE", {"project": "ARPHE", "timeline": "ADV_V1", "fps": "30",
                                           "total_frames": 60},
                [
                    {"action_id": "cut-1", "type": "CUT", "phase": "PROVISIONAL_EDIT"},
                    {"action_id": "broll-1", "type": "B_ROLL_PROVIDED", "phase": "PROVISIONAL_EDIT",
                     "state": "APPROVED", "asset_path": "C:/ARPHE/assets/broll.mov",
                     "timeline_range": {"start_frame": 20, "end_frame": 40},
                     "source_range": {"start_frame": 0, "end_frame": 20},
                     "reason": "copertura richiesta"},
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

    def test_prepare_validates_provided_broll_and_blocks_generated_broll(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as raw_root:
            path = Path(raw_root) / "plans.json"
            target = {"project": "ARPHE", "timeline": "ADV_V1", "fps": "30",
                      "total_frames": 300}
            prepared = module.prepare_vertical_social_plan(path, "PC_PERSONALE", target, [{
                "action_id": "broll-1", "type": "B_ROLL_PROVIDED", "phase": "PROVISIONAL_EDIT",
                "state": "APPROVED", "asset_path": "C:/ARPHE/assets/broll.mov",
                "timeline_range": {"start_frame": 30, "end_frame": 90},
                "source_range": {"start_frame": 0, "end_frame": 60},
                "reason": "copertura richiesta",
            }])
            self.assertEqual("PROPOSED", prepared.state)
            with self.assertRaisesRegex(Exception, "generato bloccato"):
                module.prepare_vertical_social_plan(path, "PC_PERSONALE", target, [{
                    "action_id": "gen-1", "type": "B_ROLL_GENERATED",
                    "phase": "PROVISIONAL_EDIT", "state": "APPROVED",
                }])

    def test_prepare_validates_optional_graphics_only_when_requested(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as raw_root:
            path = Path(raw_root) / "plans.json"
            target = {"project": "ARPHE", "timeline": "ADV_V1", "fps": "30",
                      "total_frames": 300}
            prepared = module.prepare_vertical_social_plan(path, "PC_PERSONALE", target, [])
            self.assertEqual("PROPOSED", prepared.state)
            with self.assertRaisesRegex(Exception, "style_role"):
                module.prepare_vertical_social_plan(path, "PC_PERSONALE", target, [{
                    "action_id": "g1", "type": "GRAPHIC", "phase": "PROVISIONAL_EDIT",
                    "state": "APPROVED", "graphic_kind": "TITLE", "text": "Titolo",
                    "style_role": "neon", "range": {"start_frame": 1, "end_frame": 30},
                    "reason": "richiesta editor",
                }])

    def test_generic_execution_evidence_updates_only_the_named_action(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as raw_root:
            path = Path(raw_root) / "plans.json"
            target = {"project": "ARPHE", "timeline": "ADV_V1", "fps": "30",
                      "total_frames": 100}
            prepared = module.prepare_vertical_social_plan(path, "PC_PERSONALE", target, [{
                "action_id": "r1", "type": "REFRAME", "phase": "PROVISIONAL_EDIT",
                "state": "APPROVED", "range": {"start_frame": 0, "end_frame": 100},
                "target": {"kind": "person", "label": "speaker"},
                "anchor": {"x": 0.5, "y": 0.5}, "reason": "volto",
            }])
            module.approve_vertical_social_plan(path, "PC_PERSONALE", prepared.plan_id,
                                                prepared.fingerprint)
            final = module.record_vertical_social_action_execution(
                path, "PC_PERSONALE", prepared.plan_id, prepared.fingerprint,
                "r1", "REFRAME", {"timeline": "__ARPHE_VERTICAL_VERTICAL_123"})
            self.assertEqual("VERIFIED", final.action("r1").state)

    def test_inspection_includes_compact_final_check(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as raw_root:
            path = Path(raw_root) / "plans.json"
            prepared = module.prepare_vertical_social_plan(
                path, "PC_PERSONALE",
                {"project": "ARPHE", "timeline": "ADV", "width": 1080, "height": 1920,
                 "fps": "30", "playback_fps": "30"},
                [{"action_id": "cut", "type": "CUT", "phase": "PROVISIONAL_EDIT"}],
            )
            inspected = module.inspect_vertical_social_plan(path, "PC_PERSONALE", prepared.plan_id)
            self.assertIn("final_check", inspected)
            self.assertFalse(inspected["final_check"]["ready_for_human_review"])

    def test_generic_advance_cannot_forge_graphic_execution(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as raw_root:
            path = Path(raw_root) / "plans.json"
            prepared = module.prepare_vertical_social_plan(
                path, "PC_PERSONALE",
                {"project": "ARPHE", "timeline": "ADV", "fps": "30", "total_frames": 60},
                [{"action_id": "g", "type": "GRAPHIC", "phase": "PROVISIONAL_EDIT",
                  "state": "APPROVED", "graphic_kind": "TITLE", "text": "Titolo",
                  "style_role": "cream", "range": {"start_frame": 0, "end_frame": 30},
                  "reason": "richiesta editor"}],
            )
            module.approve_vertical_social_plan(path, "PC_PERSONALE", prepared.plan_id,
                                                prepared.fingerprint)
            with self.assertRaisesRegex(Exception, "esecutore dedicato"):
                module.advance_vertical_social_action(
                    path, "PC_PERSONALE", prepared.plan_id, "g", "APPLIED", {"claimed": True})

    def test_prepare_validates_music_duck_against_exact_target_duration(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as raw_root:
            with self.assertRaisesRegex(Exception, "gain_db"):
                module.prepare_vertical_social_plan(
                    Path(raw_root) / "plans.json", "PC_PERSONALE",
                    {"project": "ARPHE", "timeline": "ADV", "fps": "30", "total_frames": 60},
                    [{"action_id": "m", "type": "MUSIC_DUCK", "phase": "PROVISIONAL_EDIT",
                      "state": "APPROVED", "range": {"start_frame": 0, "end_frame": 60},
                      "audio_track": 2, "gain_db": -80, "reason": "voce"}],
                )
            

if __name__ == "__main__":
    unittest.main()
