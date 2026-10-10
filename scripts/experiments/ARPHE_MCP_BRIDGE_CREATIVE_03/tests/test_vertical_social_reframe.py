from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class ReframeRequestTests(unittest.TestCase):
    def test_reframe_requires_explicit_target_range_and_safe_anchor(self):
        from bridge.vertical_social_reframe import validate_reframe_action
        action = {
            "type": "REFRAME", "state": "APPROVED", "reason": "volto relatore",
            "range": {"start_frame": 30, "end_frame": 180},
            "target": {"kind": "person", "label": "relatore"},
            "anchor": {"x": 0.5, "y": 0.42},
        }
        self.assertEqual((30, 180), validate_reframe_action(action, 300)["range"])

    def test_reframe_fails_closed_without_explicit_target(self):
        from bridge.vertical_social_reframe import validate_reframe_action
        with self.assertRaisesRegex(Exception, "target"):
            validate_reframe_action({"type": "REFRAME", "state": "APPROVED",
                                     "range": {"start_frame": 30, "end_frame": 180},
                                     "anchor": {"x": 0.5, "y": 0.42}}, 300)
