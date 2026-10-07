from __future__ import annotations

from fractions import Fraction
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.editorial_workflows import EditorialBrief, load_workflow_registry  # noqa: E402
from bridge.format_contract import (  # noqa: E402
    ResolvedFormat,
    SourceFormat,
    apply_project_format,
    resolve_format_contract,
    verify_timeline_format,
)
from bridge.safety import ValidationError  # noqa: E402


class FakeSettings:
    def __init__(self, reject: str | None = None):
        self.settings = {}
        self.reject = reject
        self.calls = []

    def SetSetting(self, key, value):
        self.calls.append((key, value))
        if key == self.reject:
            return False
        self.settings[key] = value
        return True

    def GetSetting(self, key):
        return self.settings.get(key)


def brief(workflow_id: str, format_request=None, primary="source-a"):
    workflows = load_workflow_registry(ROOT / "editorial_workflows.json")
    workflow = workflows.workflows[workflow_id]
    return EditorialBrief(
        brief_id="brief-1",
        workflow_id=workflow_id,
        workflow_version=workflow.version,
        operator_role="SEGRETERIA",
        primary_source=primary,
        requested_outputs=("publishable",),
        format_request=dict(format_request or {}),
        answers={},
        unresolved_questions=(),
    )


class FormatContractTests(unittest.TestCase):
    def test_arphe_podcast_preserves_source_dimensions_and_rate(self):
        contract = resolve_format_contract(
            brief("ARPHE_PODCAST_REELS_CTA"),
            [SourceFormat(3840, 2160, Fraction(25, 1))],
        )
        self.assertEqual((3840, 2160, Fraction(25), Fraction(25)),
                         (contract.width, contract.height, contract.project_rate, contract.playback_rate))

    def test_carabellese_forces_1080p_and_preserves_fractional_source_rate(self):
        contract = resolve_format_contract(
            brief("CARABELLESE_YOUTUBE_CLEANUP"),
            [SourceFormat(4096, 2160, Fraction(30000, 1001))],
        )
        self.assertEqual((1920, 1080), (contract.width, contract.height))
        self.assertEqual(Fraction(30000, 1001), contract.project_rate)
        self.assertEqual(contract.project_rate, contract.playback_rate)

    def test_vertical_forces_1080x1920_30_and_playback_30(self):
        contract = resolve_format_contract(
            brief("ARPHE_VERTICAL_SOCIAL"),
            [SourceFormat(1920, 1080, Fraction(25))],
        )
        self.assertEqual(ResolvedFormat(1080, 1920, Fraction(30), Fraction(30)), contract)

    def test_read_only_playback_rate_is_never_written(self):
        project = FakeSettings()
        project.settings["timelinePlaybackFrameRate"] = "30"
        result = apply_project_format(project, ResolvedFormat(1080, 1920, Fraction(30), Fraction(30)))
        self.assertNotIn(("timelinePlaybackFrameRate", "30"), project.calls)
        self.assertEqual("30", result["timelinePlaybackFrameRate"])

    def test_readback_mismatch_raises_before_editing(self):
        project = FakeSettings()
        contract = ResolvedFormat(1920, 1080, Fraction(30000, 1001), Fraction(30000, 1001))
        project.settings["timelinePlaybackFrameRate"] = "29.97"
        apply_project_format(project, contract)
        timeline = FakeSettings()
        timeline.settings.update(project.settings)
        timeline.settings["timelineResolutionWidth"] = "1280"
        with self.assertRaisesRegex(ValidationError, "read-back"):
            verify_timeline_format(project, timeline, contract)

    def test_mixed_sources_without_confirmed_primary_rate_fail_closed(self):
        with self.assertRaisesRegex(ValidationError, "primaria"):
            resolve_format_contract(
                brief("ARPHE_PODCAST_REELS_CTA", primary=None),
                [
                    SourceFormat(1920, 1080, Fraction(25)),
                    SourceFormat(1920, 1080, Fraction(30)),
                ],
            )


if __name__ == "__main__":
    unittest.main()
