from __future__ import annotations

import json
import ast
import inspect
from types import SimpleNamespace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from mcp.server.mcpserver import Image
from mcp.types import ImageContent, TextContent


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.config import DEFAULT_FLAGS, load_config  # noqa: E402
from bridge.creative_tools import _animate  # noqa: E402
from bridge.motion_presets import motion_plan, stack_plan  # noqa: E402
from bridge.safety import (PlaybackFpsActionRequired, ValidationError, allowed_asset, arphe_name,
                           ensure_no_collision, validate_color_role,
                           validate_frame_range, validate_preset,
                           validate_review, validate_timeline_settings)  # noqa: E402
from bridge.tool_catalog import EXPOSED_TOOL_NAMES, FORBIDDEN_GENERIC_TOOLS  # noqa: E402
from bridge.server import mcp  # noqa: E402
import bridge.server as server  # noqa: E402
from bridge.editorial_workflows import EditorialBrief  # noqa: E402
from bridge.registry import Registry  # noqa: E402


class SafetyTests(unittest.TestCase):
    def test_public_error_exposes_playback_action_flag_for_chat(self):
        result = server._error(PlaybackFpsActionRequired("24", "30"))
        self.assertFalse(result["ok"])
        self.assertEqual("operator_action_required", result["stage"])
        self.assertEqual("PLAYBACK_FPS_ACTION_REQUIRED", result["flag"])
        self.assertEqual("24", result["actual_playback_fps"])
        self.assertEqual("30", result["required_playback_fps"])
        self.assertIn("Project Settings", result["operator_action"])

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

    def test_render_tools_expose_closed_prepare_approve_start_verify_surface(self):
        required = {"list_editorial_workflows", "validate_editorial_brief", "prepare_render_batch",
                    "approve_render_batch", "start_render_batch", "get_render_batch_status",
                    "verify_render_batch", "cancel_render_batch"}
        self.assertTrue(required.issubset(EXPOSED_TOOL_NAMES))

    def test_no_tool_has_start_render_default_or_arbitrary_render_settings(self):
        self.assertNotIn("start_render", inspect.signature(server.queue_publish_package_exports).parameters)
        self.assertNotIn("render_settings", inspect.signature(server.prepare_render_batch).parameters)

    def test_workflow_listing_contains_no_local_brief_or_media_content(self):
        config = SimpleNamespace(workflow_registry_path=ROOT / "editorial_workflows.json")
        with patch("bridge.server.load_config", return_value=config):
            result = server.list_editorial_workflows()
        raw = json.dumps(result)
        self.assertTrue(result["ok"])
        self.assertNotIn("primary_source", raw)
        self.assertNotIn("media_path", raw)
        self.assertNotIn("review_text", raw)

    def test_legacy_render_wrappers_do_not_touch_resolve(self):
        with patch("bridge.server._runtime", side_effect=AssertionError("Resolve must not be touched")):
            self.assertFalse(server.render_preview()["render_started"])
            self.assertFalse(server.queue_longform_exports()["render_started"])
            self.assertFalse(server.queue_publish_package_exports("A", ["B"], "C")["render_started"])

    def test_registry_paths_are_package_relative_not_runtime_config_relative(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"runtime_id": "ARPHE_MCP_BRIDGE_CREATIVE_03",
                                        "workstation_id": "PC_PERSONALE",
                                        "workflow_registry_path": "editorial_workflows.json",
                                        "render_profile_registry_path": "render_profiles.json"}), encoding="utf-8")
            config = load_config(path)
        self.assertEqual(ROOT / "editorial_workflows.json", config.workflow_registry_path)
        self.assertEqual(ROOT / "render_profiles.json", config.render_profile_registry_path)

    def test_public_prepare_rejects_profile_from_another_workflow_before_resolve_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); state = root / "state.json"; registry = Registry(state)
            brief = EditorialBrief("brief-1", "CARABELLESE_YOUTUBE_CLEANUP", 1, "SEGRETERIA",
                                   "source.mov", ("publishable",), {}, {}, ())
            registry.save_brief(brief)
            config = SimpleNamespace(state_path=state, render_profile_registry_path=ROOT / "render_profiles.json",
                                     workstation_id="PC_PERSONALE")
            runtime = (object(), object(), object(), object(), config, registry, None)
            with patch("bridge.server._runtime", return_value=runtime), \
                 patch("bridge.server.do_prepare_render_batch", side_effect=AssertionError("must not write")):
                result = server.prepare_render_batch("brief-1", "VERTICAL_SOCIAL_H264", "ARPHE_PROJECT",
                                                     ["ARPHE_MAIN"], ["OUT"], 1080, 1920, "30")
            self.assertFalse(result["ok"])
            self.assertEqual("ValidationError", result["error_type"])

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

    def test_config_accepts_personal_workstation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({
                "runtime_id": "ARPHE_MCP_BRIDGE_CREATIVE_03",
                "workstation_id": "PC_PERSONALE",
            }), encoding="utf-8")
            config = load_config(path)
            self.assertEqual(path.resolve(), config.path)
            self.assertEqual("PC_PERSONALE", config.workstation_id)
            self.assertEqual(path.parent / "resolve-archives", config.resolve_archive_root)
            self.assertEqual(path.parent / "resolve-retirements.json",
                             config.resolve_retirement_registry_path)
            self.assertFalse(config.flags["CAP_RESOLVE_RETIREMENT"])

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

    def test_motion_uses_path_center_and_composite_opacity(self):
        class FakeTool:
            Center = None
            Size = None
            Angle = None
            Blend = {0: 1.0, 19: 1.0, 20: 0.0}

        transform = FakeTool()
        merge = FakeTool()

        class FakeComp:
            def BezierSpline(self):
                return {}

            def Path(self):
                return {}

            def FindTool(self, name):
                return {"CARD_TRANSFORM": transform, "CARD_OUTER": merge}.get(name)

        plan = motion_plan("ARPHE_SOFT_DROP", 10, 10)
        record = {"transform_name": "CARD_TRANSFORM", "outer_merge_name": "CARD_OUTER",
                  "start_frame": 10, "end_frame": 30}
        self.assertTrue(_animate(FakeComp(), record, plan))
        self.assertEqual({1: 0.525, 2: 0.32, 3: 0.0}, transform.Center[10])
        self.assertEqual(1.0, transform.Blend)
        self.assertEqual(0.0, merge.Blend[10])
        self.assertEqual(1.0, merge.Blend[20])
        self.assertEqual({1: 0.5, 2: 0.5, 3: 0.0}, transform.Center[29])
        self.assertEqual(1.0, transform.Size[29])
        self.assertEqual(0.0, transform.Angle[29])
        self.assertEqual(1.0, merge.Blend[29])

    def test_cta_fade_animates_only_opacity_and_holds_until_end(self):
        class FakeTool:
            Center = 0.5
            Size = 1.0
            Angle = 0.0
            Blend = 1.0

        transform = FakeTool()
        merge = FakeTool()

        class FakeComp:
            def BezierSpline(self):
                return {}

            def Path(self):
                raise AssertionError("La dissolvenza CTA non deve creare un Path")

            def FindTool(self, name):
                return {"CTA_TRANSFORM": transform, "CTA_OUTER": merge}.get(name)

        plan = motion_plan("ARPHE_CTA_FADE", 10, 24)
        self.assertTrue(all(key["x"] == key["y"] == key["rotation"] == 0.0
                            and key["scale"] == 1.0 for key in plan["keys"]))
        record = {"transform_name": "CTA_TRANSFORM", "outer_merge_name": "CTA_OUTER",
                  "start_frame": 10, "end_frame": 80}
        self.assertTrue(_animate(FakeComp(), record, plan))
        self.assertEqual(0.5, transform.Center)
        self.assertEqual(1.0, transform.Size)
        self.assertEqual(0.0, transform.Angle)
        self.assertEqual(0.0, merge.Blend[10])
        self.assertGreater(merge.Blend[22], 0.0)
        self.assertLess(merge.Blend[22], 1.0)
        self.assertEqual(1.0, merge.Blend[34])
        self.assertTrue(all(merge.Blend[frame] == 1.0 for frame in range(34, 80)))
        self.assertEqual(1.0, merge.Blend[79])
        self.assertEqual(0.0, merge.Blend[80])


class ToolAnnotationTests(unittest.IsolatedAsyncioTestCase):
    async def test_tools_are_closed_world_and_destructive_tools_are_explicit(self):
        tools = {tool.name: tool for tool in await mcp.list_tools()}
        self.assertEqual(set(EXPOSED_TOOL_NAMES), set(tools))
        for tool in tools.values():
            self.assertEqual(tool.name in {"run_artifact_maintenance", "execute_resolve_retirement"},
                             tool.annotations.destructive_hint, tool.name)
            self.assertFalse(tool.annotations.open_world_hint, tool.name)
        self.assertTrue(tools["run_artifact_maintenance"].annotations.idempotent_hint)
        self.assertTrue(tools["inspect_artifact_hygiene"].annotations.read_only_hint)
        self.assertFalse(tools["restore_quarantined_artifact"].annotations.read_only_hint)
        self.assertFalse(tools["restore_quarantined_artifact"].annotations.destructive_hint)
        self.assertTrue(tools["execute_resolve_retirement"].annotations.idempotent_hint)
        self.assertTrue(tools["inspect_resolve_retirements"].annotations.read_only_hint)

    def test_artifact_tools_accept_no_arbitrary_path(self):
        self.assertEqual([], list(inspect.signature(server.inspect_artifact_hygiene).parameters))
        self.assertEqual([], list(inspect.signature(server.run_artifact_maintenance).parameters))
        self.assertEqual(["artifact_id"],
                         list(inspect.signature(server.restore_quarantined_artifact).parameters))

    def test_resolve_retirement_tools_accept_ids_and_names_but_no_path(self):
        self.assertEqual([], list(inspect.signature(server.inspect_resolve_retirements).parameters))
        self.assertEqual(["kind", "project_name", "timeline_name"],
                         list(inspect.signature(server.prepare_resolve_retirement).parameters))
        self.assertEqual(["retirement_id", "operator_role"],
                         list(inspect.signature(server.approve_resolve_retirement).parameters))
        self.assertEqual(["retirement_id"],
                         list(inspect.signature(server.execute_resolve_retirement).parameters))
        self.assertEqual(["retirement_id"],
                         list(inspect.signature(server.recover_resolve_retirement).parameters))

    async def test_prepare_and_approve_are_safe_writes_start_and_cancel_are_explicit_writes(self):
        tools = {tool.name: tool for tool in await mcp.list_tools()}
        for name in ("prepare_render_batch", "approve_render_batch", "start_render_batch", "cancel_render_batch"):
            self.assertFalse(tools[name].annotations.read_only_hint, name)
        for name in ("list_editorial_workflows", "get_render_batch_status"):
            self.assertTrue(tools[name].annotations.read_only_hint, name)

    async def test_diagnostic_reads_and_capture_are_classified_explicitly(self):
        tools = {tool.name: tool for tool in await mcp.list_tools()}
        for name in ("ping", "resolve_status", "get_feature_flags", "get_creative_status",
                     "inspect_fusion_graph"):
            self.assertTrue(tools[name].annotations.read_only_hint, name)
            self.assertTrue(tools[name].annotations.idempotent_hint, name)
        self.assertFalse(tools["capture_timeline_frames"].annotations.read_only_hint)
        self.assertFalse(tools["capture_timeline_frames"].annotations.idempotent_hint)

    async def test_capture_tool_returns_mcp_content_without_serializing_image_helpers(self):
        metadata = {
            "ok": True,
            "action": "capture_timeline_frames",
            "captures": [{"frame_offset": 0, "timecode": "01:00:00:00"}],
        }
        runtime = (object(), object(), object(), object(), object(), object(), None)
        with patch("bridge.server._runtime", return_value=runtime), patch(
            "bridge.server.do_capture_timeline_frames",
            return_value=[metadata, Image(data=b"fake-jpeg", format="jpeg")],
        ):
            result = await mcp.call_tool("capture_timeline_frames", {"frame_offsets": [0]})

        self.assertFalse(result.is_error)
        self.assertEqual(metadata, result.structured_content)
        self.assertIsInstance(result.content[0], TextContent)
        self.assertIsInstance(result.content[1], ImageContent)
        self.assertEqual("image/jpeg", result.content[1].mime_type)


if __name__ == "__main__":
    unittest.main()
