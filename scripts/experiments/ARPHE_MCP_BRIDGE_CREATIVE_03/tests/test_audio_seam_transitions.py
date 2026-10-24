from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.audio_seam_transitions import (  # noqa: E402
    apply_audio_seam_transitions,
    create_audio_seam_test,
)
from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402
from bridge.registry import Registry  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402
from bridge.tool_catalog import EXPOSED_TOOL_NAMES  # noqa: E402


class AudioItem:
    def __init__(self, start: int, end: int, accepts_transition: bool = True, transition_type: str = "transition"):
        self.start = start
        self.end = end
        self.accepts_transition = accepts_transition
        self.transition_type = transition_type
        self.transitions: list[dict[str, object]] = []

    def GetStart(self):
        return self.start

    def GetEnd(self):
        return self.end

    def AddTransition(self, options):
        self.transitions.append(dict(options))
        return NativeTransition(self.transition_type) if self.accepts_transition else None


class NativeTransition:
    def __init__(self, transition_type: str = "transition"):
        self.transition_type = transition_type

    def GetType(self):
        return self.transition_type


class Timeline:
    def __init__(self, audio_items: list[AudioItem], name: str = "Timeline 1"):
        self.audio_items = audio_items
        self.name = name
        self.project = None

    def GetItemListInTrack(self, track_type: str, index: int):
        return list(self.audio_items) if (track_type, index) == ("audio", 1) else []

    def GetName(self):
        return self.name

    def DuplicateTimeline(self, name: str):
        duplicate = Timeline(
            [AudioItem(item.start, item.end, item.accepts_transition, item.transition_type) for item in self.audio_items], name,
        )
        duplicate.project = self.project
        self.project.timelines.append(duplicate)
        self.project.current = duplicate
        return duplicate


class Project:
    def __init__(self, timeline: Timeline):
        self.timeline = timeline
        timeline.project = self
        self.timelines = [timeline]
        self.current = timeline
        self.pool = Pool(self)
        self.settings = {}

    def GetName(self):
        return "advbeppe"

    def GetCurrentTimeline(self):
        return self.current

    def SetCurrentTimeline(self, timeline):
        self.current = timeline
        return True

    def GetTimelineCount(self):
        return len(self.timelines)

    def GetTimelineByIndex(self, index: int):
        return self.timelines[index - 1]

    def GetMediaPool(self):
        return self.pool

    def GetSetting(self, key: str):
        return self.settings.get(key)

    def SetSetting(self, key: str, value):
        self.settings[key] = value
        return True


class Pool:
    def __init__(self, project: Project):
        self.project = project

    def CreateEmptyTimeline(self, _name: str):
        return None

    def DeleteTimelines(self, timelines):
        self.project.timelines = [timeline for timeline in self.project.timelines if timeline not in timelines]
        return True


def config(root: Path) -> CreativeConfig:
    flags = dict(DEFAULT_FLAGS)
    flags["CAP_TIMELINE"] = True
    return CreativeConfig(
        path=root / "config.json", asset_root=root / "assets", render_root=root / "renders",
        state_path=root / "state.json", audit_log_path=root / "audit.jsonl",
        palette=dict(DEFAULT_PALETTE), flags=flags,
        allowed_projects=frozenset({"advbeppe"}), allowed_timelines=frozenset({"Timeline 1"}),
        render_format="mp4", render_codec="H264", workstation_id="PC_PERSONALE",
    )


class AudioSeamTransitionTests(unittest.TestCase):
    def test_exposes_only_the_named_audio_seam_test(self):
        self.assertIn("create_audio_seam_test", EXPOSED_TOOL_NAMES)
        self.assertNotIn("edit_audio_at_frame", EXPOSED_TOOL_NAMES)

    def test_adds_native_audio_cross_fades_at_verified_contiguous_boundaries(self):
        first = AudioItem(108000, 108309)
        second = AudioItem(108309, 108610)
        third = AudioItem(108610, 108645)

        result = apply_audio_seam_transitions(
            Timeline([first, second, third]), cut_frames=[108309, 108610], duration_frames=2,
        )

        expected = {
            "type": "Cross Fade 0 dB", "category": "audio", "position": "start",
            "alignment": "center", "duration": 2,
        }
        self.assertEqual([108309, 108610], result["cut_frames"])
        self.assertEqual([expected], second.transitions)
        self.assertEqual([expected], third.transitions)
        self.assertEqual([], first.transitions)

    def test_refuses_a_non_contiguous_boundary_before_adding_a_transition(self):
        first = AudioItem(108000, 108308)
        second = AudioItem(108309, 108610)

        with self.assertRaisesRegex(ValidationError, "taglio A1"):
            apply_audio_seam_transitions(
                Timeline([first, second]), cut_frames=[108309], duration_frames=2,
            )

        self.assertEqual([], first.transitions)
        self.assertEqual([], second.transitions)

    def test_rejects_a_transition_when_resolve_cannot_read_it_back_as_a_transition(self):
        first = AudioItem(108000, 108309)
        second = AudioItem(108309, 108610, transition_type="audio")

        with self.assertRaisesRegex(RuntimeError, "read-back"):
            apply_audio_seam_transitions(
                Timeline([first, second]), cut_frames=[108309], duration_frames=2,
            )

    def test_creates_a_duplicate_and_leaves_the_source_audio_untouched(self):
        source = Timeline([
            AudioItem(108000, 108309), AudioItem(108309, 108610), AudioItem(108610, 108645),
        ])
        project = Project(source)
        with tempfile.TemporaryDirectory() as directory:
            cfg = config(Path(directory))
            result = create_audio_seam_test(
                project, cfg, Registry(cfg.state_path), "Timeline 1", "ARPHE_ADV_SEAM_TEST",
                cut_frames=[108309, 108610], duration_frames=2,
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["source_preserved"])
        self.assertEqual("Timeline 1", result["source_timeline"])
        self.assertEqual("ARPHE_ADV_SEAM_TEST", result["created_timeline"])
        self.assertEqual([], source.audio_items[1].transitions)
        self.assertEqual([], source.audio_items[2].transitions)
        duplicate = project.current
        self.assertEqual(1, len(duplicate.audio_items[1].transitions))
        self.assertEqual(1, len(duplicate.audio_items[2].transitions))

    def test_deletes_the_test_timeline_and_restores_the_source_if_a_transition_is_rejected(self):
        source = Timeline([
            AudioItem(108000, 108309), AudioItem(108309, 108610),
            AudioItem(108610, 108645, accepts_transition=False),
        ])
        project = Project(source)
        with tempfile.TemporaryDirectory() as directory:
            cfg = config(Path(directory))
            with self.assertRaisesRegex(RuntimeError, "rifiutato"):
                create_audio_seam_test(
                    project, cfg, Registry(cfg.state_path), "Timeline 1", "ARPHE_ADV_SEAM_TEST",
                    cut_frames=[108309, 108610], duration_frames=2,
                )

        self.assertEqual([source], project.timelines)
        self.assertIs(source, project.current)
        self.assertEqual([], source.audio_items[1].transitions)


if __name__ == "__main__":
    unittest.main()
