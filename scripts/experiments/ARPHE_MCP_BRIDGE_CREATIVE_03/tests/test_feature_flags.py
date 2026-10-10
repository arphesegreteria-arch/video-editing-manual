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
                    "GetName",
                    "GetTimelineCount", "GetTimelineByIndex", "GetSetting", "SetSetting",
                    "CreateEmptyTimeline", "ImportMedia",
                    "AppendToTimeline", "InsertFusionCompositionIntoTimeline",
                    "GetRootFolder", "GetClipList", "GetSubFolderList", "AddMarker",
                    "GetMarkers", "DeleteMarkerAtFrame", "GetUniqueId", "GetItemListInTrack",
                    "DuplicateTimeline",
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
        self.assertEqual("PARTIAL", capabilities["CAP_PROJECT"]["status"])
        self.assertEqual("PARTIAL", capabilities["CAP_TIMELINE"]["status"])
        self.assertFalse(capabilities["CAP_FUSION"]["active"])
        self.assertTrue(capabilities["CAP_FUSION"]["technically_available"])
        self.assertEqual("SUPPORTED", capabilities["CAP_FUSION"]["status"])
        self.assertTrue(capabilities["CAP_FUSION"]["validated"])
        self.assertFalse(capabilities["CAP_ARTIFACT_MAINTENANCE"]["active"])
        self.assertTrue(capabilities["CAP_ARTIFACT_MAINTENANCE"]["technically_available"])
        self.assertFalse(DEFAULT_FLAGS["CAP_READABILITY_GUARD"])
        self.assertFalse(capabilities["CAP_READABILITY_GUARD"]["active"])
        self.assertTrue(capabilities["CAP_READABILITY_GUARD"]["technically_available"])
        self.assertEqual("PARTIAL", capabilities["CAP_READABILITY_GUARD"]["status"])
        self.assertFalse(DEFAULT_FLAGS["CAP_EDITORIAL_SELECTION"])
        self.assertFalse(capabilities["CAP_EDITORIAL_SELECTION"]["active"])
        self.assertTrue(capabilities["CAP_EDITORIAL_SELECTION"]["technically_available"])
        self.assertFalse(DEFAULT_FLAGS["CAP_CARABELLESE_CLEANUP"])
        self.assertFalse(capabilities["CAP_CARABELLESE_CLEANUP"]["active"])
        self.assertTrue(capabilities["CAP_CARABELLESE_CLEANUP"]["technically_available"])
        self.assertFalse(DEFAULT_FLAGS["CAP_BRANDED_LONGFORM_EDITORIAL"])
        self.assertTrue(capabilities["CAP_BRANDED_LONGFORM_EDITORIAL"]["technically_available"])
        self.assertFalse(DEFAULT_FLAGS["CAP_WORKFLOW_CONTROL_PLANE"])
        self.assertFalse(capabilities["CAP_WORKFLOW_CONTROL_PLANE"]["active"])
        self.assertTrue(capabilities["CAP_WORKFLOW_CONTROL_PLANE"]["implemented"])


if __name__ == "__main__":
    unittest.main()
