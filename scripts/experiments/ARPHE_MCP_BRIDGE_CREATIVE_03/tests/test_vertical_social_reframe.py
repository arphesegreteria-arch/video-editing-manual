from pathlib import Path
import sys
import unittest
from unittest.mock import patch

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

    def test_reframe_plan_uses_safe_anchor_and_no_implicit_zoom(self):
        from bridge.vertical_social_reframe import reframe_transform_plan
        plan = reframe_transform_plan({"anchor": {"x": 0.72, "y": 0.42}}, 1080, 1920)
        self.assertEqual({"x": 0.72, "y": 0.42}, plan["center"])
        self.assertEqual(1.0, plan["zoom"])

    def test_transform_parameters_are_applied_and_read_back(self):
        from bridge.vertical_social_reframe import apply_transform_parameters
        class Tool:
            def __init__(self): self.values = {}
            def SetInput(self, name, value): self.values[name] = value
            def GetInput(self, name): return self.values.get(name)
        tool = Tool()
        self.assertTrue(apply_transform_parameters(tool, {"center": {"x": .6, "y": .4}, "zoom": 1.0}))
        self.assertEqual({1: .6, 2: .4, 3: 0.0}, tool.GetInput("Center"))

    def test_fusion_adapter_connects_media_transform_and_output(self):
        from bridge.vertical_social_reframe import apply_fusion_reframe

        class Tool:
            def __init__(self, reg_id=None): self.reg_id, self.values = reg_id, {}
            def GetAttrs(self): return {"TOOLS_RegID": self.reg_id}
            def SetInput(self, name, value): self.values[name] = value
            def GetInput(self, name): return self.values.get(name)

        class Comp:
            def __init__(self, media): self.media = media
            def GetToolList(self, selected): return {1: self.media}

        media, output, transform = Tool("MediaIn"), Tool("MediaOut"), Tool("Transform")
        comp = Comp(media)
        item = type("Item", (), {"AddFusionComp": lambda self: comp})()
        with patch("bridge.vertical_social_reframe._media_out", return_value=output), \
                patch("bridge.vertical_social_reframe._new_tool", return_value=transform), \
                patch("bridge.vertical_social_reframe.connect_input", return_value=True) as connected:
            self.assertTrue(apply_fusion_reframe(item, {"center": {"x": .5, "y": .42}, "zoom": 1.0}))
        self.assertEqual(2, connected.call_count)
