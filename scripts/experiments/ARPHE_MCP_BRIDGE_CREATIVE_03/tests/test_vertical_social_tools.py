from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.config import DEFAULT_FLAGS
from bridge.tool_catalog import EXPOSED_TOOL_NAMES
import bridge.server as server


class VerticalSocialToolTests(unittest.TestCase):
    def config(self, root: Path, enabled=False):
        flags = dict(DEFAULT_FLAGS)
        flags["CAP_VERTICAL_SOCIAL"] = enabled
        return SimpleNamespace(
            flags=flags, workstation_id="PC_PERSONALE",
            vertical_social_plans_path=root / "plans.json",
            audit_log_path=root / "audit.jsonl",
        )

    def test_catalog_exposes_closed_vertical_social_surface(self):
        required = {"inspect_vertical_social", "prepare_vertical_social_plan",
                    "approve_vertical_social_plan", "inspect_vertical_social_plan",
                    "mark_vertical_social_picture_lock", "advance_vertical_social_action",
                    "apply_vertical_social_cuts", "apply_vertical_social_action"}
        self.assertTrue(required.issubset(EXPOSED_TOOL_NAMES))
        for name in required:
            self.assertTrue(callable(getattr(server, name)))

    def test_inspection_works_off_and_mutation_fails_before_runtime(self):
        with tempfile.TemporaryDirectory() as raw:
            cfg = self.config(Path(raw), False)
            with patch("bridge.server.load_config", return_value=cfg),                  patch("bridge.server._runtime", side_effect=AssertionError("runtime touched")):
                status = server.inspect_vertical_social()
                prepared = server.prepare_vertical_social_plan(
                    {"project": "ARPHE", "timeline": "ADV", "fps": "30"}, [])
        self.assertTrue(status["ok"])
        self.assertFalse(status["capability_enabled"])
        self.assertFalse(prepared["ok"])
        self.assertIn("CAP_VERTICAL_SOCIAL", prepared["error"])

    def test_action_executor_routes_reframe_to_owned_provisional_and_restores_timeline(self):
        class Named:
            def __init__(self, name): self.name = name
            def GetName(self): return self.name
        class Project(Named):
            def __init__(self):
                super().__init__("ARPHE")
                self.current = Named("SOURCE")
            def SetCurrentTimeline(self, timeline): self.current = timeline; return True

        with tempfile.TemporaryDirectory() as raw:
            cfg = self.config(Path(raw), True)
            project, source, provisional = Project(), Named("SOURCE"), Named("__ARPHE_VERTICAL_VERTICAL_12345678")
            project.current = source
            action = SimpleNamespace(action_id="r1", action_type="REFRAME", state="APPROVED",
                                     evidence={}, to_dict=lambda: {
                                         "action_id": "r1", "type": "REFRAME", "state": "APPROVED",
                                         "range": {"start_frame": 0, "end_frame": 60},
                                         "target": {"kind": "person", "label": "speaker"},
                                         "anchor": {"x": .5, "y": .5}, "reason": "volto"})
            plan = SimpleNamespace(target={"project": "ARPHE", "timeline": "SOURCE",
                                                   "total_frames": 60},
                                   action=lambda action_id: action)
            with patch("bridge.server._runtime", return_value=(object(), object(), project, source, cfg, object(), None)), \
                 patch("bridge.server.require_capability"), \
                 patch("bridge.server.do_approved_vertical_social_plan", return_value=plan), \
                 patch("bridge.server.do_find_vertical_social_provisional", return_value=provisional), \
                 patch("bridge.server.do_apply_vertical_social_reframe", return_value={"ok": True, "action_id": "r1"}), \
                 patch("bridge.server.do_record_vertical_social_action_execution", return_value=plan):
                result = server.apply_vertical_social_action("vertical_12345678", "fingerprint", "r1")
            self.assertTrue(result["ok"])
            self.assertIs(source, project.current)

    def test_cut_executor_restores_source_after_creating_provisional(self):
        class Clip:
            def GetDuration(self): return 60
        class Timeline:
            def __init__(self, name): self.name = name
            def GetName(self): return self.name
            def GetItemListInTrack(self, kind, index): return [Clip()]
        class Project:
            def __init__(self, source): self.source, self.current = source, source
            def GetName(self): return "ARPHE"
            def SetCurrentTimeline(self, timeline): self.current = timeline; return True

        with tempfile.TemporaryDirectory() as raw:
            cfg = self.config(Path(raw), True)
            source, provisional = Timeline("SOURCE"), Timeline("__ARPHE_VERTICAL_VERTICAL_12345678")
            project = Project(source)
            plan = SimpleNamespace(target={"project": "ARPHE", "timeline": "SOURCE"},
                                   to_dict=lambda: {"plan_id": "vertical_12345678", "actions": []})
            verified = SimpleNamespace(actions=())
            def create(*args, **kwargs):
                project.current = provisional
                return provisional
            with patch("bridge.server._runtime", return_value=(object(), object(), project, source, cfg, object(), None)), \
                 patch("bridge.server.require_capability"), \
                 patch("bridge.server.do_approved_vertical_social_plan", return_value=plan), \
                 patch("bridge.server.do_create_provisional_cut_timeline", side_effect=create), \
                 patch("bridge.server.do_record_vertical_social_cut_execution", return_value=verified):
                result = server.apply_vertical_social_cuts("vertical_12345678", "fingerprint")
            self.assertTrue(result["ok"])
            self.assertIs(source, project.current)

    def test_action_executor_routes_validated_music_duck_and_graphic(self):
        class Named:
            def __init__(self, name): self.name = name
            def GetName(self): return self.name
        class Project(Named):
            def __init__(self, source): super().__init__("ARPHE"); self.current = source
            def SetCurrentTimeline(self, timeline): self.current = timeline; return True
        with tempfile.TemporaryDirectory() as raw:
            cfg = self.config(Path(raw), True)
            source, provisional = Named("SOURCE"), Named("__ARPHE_VERTICAL_VERTICAL_12345678")
            project = Project(source)
            action = SimpleNamespace(action_id="m1", action_type="MUSIC_DUCK", state="APPROVED",
                                     evidence={}, to_dict=lambda: {"action_id": "m1", "type": "MUSIC_DUCK"})
            current = [action]
            plan = SimpleNamespace(target={"project": "ARPHE", "timeline": "SOURCE", "total_frames": 60},
                                   action=lambda action_id: current[0])
            with patch("bridge.server._runtime", return_value=(object(), object(), project, source, cfg, object(), None)), \
                 patch("bridge.server.require_capability"), \
                 patch("bridge.server.do_approved_vertical_social_plan", return_value=plan), \
                 patch("bridge.server.do_find_vertical_social_provisional", return_value=provisional), \
                 patch("bridge.server.do_apply_vertical_social_music", return_value={"ok": True, "action_id": "m1"}) as apply, \
                 patch("bridge.server.do_apply_vertical_social_overlay", return_value={"ok": True, "action_id": "g1"}) as overlay, \
                 patch("bridge.server.do_record_vertical_social_action_execution", return_value=plan):
                result = server.apply_vertical_social_action("vertical_12345678", "fingerprint", "m1")
                current[0] = SimpleNamespace(action_id="g1", action_type="GRAPHIC", state="APPROVED",
                                             evidence={}, to_dict=lambda: {"action_id": "g1", "type": "GRAPHIC"})
                graphic = server.apply_vertical_social_action("vertical_12345678", "fingerprint", "g1")
            self.assertTrue(result["ok"])
            self.assertTrue(graphic["ok"])
            apply.assert_called_once()
            overlay.assert_called_once()
            self.assertIs(source, project.current)

    def test_action_executor_requires_picture_lock_before_routing_captions(self):
        class Named:
            def __init__(self, name): self.name = name
            def GetName(self): return self.name
        class Project(Named):
            def __init__(self, source): super().__init__("ARPHE"); self.current = source
            def SetCurrentTimeline(self, timeline): self.current = timeline; return True
        with tempfile.TemporaryDirectory() as raw:
            cfg = self.config(Path(raw), True)
            source, provisional = Named("SOURCE"), Named("__ARPHE_VERTICAL_VERTICAL_12345678")
            project = Project(source)
            action = SimpleNamespace(
                action_id="c1", action_type="CAPTIONS", state="APPROVED", evidence={},
                to_dict=lambda: {"action_id": "c1", "type": "CAPTIONS",
                                 "locked_edit_fingerprint": "AT_PICTURE_LOCK"},
            )
            plan = SimpleNamespace(
                target={"project": "ARPHE", "timeline": "SOURCE", "total_frames": 60},
                action=lambda action_id: action,
            )
            lock_state = {"picture_locked": False, "locked_edit_fingerprint": None}
            current_fingerprint = ["b" * 64]
            with patch("bridge.server._runtime", return_value=(object(), object(), project, source, cfg, object(), None)), \
                 patch("bridge.server.require_capability"), \
                 patch("bridge.server.do_approved_vertical_social_plan", return_value=plan), \
                 patch("bridge.server.do_inspect_vertical_social_plan", side_effect=lambda *args: lock_state), \
                 patch("bridge.server.do_find_vertical_social_provisional", return_value=provisional), \
                 patch("bridge.server.vertical_social_timeline_fingerprint",
                       side_effect=lambda timeline: current_fingerprint[0]), \
                 patch("bridge.server.do_apply_vertical_social_captions", create=True,
                       return_value={"ok": True, "action_id": "c1"}) as apply, \
                 patch("bridge.server.do_record_vertical_social_action_execution", return_value=plan):
                blocked = server.apply_vertical_social_action("vertical_12345678", "fingerprint", "c1")
                self.assertFalse(blocked["ok"])
                self.assertIn("picture lock", blocked["error"].lower())
                apply.assert_not_called()

                lock_state.update({"picture_locked": True, "locked_edit_fingerprint": "a" * 64})
                changed = server.apply_vertical_social_action("vertical_12345678", "fingerprint", "c1")
                self.assertFalse(changed["ok"])
                self.assertIn("dopo il picture lock", changed["error"])

                current_fingerprint[0] = "a" * 64
                result = server.apply_vertical_social_action("vertical_12345678", "fingerprint", "c1")
            self.assertTrue(result["ok"])
            apply.assert_called_once()
            self.assertEqual("a" * 64, apply.call_args.args[3]["locked_edit_fingerprint"])
            self.assertIs(source, project.current)

    def test_picture_lock_tool_fingerprints_owned_provisional(self):
        with tempfile.TemporaryDirectory() as raw:
            cfg = self.config(Path(raw), True)
            provisional = object()
            wrapped = SimpleNamespace(plan_id="vertical_12345678", picture_locked=True)
            with patch("bridge.server.load_config", return_value=cfg), \
                 patch("bridge.server._runtime", return_value=(object(), object(), object(), object(), cfg, object(), None)), \
                 patch("bridge.server.require_capability"), \
                 patch("bridge.server.do_find_vertical_social_provisional", return_value=provisional), \
                 patch("bridge.server.vertical_social_timeline_fingerprint", return_value="d" * 64), \
                 patch("bridge.server.do_mark_vertical_social_picture_lock", return_value=wrapped) as mark:
                result = server.mark_vertical_social_picture_lock("vertical_12345678")
            self.assertTrue(result["ok"])
            self.assertEqual("d" * 64, result["locked_edit_fingerprint"])
            mark.assert_called_once_with(
                cfg.vertical_social_plans_path, "PC_PERSONALE", "vertical_12345678", "d" * 64)


if __name__ == "__main__":
    unittest.main()
