from __future__ import annotations

import json
import ast
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.config import DEFAULT_FLAGS, load_config  # noqa: E402
from bridge.motion_presets import motion_plan, stack_plan  # noqa: E402
from bridge.safety import (ValidationError, allowed_asset, arphe_name,
                           ensure_no_collision, validate_color_role,
                           validate_frame_range, validate_preset,
                           validate_review, validate_timeline_settings)  # noqa: E402
from bridge.tool_catalog import EXPOSED_TOOL_NAMES, FORBIDDEN_GENERIC_TOOLS  # noqa: E402


class SafetyTests(unittest.TestCase):
    def test_name_is_sanitized_and_prefixed(self):
        self.assertEqual("ARPHE_Mia_Creative", arphe_name("  Mia Creative!! ", "FALLBACK"))
        self.assertTrue(arphe_name("x" * 200, "FALLBACK").startswith("ARPHE_"))
        self.assertLessEqual(len(arphe_name("x" * 200, "FALLBACK")), 64)

    def test_collision_rejects_overwrite_case_insensitively(self):
        with self.assertRaisesRegex(ValidationError, "overwrite vietato"):
            ensure_no_collision("ARPHE_TEST", ["arphe_test"], "Timeline")

    def test_timeline_settings_allow_vertical_30(self):
        self.assertEqual((1080, 1920, 30.0), validate_timeline_settings(1080, 1920, 30))
        for invalid in ((720, 1280, 30), (1080, 1920, 29.97), (True, 1920, 30), (1080.5, 1920, 30)):
            with self.assertRaises(ValidationError):
                validate_timeline_settings(*invalid)

    def test_frame_ranges_are_bounded(self):
        self.assertEqual((0, 540), validate_frame_range(0, 540))
        for invalid in ((-1, 10), (10, 10), (20, 10), (0, 20_000), (0.0, 10)):
            with self.assertRaises(ValidationError):
                validate_frame_range(*invalid)

    def test_review_limits_and_stars(self):
        validate_review("Testo fittizio", 5, "fittizio", "Etichetta")
        for stars in (0, 6, True, 4.5):
            with self.assertRaises(ValidationError):
                validate_review("Testo", stars, None, None)
        with self.assertRaises(ValidationError):
            validate_review("x" * 801, 5, None, None)
        with self.assertRaises(ValidationError):
            validate_review("Testo", 5, "assente", None)

    def test_preset_and_color_role_allowlists(self):
        self.assertEqual("ARPHE_SOFT_DROP", validate_preset("ARPHE_SOFT_DROP"))
        self.assertEqual("burgundy", validate_color_role("burgundy"))
        with self.assertRaises(ValidationError): validate_preset("BOUNCE_ANY")
        with self.assertRaises(ValidationError): validate_color_role("#ff00ff")

    def test_filesystem_allowlist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allowed = root / "assets"
            allowed.mkdir()
            image = allowed / "logo.png"
            image.write_bytes(b"fake")
            outside = root / "outside.png"
            outside.write_bytes(b"fake")
            self.assertEqual(image.resolve(), allowed_asset(str(image), allowed, "image"))
            with self.assertRaises(ValidationError): allowed_asset(str(outside), allowed, "image")
            with self.assertRaises(ValidationError): allowed_asset(str(image), allowed, "video")

    def test_no_dangerous_generic_tools(self):
        self.assertTrue(FORBIDDEN_GENERIC_TOOLS.isdisjoint(EXPOSED_TOOL_NAMES))

    def test_catalog_matches_mcp_decorated_functions(self):
        tree = ast.parse((ROOT / "bridge" / "server.py").read_text(encoding="utf-8"))
        decorated = {
            node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute)
                    and isinstance(item.func.value, ast.Name) and item.func.value.id == "mcp"
                    and item.func.attr == "tool" for item in node.decorator_list)
        }
        self.assertEqual(set(EXPOSED_TOOL_NAMES), decorated)

    def test_default_flags_gate_advanced_writes(self):
        self.assertTrue(DEFAULT_FLAGS["CAP_PROJECT"])
        self.assertTrue(DEFAULT_FLAGS["CAP_TIMELINE"])
        for name in ("CAP_FUSION", "CAP_REVIEW", "CAP_MOTION", "CAP_ASSETS", "CAP_RENDER"):
            self.assertFalse(DEFAULT_FLAGS[name])

    def test_malformed_config_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"runtime_id": "WRONG", "workstation_id": "PC_SEGRETERIA"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "runtime_id"):
                load_config(path)

    def test_config_rejects_unallowlisted_render_codec(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({
                "runtime_id": "ARPHE_MCP_BRIDGE_CREATIVE_03",
                "workstation_id": "PC_SEGRETERIA",
                "render_format": "mov",
                "render_codec": "Anything",
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "render_format/render_codec"):
                load_config(path)

    def test_config_rejects_non_boolean_feature_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({
                "runtime_id": "ARPHE_MCP_BRIDGE_CREATIVE_03",
                "workstation_id": "PC_SEGRETERIA",
                "feature_flags": {"CAP_RENDER": "false"},
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "true o false"):
                load_config(path)


class MotionTests(unittest.TestCase):
    def test_soft_drop_has_settle_without_aggressive_bounce(self):
        plan = motion_plan("ARPHE_SOFT_DROP", 0, 18)
        self.assertEqual(3, len(plan["keys"]))
        self.assertLessEqual(abs(plan["keys"][1]["scale"] - 1.0), 0.02)
        self.assertEqual(1.0, plan["keys"][-1]["scale"])

    def test_paper_stack_preserves_order_and_stagger(self):
        cards = [f"ARPHE_CARD_{index}" for index in range(5)]
        plans = stack_plan(cards, 0, 12, 0.25, "top", "alternate", [0.02], 0.94, 0.0, 18, "ease_out", True)
        self.assertEqual(cards, [plan["card_id"] for plan in plans])
        self.assertEqual([1, 2, 3, 4, 5], [plan["z_order"] for plan in plans])
        self.assertTrue(all(plans[index]["keys"][0]["frame"] < plans[index + 1]["keys"][0]["frame"] for index in range(4)))


if __name__ == "__main__":
    unittest.main()
