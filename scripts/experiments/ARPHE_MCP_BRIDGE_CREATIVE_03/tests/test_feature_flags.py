from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402
from bridge.feature_flags import report  # noqa: E402


class Fake:
    def GetMediaPool(self):
        return self

    def __getattr__(self, name):
        if name in {"CreateProject", "LoadProject", "SaveProject",
                    "GetCurrentProject", "GetProjectListInCurrentFolder", "SetCurrentTimeline",
                    "GetTimelineCount", "GetTimelineByIndex", "GetSetting", "SetSetting",
                    "CreateEmptyTimeline", "ImportMedia",
                    "AppendToTimeline", "InsertFusionCompositionIntoTimeline",
                    "SetCurrentRenderFormatAndCodec", "SetRenderSettings", "AddRenderJob", "StartRendering"}:
            return lambda *_args: True
        raise AttributeError(name)


class FeatureFlagTests(unittest.TestCase):
    def test_flags_separate_enabled_available_and_validated(self):
        config = CreativeConfig(Path("config"), Path("assets"), Path("renders"), Path("state"), Path("audit"),
                                dict(DEFAULT_PALETTE), dict(DEFAULT_FLAGS), frozenset(), frozenset(), "mp4", "H264")
        capabilities = report(config, Fake(), Fake(), Fake())
        self.assertTrue(capabilities["CAP_PROJECT"]["active"])
        self.assertFalse(capabilities["CAP_PROJECT"]["validated"])
        self.assertTrue(capabilities["CAP_TIMELINE"]["active"])
        self.assertFalse(capabilities["CAP_FUSION"]["active"])
        self.assertTrue(capabilities["CAP_FUSION"]["technically_available"])
        self.assertEqual("PENDING", capabilities["CAP_FUSION"]["status"])


if __name__ == "__main__":
    unittest.main()
