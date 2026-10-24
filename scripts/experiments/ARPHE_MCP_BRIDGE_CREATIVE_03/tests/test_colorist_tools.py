from __future__ import annotations

from dataclasses import replace
import inspect
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge import server  # noqa: E402
from bridge.colorist_jobs import after_version_names  # noqa: E402
from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402
from bridge.registry import Registry  # noqa: E402


class FakeGraph:
    def GetNumNodes(self): return 1
    def ApplyGradeFromDRX(self, *_args): return True


class FakeClip:
    def __init__(self, clip_id):
        self.clip_id = clip_id
        self.add_calls = []

    def GetUniqueId(self): return self.clip_id
    def GetName(self): return self.clip_id
    def GetStart(self): return 0
    def GetEnd(self): return 100
    def GetCurrentVersion(self): return {"versionName": "Original", "versionType": 0}
    def GetVersionNameList(self, _kind): return ["Original"]
    def AddVersion(self, name, kind): self.add_calls.append((name, kind)); return True
    def LoadVersionByName(self, *_args): return True
    def SetCDL(self, *_args): return True
    def CopyGrades(self, *_args): return True
    def GetNodeGraph(self): return FakeGraph()


class FakeTimeline:
    def __init__(self): self.clips = [FakeClip("clip-a"), FakeClip("clip-b")]
    def GetName(self): return "ARPHE_COLOR_TEST"
    def GetUniqueId(self): return "timeline-123"
    def GetTrackCount(self, kind): return 1 if kind == "video" else 0
    def GetItemListInTrack(self, kind, index): return self.clips if kind == "video" and index == 1 else []


class FakeProject:
    def GetName(self): return "ARPHE_TEST"


def config_for(root: Path, enabled=False):
    flags = dict(DEFAULT_FLAGS)
    flags["CAP_COLORIST"] = enabled
    return CreativeConfig(
        root / "config.json", root / "assets", root / "renders", root / "state.json",
        root / "audit.jsonl", dict(DEFAULT_PALETTE), flags, frozenset(), frozenset(), "mp4", "H264",
        workstation_id="PC_PERSONALE", colorist_jobs_path=root / "colorist_jobs.json",
        colorist_presets_path=ROOT / "colorist_presets.json",
        artifact_registry_path=root / "artifact_registry.json",
    )


class ColoristToolTests(unittest.IsolatedAsyncioTestCase):
    def test_tool_signatures_are_closed_and_accept_no_paths_or_raw_cdl(self):
        self.assertEqual([], list(inspect.signature(server.inspect_colorist_context).parameters))
        self.assertEqual(
            ["clip_ids", "reference_clip_id", "adjustments", "preset_name", "drx_preset_name"],
            list(inspect.signature(server.prepare_colorist_plan).parameters),
        )
        self.assertEqual(["colorist_job_id", "expected_plan_fingerprint", "operator_role"],
                         list(inspect.signature(server.approve_colorist_plan).parameters))
        self.assertEqual(["colorist_job_id"], list(inspect.signature(server.apply_colorist_plan).parameters))
        self.assertEqual(["colorist_job_id", "clip_id", "side"],
                         list(inspect.signature(server.preview_colorist_version).parameters))
        self.assertEqual(["colorist_job_id", "clip_id"],
                         list(inspect.signature(server.restore_colorist_preview).parameters))
        self.assertEqual(
            ["colorist_job_id", "expected_plan_fingerprint", "expected_revision", "operator_role", "reason"],
            list(inspect.signature(server.cancel_colorist_plan).parameters),
        )

    async def test_annotations_make_inspection_read_only_and_every_state_change_explicit(self):
        tools = {tool.name: tool for tool in await server.mcp.list_tools()}
        for name in ("inspect_colorist_context", "inspect_colorist_plan"):
            self.assertTrue(tools[name].annotations.read_only_hint, name)
        for name in ("prepare_colorist_plan", "approve_colorist_plan", "apply_colorist_plan",
                     "preview_colorist_version", "restore_colorist_preview", "submit_colorist_review",
                     "cancel_colorist_plan"):
            self.assertFalse(tools[name].annotations.read_only_hint, name)
            self.assertFalse(tools[name].annotations.destructive_hint, name)
            self.assertFalse(tools[name].annotations.open_world_hint, name)

    def test_cancel_prepared_plan_uses_fingerprint_and_revision_without_resolve(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = config_for(root, enabled=False)
            project, timeline = FakeProject(), FakeTimeline()
            registry = Registry(config.state_path)
            registry.add_project("ARPHE_TEST")
            registry.add_timeline("ARPHE_TEST", "ARPHE_COLOR_TEST")
            runtime = (object(), object(), project, timeline, config, registry, None)
            with patch("bridge.server._runtime", return_value=runtime), patch(
                "bridge.server.load_config", return_value=config
            ):
                prepared = server.prepare_colorist_plan(
                    ["clip-a"], "clip-a", {}, "ARPHE_CLEAN_NEUTRAL", None,
                )
                cancelled = server.cancel_colorist_plan(
                    prepared["colorist_job_id"], prepared["plan_fingerprint"], prepared["revision"],
                    "ALESSIO", "No longer needed",
                )
            self.assertTrue(cancelled["ok"])
            self.assertEqual("CANCELLED", cancelled["state"])
            self.assertEqual([], timeline.clips[0].add_calls)

    def test_prepare_and_approve_are_offline_but_apply_fails_closed_when_gate_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = config_for(root, enabled=False)
            project, timeline = FakeProject(), FakeTimeline()
            registry = Registry(config.state_path)
            registry.add_project("ARPHE_TEST")
            registry.add_timeline("ARPHE_TEST", "ARPHE_COLOR_TEST")
            runtime = (object(), object(), project, timeline, config, registry, None)
            with patch("bridge.server._runtime", return_value=runtime), patch(
                "bridge.server.load_config", return_value=config
            ):
                prepared = server.prepare_colorist_plan(
                    ["clip-a", "clip-b"], "clip-a", {"temperature": 0.1},
                    "ARPHE_CLEAN_NEUTRAL", None,
                )
                self.assertTrue(prepared["ok"])
                approved = server.approve_colorist_plan(
                    prepared["colorist_job_id"], prepared["plan_fingerprint"], "ALESSIO"
                )
                self.assertTrue(approved["ok"])
                applied = server.apply_colorist_plan(prepared["colorist_job_id"])

            self.assertFalse(applied["ok"])
            self.assertIn("CAP_COLORIST", applied["error"])
            self.assertEqual([], timeline.clips[0].add_calls)

    def test_arphe_prefix_is_not_authorization_without_registry_or_allowlist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = config_for(root, enabled=False)
            project, timeline = FakeProject(), FakeTimeline()
            runtime = (object(), object(), project, timeline, config, Registry(config.state_path), None)
            with patch("bridge.server._runtime", return_value=runtime):
                result = server.prepare_colorist_plan(
                    ["clip-a"], "clip-a", {}, "ARPHE_CLEAN_NEUTRAL", None,
                )
            self.assertFalse(result["ok"])
            self.assertIn("registrato", result["error"])
            self.assertEqual([], timeline.clips[0].add_calls)

    def test_changed_drx_is_rejected_before_resolve_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "assets" / "looks"
            assets.mkdir(parents=True)
            drx = assets / "look.drx"
            drx.write_text("approved", encoding="utf-8")
            presets = root / "presets.json"
            presets.write_text(json.dumps({
                "schema": "ARPHE_COLORIST_PRESETS_V1",
                "presets": {"ARPHE_CLEAN_NEUTRAL": {
                    "temperature": 0.0, "tint": 0.0, "exposure_stops": 0.0,
                    "contrast": 0.0, "saturation": 1.0,
                }},
                "drx_presets": {"ARPHE_LOOK": "looks/look.drx"},
            }), encoding="utf-8")
            config = replace(config_for(root, enabled=True), colorist_presets_path=presets)
            project, timeline = FakeProject(), FakeTimeline()
            registry = Registry(config.state_path)
            registry.add_project("ARPHE_TEST")
            registry.add_timeline("ARPHE_TEST", "ARPHE_COLOR_TEST")
            runtime = (object(), object(), project, timeline, config, registry, None)
            with patch("bridge.server._runtime", return_value=runtime), patch(
                "bridge.server.load_config", return_value=config
            ):
                prepared = server.prepare_colorist_plan(
                    ["clip-a"], "clip-a", {}, "ARPHE_CLEAN_NEUTRAL", "ARPHE_LOOK",
                )
                approved = server.approve_colorist_plan(
                    prepared["colorist_job_id"], prepared["plan_fingerprint"], "ALESSIO"
                )
                self.assertTrue(approved["ok"])
                drx.write_text("changed-after-approval", encoding="utf-8")
                applied = server.apply_colorist_plan(prepared["colorist_job_id"])
            self.assertFalse(applied["ok"])
            self.assertIn("modificato", applied["error"])
            self.assertEqual([], timeline.clips[0].add_calls)

    def test_apply_failure_is_persisted_as_recoverable_not_left_approved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = config_for(root, enabled=True)
            project, timeline = FakeProject(), FakeTimeline()
            registry = Registry(config.state_path)
            registry.add_project("ARPHE_TEST")
            registry.add_timeline("ARPHE_TEST", "ARPHE_COLOR_TEST")
            runtime = (object(), object(), project, timeline, config, registry, None)
            failure = {"ok": False, "stage": "apply_colorist", "recoverable": True,
                       "error": "simulated", "created_versions": [], "restored_clip_ids": []}
            with patch("bridge.server._runtime", return_value=runtime), patch(
                "bridge.server.load_config", return_value=config
            ), patch("bridge.server.do_apply_colorist_job", return_value=failure):
                prepared = server.prepare_colorist_plan(
                    ["clip-a"], "clip-a", {}, "ARPHE_CLEAN_NEUTRAL", None,
                )
                server.approve_colorist_plan(
                    prepared["colorist_job_id"], prepared["plan_fingerprint"], "ALESSIO"
                )
                applied = server.apply_colorist_plan(prepared["colorist_job_id"])
                inspected = server.inspect_colorist_plan(prepared["colorist_job_id"])
            self.assertFalse(applied["ok"])
            self.assertEqual("FAILED_RECOVERABLE", applied["state"])
            self.assertEqual("FAILED_RECOVERABLE", inspected["state"])

    def test_failed_preview_restore_keeps_tracking_for_a_later_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = config_for(root, enabled=True)
            project, timeline = FakeProject(), FakeTimeline()
            registry = Registry(config.state_path)
            registry.add_project("ARPHE_TEST")
            registry.add_timeline("ARPHE_TEST", "ARPHE_COLOR_TEST")
            runtime = (object(), object(), project, timeline, config, registry, None)
            with patch("bridge.server._runtime", return_value=runtime), patch(
                "bridge.server.load_config", return_value=config
            ):
                prepared = server.prepare_colorist_plan(
                    ["clip-a"], "clip-a", {}, "ARPHE_CLEAN_NEUTRAL", None,
                )
                server.approve_colorist_plan(
                    prepared["colorist_job_id"], prepared["plan_fingerprint"], "ALESSIO"
                )
                applying = server._colorist_store(config).get(
                    prepared["colorist_job_id"], config.workstation_id
                )
                names = after_version_names(applying)
                evidence = ({
                    "clip_id": "clip-a", "before_version": "Original",
                    "after_version": names["clip-a"], "reference_clip_id": "clip-a",
                    "cdl_applied_directly": True, "drx_preset_name": None,
                },)
                with patch("bridge.server.do_apply_colorist_job", return_value={
                    "ok": True, "evidence": evidence,
                }):
                    applied = server.apply_colorist_plan(prepared["colorist_job_id"])
                self.assertTrue(applied["ok"])
                with patch("bridge.server.do_validate_colorist_preview", return_value={
                    "restore_version": names["clip-a"], "target_version": "Original",
                }), patch("bridge.server.do_preview_colorist_version", return_value={
                    "ok": True, "clip_id": "clip-a", "loaded_version": "Original",
                }):
                    previewed = server.preview_colorist_version(
                        prepared["colorist_job_id"], "clip-a", "before"
                    )
                self.assertTrue(previewed["ok"])
                with patch(
                    "bridge.server.do_restore_colorist_preview",
                    side_effect=RuntimeError("Ripristino preview read-back fallito"),
                ):
                    restored = server.restore_colorist_preview(
                        prepared["colorist_job_id"], "clip-a"
                    )
                inspected = server.inspect_colorist_plan(prepared["colorist_job_id"])

            self.assertFalse(restored["ok"])
            self.assertEqual(names["clip-a"], inspected["preview_restore_versions"]["clip-a"])


if __name__ == "__main__":
    unittest.main()
