from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402
from bridge.project_tools import create_project  # noqa: E402
from bridge.registry import Registry  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402
from bridge.timeline_tools import _timeline_allowed, create_timeline  # noqa: E402
from bridge.vertical_social_apply import provisional_timeline_name  # noqa: E402
from bridge.vertical_social_jobs import VerticalSocialPlanStore, new_vertical_social_plan  # noqa: E402
from bridge.creative_tools import (_frame_to_timecode, _sequence_boundaries,
                                   _sequence_windows, _automatic_sequence_windows,
                                   _fixed_readability_windows,
                                   _review_reading_frames, _cta_duration_frames,
                                   _intro_duration_frames, _timeline_is_vertical)  # noqa: E402
from bridge.fusion_tools import set_visibility_window  # noqa: E402


def config_for(root: Path) -> CreativeConfig:
    return CreativeConfig(
        root / "config.json", root / "assets", root / "renders", root / "state.json",
        root / "audit.jsonl", dict(DEFAULT_PALETTE), dict(DEFAULT_FLAGS), frozenset(),
        frozenset(), "mp4", "H264",
    )


class FakeManager:
    def __init__(self):
        self.create_calls = 0

    def CreateProject(self, _name):
        self.create_calls += 1
        return object()

    def LoadProject(self, _name):
        return object()

    def SaveProject(self):
        return True

    def GetProjectListInCurrentFolder(self):
        return ["arphe_existing"]

    def GetCurrentProject(self):
        return None


class FakePool:
    def __init__(self, project):
        self.project = project
        self.create_calls = 0

    def CreateEmptyTimeline(self, name):
        self.create_calls += 1
        return FakeTimeline(name, self.project.settings)


class FakeTimeline:
    def __init__(self, name, settings):
        self.name = name
        self.settings = dict(settings)

    def GetName(self):
        return self.name

    def GetSetting(self, key):
        return self.settings.get(key)


class FakeProject:
    def __init__(self):
        self.settings = {
            "timelineResolutionWidth": "1920",
            "timelineResolutionHeight": "1080",
            "timelineFrameRate": "24",
            "timelinePlaybackFrameRate": "24",
        }
        self.pool = FakePool(self)
        self.current = None

    def GetMediaPool(self):
        return self.pool

    def GetCurrentTimeline(self):
        return None

    def GetTimelineCount(self):
        return 0

    def GetTimelineByIndex(self, _index):
        return None

    def SetCurrentTimeline(self, _timeline):
        self.current = _timeline
        return True

    def GetSetting(self, key):
        return self.settings.get(key)

    def SetSetting(self, key, value):
        self.settings[key] = value
        return True

    def GetName(self):
        return "ARPHE_PROJECT"


class ReadOnlyPlaybackProject(FakeProject):
    def __init__(self):
        super().__init__()
        self.set_calls = []

    def SetSetting(self, key, value):
        self.set_calls.append((key, value))
        if key == "timelinePlaybackFrameRate":
            return False
        return super().SetSetting(key, value)


class ProjectTimelineSafetyTests(unittest.TestCase):
    def test_review_sequence_timecode_preserves_resolve_start_hour(self):
        self.assertEqual("01:00:00:00", _frame_to_timecode(108000, 30))
        self.assertEqual("01:00:03:00", _frame_to_timecode(108090, 30))

    def test_review_sequence_detects_portrait_timeline_from_settings(self):
        class PortraitTimeline:
            def GetSetting(self, key):
                return {"timelineResolutionWidth": "1080", "timelineResolutionHeight": "1920"}.get(key)

        self.assertTrue(_timeline_is_vertical(PortraitTimeline()))
        self.assertFalse(_timeline_is_vertical(FakeTimeline("ARPHE_16X9", {
            "timelineResolutionWidth": "1920", "timelineResolutionHeight": "1080",
        })))

    def test_review_sequence_boundaries_are_gap_free(self):
        self.assertEqual([0, 37, 75, 112, 150], _sequence_boundaries(4, 150))

    def test_review_sequence_windows_overlap_for_incoming_motion(self):
        self.assertEqual([(0, 47), (37, 85), (75, 122), (112, 150)],
                         _sequence_windows(4, 150, 10))

    def test_review_sequence_windows_never_exceed_composition(self):
        self.assertEqual([(0, 1), (1, 2), (2, 3), (3, 4)],
                         _sequence_windows(4, 4, 10))

    def test_automatic_review_windows_follow_each_text_reading_time(self):
        reviews = [
            {"text": "Molto bene."},
            {"text": " ".join(["accogliente"] * 30)},
        ]
        self.assertEqual(90, _review_reading_frames(reviews[0]))
        self.assertEqual(270, _review_reading_frames(reviews[1]))
        self.assertEqual(([(0, 100), (90, 360)], 360),
                         _automatic_sequence_windows(reviews))
        self.assertEqual(120, _cta_duration_frames({"headline": "Scopri Arphè", "text": "Prenota ora"}))
        self.assertEqual(90, _intro_duration_frames({"headline": "Dicono di noi", "text": "su MioDottore"}))

    def test_fixed_review_windows_preserve_each_assessed_minimum(self):
        layouts = [{"duration_frames": 90}, {"duration_frames": 360}]
        windows = _fixed_readability_windows(layouts, 510)
        self.assertGreaterEqual(windows[0][1] - windows[0][0], 90)
        self.assertGreaterEqual(windows[1][1] - windows[1][0], 360)
        self.assertEqual(510, windows[-1][1])

    def test_project_collision_stops_before_create(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = FakeManager()
            root = Path(directory)
            with self.assertRaises(ValidationError):
                create_project(manager, config_for(root), Registry(root / "state.json"), "ARPHE_EXISTING")
            self.assertEqual(0, manager.create_calls)

    def test_invalid_timeline_settings_stop_before_create(self):
        with tempfile.TemporaryDirectory() as directory:
            project = FakeProject()
            root = Path(directory)
            registry = Registry(root / "state.json")
            registry.add_project("ARPHE_PROJECT")
            with self.assertRaises(ValidationError):
                create_timeline(project, config_for(root), registry, "ARPHE_TEST", 720, 1280, 30)
            self.assertEqual(0, project.pool.create_calls)

    def test_owned_vertical_provisional_timeline_is_selectable_without_global_allowlist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(config_for(root), workstation_id="PC_PERSONALE",
                             vertical_social_plans_path=root / "vertical_plans.json")
            plan = new_vertical_social_plan(
                workstation_id="PC_PERSONALE",
                target={"project": "ARPHE_PROJECT", "timeline": "SOURCE"},
                actions=[{"action_id": "cut-1", "type": "CUT", "phase": "PROVISIONAL_EDIT"}],
            )
            VerticalSocialPlanStore(config.vertical_social_plans_path, "PC_PERSONALE").create(plan)
            registry = Registry(root / "state.json")
            self.assertTrue(_timeline_allowed(
                "ARPHE_PROJECT", provisional_timeline_name(plan.plan_id), config, registry))
            self.assertFalse(_timeline_allowed(
                "ARPHE_PROJECT", "__ARPHE_VERTICAL_VERTICAL_UNKNOWN", config, registry))

    def test_project_defaults_are_set_before_timeline_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = FakeProject()
            project.settings["timelinePlaybackFrameRate"] = "30"
            registry = Registry(root / "state.json")
            registry.add_project("ARPHE_PROJECT")
            result = create_timeline(project, config_for(root), registry,
                                     "ARPHE_VERTICAL_V2", 1080, 1920, 30)
            self.assertTrue(result["ok"])
            self.assertTrue(result["settings_match"])
            self.assertEqual({"width": "1080", "height": "1920", "fps": "30", "playback_fps": "30"}, result["actual_settings"])
            self.assertEqual(1, project.pool.create_calls)

    def test_playback_mismatch_returns_chat_action_flag_before_timeline_create(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = ReadOnlyPlaybackProject()
            registry = Registry(root / "state.json")
            registry.add_project("ARPHE_PROJECT")
            result = create_timeline(project, config_for(root), registry,
                                     "ARPHE_VERTICAL_GATE", 1080, 1920, 30)
            self.assertFalse(result["ok"])
            self.assertEqual("PLAYBACK_FPS_ACTION_REQUIRED", result.get("flag"))
            self.assertEqual("24", result.get("actual_playback_fps"))
            self.assertEqual("30", result.get("required_playback_fps"))
            self.assertIn("Project Settings", result.get("operator_action", ""))
            self.assertEqual(0, project.pool.create_calls)
            self.assertNotIn(("timelinePlaybackFrameRate", "30"), project.set_calls)

    def test_visibility_window_has_hold_and_closed_boundaries(self):
        class FakeComp:
            def BezierSpline(self):
                return {}

        class FakeMerge:
            Blend = None

        merge = FakeMerge()
        self.assertTrue(set_visibility_window(FakeComp(), merge, 10, 20))
        self.assertEqual({0: 0.0, 9: 0.0, 10: 1.0, 19: 1.0, 20: 0.0}, merge.Blend)


if __name__ == "__main__":
    unittest.main()
