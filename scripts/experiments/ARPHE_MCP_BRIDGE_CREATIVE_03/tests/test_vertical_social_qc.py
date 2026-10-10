from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class VerticalSocialQcTests(unittest.TestCase):
    def test_verified_plan_with_matching_vertical_format_is_review_ready(self):
        from bridge.vertical_social_qc import final_vertical_social_check
        result = final_vertical_social_check({
            "target": {"width": 1080, "height": 1920, "fps": "30", "playback_fps": "30"},
            "actions": [{"action_id": "cut", "type": "CUT", "state": "VERIFIED"}],
        }, picture_locked=False)
        self.assertTrue(result["ready_for_human_review"])
        self.assertTrue(result["ready_for_delivery"])

    def test_qc_reports_fps_inflight_blocked_and_caption_lock_separately(self):
        from bridge.vertical_social_qc import final_vertical_social_check
        result = final_vertical_social_check({
            "target": {"width": 1080, "height": 1920, "fps": "30", "playback_fps": "24"},
            "actions": [
                {"action_id": "g", "type": "GRAPHIC", "state": "APPROVED"},
                {"action_id": "b", "type": "B_ROLL_GENERATED", "state": "BLOCKED"},
                {"action_id": "c", "type": "CAPTIONS", "state": "APPROVED"},
            ],
        }, picture_locked=False)
        self.assertFalse(result["ready_for_human_review"])
        self.assertFalse(result["ready_for_delivery"])
        self.assertIn("playback_fps_mismatch", result["issues"])
        self.assertIn("caption_before_picture_lock", result["issues"])
        self.assertEqual(["b"], result["blocked_actions"])

