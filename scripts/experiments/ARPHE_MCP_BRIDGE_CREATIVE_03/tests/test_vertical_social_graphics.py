from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class VerticalSocialGraphicTests(unittest.TestCase):
    def test_empty_plan_produces_no_graphic_or_cta_actions(self):
        from bridge.vertical_social_graphics import approved_graphic_actions
        self.assertEqual((), approved_graphic_actions({"actions": []}, 300))

    def test_graphic_and_cta_are_explicit_and_brand_limited(self):
        from bridge.vertical_social_graphics import approved_graphic_actions
        result = approved_graphic_actions({"actions": [
            {"action_id": "g1", "type": "GRAPHIC", "state": "APPROVED",
             "graphic_kind": "LOWER_THIRD", "text": "Dott.ssa Rossi",
             "style_role": "cream", "range": {"start_frame": 30, "end_frame": 120},
             "reason": "identificazione relatore"},
            {"action_id": "c1", "type": "CTA", "state": "APPROVED",
             "headline": "Prenota una visita", "text": "Contattaci",
             "style_role": "burgundy", "range": {"start_frame": 210, "end_frame": 300},
             "reason": "richiesta esplicita editor"},
        ]}, 300)
        self.assertEqual(("g1", "c1"), tuple(item["action_id"] for item in result))

    def test_unrequested_or_noncanonical_graphic_fails_closed(self):
        from bridge.vertical_social_graphics import approved_graphic_actions
        with self.assertRaisesRegex(Exception, "style_role"):
            approved_graphic_actions({"actions": [{
                "action_id": "g1", "type": "GRAPHIC", "state": "APPROVED",
                "graphic_kind": "LOWER_THIRD", "text": "Titolo", "style_role": "neon",
                "range": {"start_frame": 1, "end_frame": 30}, "reason": "test",
            }]}, 100)

