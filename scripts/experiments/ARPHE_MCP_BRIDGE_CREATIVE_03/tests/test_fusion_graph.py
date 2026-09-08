from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.creative_tools import _merge, _remove_tools_created_after, _text  # noqa: E402
from bridge.fusion_tools import connect_input  # noqa: E402


class FakeOutput:
    pass


class FakeSource:
    def __init__(self):
        self.output = FakeOutput()

    def FindMainOutput(self, _index):
        return self.output


class FakeInput:
    def __init__(self):
        self.connected = None

    def ConnectTo(self, output):
        self.connected = output

    def GetConnectedOutput(self):
        return self.connected


class FakeTarget:
    def __init__(self, names, set_input_result=True, tool_name="ARPHE_TEST"):
        self.inputs = {name: FakeInput() for name in names}
        self.values = {}
        self.set_input_result = set_input_result
        self.deleted = False
        self.tool_name = tool_name

    def FindInput(self, name):
        return self.inputs.get(name)

    def SetInput(self, name, value, *_args):
        self.values[name] = value
        return self.set_input_result

    def GetInput(self, name):
        return self.values.get(name)

    def SetAttrs(self, attrs):
        self.tool_name = attrs.get("TOOLS_Name", self.tool_name)
        return True

    def GetAttrs(self):
        return {"TOOLS_Name": self.tool_name}

    def Delete(self):
        self.deleted = True


class FakeComp:
    def __init__(self):
        self.merge = FakeTarget(("Background", "Foreground"))

    def AddTool(self, reg_id, _x, _y):
        return self.merge if reg_id == "Merge" else None


class FakeTextComp:
    def __init__(self, set_input_result=True):
        self.text = FakeTarget((), set_input_result=set_input_result)

    def AddTool(self, reg_id, _x, _y):
        return self.text if reg_id == "TextPlus" else None


class FusionGraphTests(unittest.TestCase):
    def test_named_socket_connection_is_verified(self):
        source = FakeSource()
        target = FakeTarget(("Foreground",))
        self.assertTrue(connect_input(target, "Foreground", source))
        self.assertIs(source.output, target.inputs["Foreground"].connected)

    def test_missing_named_socket_does_not_report_success(self):
        self.assertFalse(connect_input(FakeTarget(()), "Foreground", FakeSource()))

    def test_merge_connects_both_sources(self):
        comp = FakeComp()
        background = FakeSource()
        foreground = FakeSource()
        merge = _merge(comp, background, foreground, "ARPHE_TEST_MERGE")
        self.assertIs(background.output, merge.inputs["Background"].connected)
        self.assertIs(foreground.output, merge.inputs["Foreground"].connected)

    def test_review_text_uses_verified_frame_layout(self):
        comp = FakeTextComp()
        _text(comp, "ARPHE_REVIEW_TEXT", "Testo fittizio", 0.036,
              {"r": 0.2, "g": 0.1, "b": 0.1, "a": 1.0}, 0.49,
              layout_type=1.0, frame_width=0.66, frame_height=0.17)
        self.assertEqual(1.0, comp.text.values["LayoutType"])
        self.assertEqual(0.66, comp.text.values["LayoutWidth"])
        self.assertEqual(0.17, comp.text.values["LayoutHeight"])
        self.assertNotIn("Width", comp.text.values)
        self.assertNotIn("Height", comp.text.values)
        self.assertEqual("Open Sans", comp.text.values["Font"])

    def test_star_text_uses_symbol_font(self):
        comp = FakeTextComp()
        _text(comp, "ARPHE_STARS", "★ ★ ★ ★ ★", 0.035,
              {"r": 0.4, "g": 0.1, "b": 0.2, "a": 1.0}, 0.62,
              font="Segoe UI Symbol", style="Regular")
        self.assertEqual("Segoe UI Symbol", comp.text.values["Font"])
        self.assertEqual("★ ★ ★ ★ ★", comp.text.values["StyledText"])

    def test_text_accepts_fusion_none_return_when_readback_matches(self):
        comp = FakeTextComp(set_input_result=None)
        _text(comp, "ARPHE_TEXT_NONE_RETURN", "Testo fittizio", 0.036,
              {"r": 0.2, "g": 0.1, "b": 0.1, "a": 1.0}, 0.49)
        self.assertEqual("Testo fittizio", comp.text.values["StyledText"])

    def test_cleanup_only_removes_tools_created_after_snapshot(self):
        original = FakeTarget((), tool_name="ARPHE_ORIGINAL")
        created = FakeTarget((), tool_name="ARPHE_CREATED")
        media_out = FakeTarget((), tool_name="MediaOut1")
        comp = type("CleanupComp", (), {"GetToolList": lambda self: {
            1: original, 2: created, 3: media_out}})()
        removed = _remove_tools_created_after(comp, {"ARPHE_ORIGINAL"})
        self.assertEqual(1, removed)
        self.assertFalse(original.deleted)
        self.assertTrue(created.deleted)
        self.assertFalse(media_out.deleted)


if __name__ == "__main__":
    unittest.main()
