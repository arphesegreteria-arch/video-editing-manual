from __future__ import annotations

import inspect
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402
from bridge.readability_approvals import approve_readability  # noqa: E402
from bridge.registry import Registry  # noqa: E402
from bridge.review_workflow import (  # noqa: E402
    add_guarded_review_card,
    create_guarded_review_sequence,
    inspect_sequence_readability,
)
from bridge import server  # noqa: E402
from bridge.tool_catalog import EXPOSED_TOOL_NAMES  # noqa: E402


class ReadyMeasurer:
    available = True
    unavailable_reason = ""

    def font_available(self, _family: str, _weight: int) -> bool:
        return True

    def measure_text(self, text: str, _family: str, _weight: int, font_size: float) -> float:
        return len(text) * font_size * 0.01


class MissingWeightMeasurer(ReadyMeasurer):
    def font_available(self, family: str, weight: int) -> bool:
        return not (family == "Satoshi" and weight == 500)


class ResolveFake:
    def __init__(self, settings: dict[str, str], name: str = "ARPHE_TEST"):
        self.settings = dict(settings)
        self.name = name
        self.insert_calls = 0
        self.add_tool_calls = 0

    def GetSetting(self, key):
        return self.settings.get(key)

    def GetName(self):
        return self.name

    def InsertFusionCompositionIntoTimeline(self, *_args):
        self.insert_calls += 1
        return self

    def AddTool(self, *_args):
        self.add_tool_calls += 1
        return self


SETTINGS = {
    "timelineResolutionWidth": "1080",
    "timelineResolutionHeight": "1920",
    "timelineFrameRate": "30",
    "timelinePlaybackFrameRate": "30",
}


def review_words(count: int) -> str:
    return " ".join(f"w{index}" for index in range(count))


class ReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        flags = dict(DEFAULT_FLAGS)
        flags.update({"CAP_REVIEW": True, "CAP_FUSION": True, "CAP_READABILITY_GUARD": True})
        self.config = CreativeConfig(
            path=base / "config.json",
            asset_root=base / "assets",
            render_root=base / "renders",
            state_path=base / "state.json",
            audit_log_path=base / "audit.jsonl",
            palette=dict(DEFAULT_PALETTE),
            flags=flags,
            allowed_projects=frozenset(),
            allowed_timelines=frozenset(),
            render_format="mp4",
            render_codec="H264",
            workstation_id="PC_PERSONALE",
        )
        self.registry = Registry(self.config.state_path)
        self.project = ResolveFake(SETTINGS)
        self.timeline = ResolveFake(SETTINGS)

    def tearDown(self):
        self.temporary.cleanup()

    def create(self, reviews, token=None, total=0):
        return create_guarded_review_sequence(
            self.project,
            self.timeline,
            self.config,
            self.registry,
            "READABILITY_TEST",
            reviews,
            total,
            "cream",
            None,
            None,
            token,
        )

    def assert_zero_writes(self):
        self.assertEqual(self.project.insert_calls + self.timeline.insert_calls, 0)
        self.assertEqual(self.project.add_tool_calls + self.timeline.add_tool_calls, 0)

    def test_font_overflow_fps_contract_capability_and_stale_approval_are_zero_write(self):
        cases = []
        cases.append(("font", MissingWeightMeasurer(), None, None))
        cases.append(("overflow", ReadyMeasurer(), None, [{"text": "x" * 100000, "stars": 5}]))
        project_settings = dict(SETTINGS)
        project_settings["timelineFrameRate"] = "24"
        cases.append(("project-fps", ReadyMeasurer(), (project_settings, SETTINGS), None))
        timeline_settings = dict(SETTINGS)
        timeline_settings["timelineFrameRate"] = "24"
        cases.append(("timeline-fps", ReadyMeasurer(), (SETTINGS, timeline_settings), None))
        playback_settings = dict(SETTINGS)
        playback_settings["timelinePlaybackFrameRate"] = "24"
        cases.append(("playback-fps", ReadyMeasurer(), (playback_settings, SETTINGS), None))

        for label, measurer, settings_pair, reviews_override in cases:
            with self.subTest(label=label):
                self.project = ResolveFake((settings_pair or (SETTINGS, SETTINGS))[0])
                self.timeline = ResolveFake((settings_pair or (SETTINGS, SETTINGS))[1])
                with patch("bridge.review_workflow.WindowsGdiTextMeasurer", return_value=measurer), patch(
                    "bridge.review_workflow.create_review_sequence"
                ) as primitive:
                    with self.assertRaises(Exception):
                        self.create(reviews_override or [{"text": "Testo sintetico.", "stars": 5}])
                    primitive.assert_not_called()
                self.assert_zero_writes()

        self.project = ResolveFake(SETTINGS)
        self.timeline = ResolveFake(SETTINGS)
        disabled = dict(self.config.flags)
        disabled["CAP_READABILITY_GUARD"] = False
        self.config = type(self.config)(**{**self.config.__dict__, "flags": disabled})
        with patch("bridge.review_workflow.WindowsGdiTextMeasurer", return_value=ReadyMeasurer()):
            with self.assertRaises(Exception):
                self.create([{"text": "Testo sintetico.", "stars": 5}])
        self.assert_zero_writes()

        self.config = type(self.config)(**{**self.config.__dict__, "flags": {**disabled, "CAP_READABILITY_GUARD": True}})
        long_reviews = [{"text": review_words(45), "stars": 5}]
        with patch("bridge.review_workflow.WindowsGdiTextMeasurer", return_value=ReadyMeasurer()):
            assessment = inspect_sequence_readability(self.timeline, self.config, long_reviews)
            approval = approve_readability(
                self.registry,
                self.config.workstation_id,
                assessment.fingerprint,
                [{"review_index": 0, "decision": "LONG_SINGLE"}],
                "ALESSIO",
            )
            long_reviews[0]["text"] += "!"
            with self.assertRaisesRegex(Exception, "STALE_APPROVAL"):
                self.create(long_reviews, approval.token)
        self.assert_zero_writes()

        with patch("bridge.review_workflow.CONTRACT_PATH", Path(self.temporary.name) / "missing.json"):
            with self.assertRaisesRegex(Exception, "CONTRACT_MISMATCH"):
                self.create([{"text": "Testo sintetico.", "stars": 5}])
        self.assert_zero_writes()

    def test_pass_long_single_and_split_forward_assessed_layouts(self):
        captured = []

        def primitive(*args, **kwargs):
            captured.append((args, kwargs))
            return {"ok": True, "cards": len(args[5]), "reviews": args[5]}

        with patch("bridge.review_workflow.WindowsGdiTextMeasurer", return_value=ReadyMeasurer()), patch(
            "bridge.review_workflow.create_review_sequence", side_effect=primitive
        ):
            short = [{"text": "Testo sintetico.", "stars": 5}]
            self.assertTrue(self.create(short)["ok"])
            short_layout = captured[-1][1]["readability_layouts"][0]
            self.assertEqual(short_layout["duration_frames"], 90)
            self.assertEqual(short_layout["safe_area"]["right"], 0.84)
            self.assertEqual(short_layout["typography"]["heading"]["weight"], 300)

            long_reviews = [{"text": review_words(45), "stars": 5}]
            assessment = inspect_sequence_readability(self.timeline, self.config, long_reviews)
            approval = approve_readability(
                self.registry,
                self.config.workstation_id,
                assessment.fingerprint,
                [{"review_index": 0, "decision": "LONG_SINGLE"}],
                "ALESSIO",
            )
            self.assertTrue(self.create(long_reviews, approval.token)["ok"])
            self.assertEqual(captured[-1][1]["readability_layouts"][0]["duration_frames"], 390)

            source = review_words(23) + ". " + review_words(23) + "."
            split_reviews = [{"text": source, "stars": 5}]
            split_assessment = inspect_sequence_readability(self.timeline, self.config, split_reviews)
            offset = split_assessment.reviews[0].suggested_split
            split_approval = approve_readability(
                self.registry,
                self.config.workstation_id,
                split_assessment.fingerprint,
                [{"review_index": 0, "decision": "VERBATIM_SPLIT", "split_offset": offset}],
                "ALESSIO",
            )
            result = self.create(split_reviews, split_approval.token)
            self.assertEqual(result["cards"], 2)
            self.assertEqual("".join(item["text"] for item in result["reviews"]), source)
            self.assertEqual(len(captured[-1][1]["readability_layouts"]), 2)

    def test_single_card_cannot_undercut_assessed_duration(self):
        with patch("bridge.review_workflow.WindowsGdiTextMeasurer", return_value=ReadyMeasurer()), patch(
            "bridge.review_workflow.add_review_card"
        ) as primitive:
            with self.assertRaises(Exception):
                add_guarded_review_card(
                    self.project,
                    self.timeline,
                    self.config,
                    self.registry,
                    "COMP",
                    review_words(20),
                    5,
                    0,
                    100,
                    "cream",
                    None,
                    None,
                    None,
                )
            primitive.assert_not_called()

    def test_mcp_surface_is_guarded_and_redacted(self):
        self.assertIn("inspect_review_readability", EXPOSED_TOOL_NAMES)
        self.assertIn("approve_review_readability", EXPOSED_TOOL_NAMES)
        for function in (
            server.add_review_card,
            server.create_review_sequence,
            server.create_review_sequence_v2,
        ):
            self.assertIn("readability_approval_token", inspect.signature(function).parameters)

        secret = "RECENSIONE-DA-NON-REGISTRARE"
        with patch("bridge.review_workflow.WindowsGdiTextMeasurer", return_value=ReadyMeasurer()):
            result = inspect_sequence_readability(
                self.timeline,
                self.config,
                [{"text": secret, "stars": 5}],
            ).to_dict()
        self.assertNotIn(secret, str(result))


if __name__ == "__main__":
    unittest.main()
