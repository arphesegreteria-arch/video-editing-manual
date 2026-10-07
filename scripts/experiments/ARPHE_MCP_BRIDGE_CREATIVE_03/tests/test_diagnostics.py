from __future__ import annotations

from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.diagnostic_tools import (capture_timeline_frames, _validate_offsets,
                                     frame_to_timecode)  # noqa: E402
from bridge.artifact_records import ArtifactStore  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402


class FakeTimeline:
    def __init__(self):
        self.timecode = "01:00:00:10"

    def GetName(self):
        return "ARPHE_TEST_TIMELINE"

    def GetStartFrame(self):
        return 108000

    def GetEndFrame(self):
        return 108150

    def GetSetting(self, name):
        return "30" if name == "timelineFrameRate" else None

    def GetCurrentTimecode(self):
        return self.timecode

    def SetCurrentTimecode(self, value):
        self.timecode = value
        return True


class FakeResolve:
    def __init__(self):
        self.page = "fusion"

    def GetCurrentPage(self):
        return self.page

    def OpenPage(self, page):
        self.page = page
        return True


class FakeProject:
    def GetName(self):
        return "ARPHE_TEST_PROJECT"

    def ExportCurrentFrameAsStill(self, path):
        Path(path).write_bytes(b"fake-png")
        return True


class FakeRegistry:
    def timeline_allowed(self, project, timeline):
        return project == "ARPHE_TEST_PROJECT" and timeline == "ARPHE_TEST_TIMELINE"


class DiagnosticTests(unittest.TestCase):
    @staticmethod
    def _config(root: Path):
        return SimpleNamespace(
            render_root=root,
            allowed_timelines=[],
            artifact_registry_path=root / "artifact_registry.json",
            workstation_id="PC_PERSONALE",
        )

    def test_frame_to_timecode_uses_absolute_timeline_frame(self):
        self.assertEqual("01:00:00:00", frame_to_timecode(108000, 30))
        self.assertEqual("01:00:04:29", frame_to_timecode(108149, 30))

    def test_offsets_are_bounded_and_deduplicated(self):
        start, fps, offsets = _validate_offsets(FakeTimeline(), [0, 1, 1, 149])
        self.assertEqual(108000, start)
        self.assertEqual(30, fps)
        self.assertEqual([0, 1, 149], offsets)

    def test_batch_and_range_limits(self):
        for invalid in ([], list(range(9)), [-1], [150], [True], [1.5]):
            with self.assertRaises(ValidationError):
                _validate_offsets(FakeTimeline(), invalid)

    def test_capture_restores_page_and_playhead_and_returns_images(self):
        resolve = FakeResolve()
        timeline = FakeTimeline()
        original_timecode = timeline.timecode
        with tempfile.TemporaryDirectory() as directory:
            config = self._config(Path(directory))
            result = capture_timeline_frames(
                resolve, FakeProject(), timeline, config, FakeRegistry(), [0, 2]
            )
            self.assertEqual(3, len(result))
            self.assertTrue(result[0]["ok"])
            self.assertEqual([0, 2], [entry["frame_offset"] for entry in result[0]["captures"]])
            self.assertTrue(result[0]["playhead_restored"])
            self.assertEqual("fusion", resolve.page)
            self.assertEqual(original_timecode, timeline.timecode)
            self.assertEqual(2, len(list((Path(directory) / "diagnostics").glob("*.jpg"))))
            records = ArtifactStore(config.artifact_registry_path, config.workstation_id).records()
            self.assertEqual(2, len(records))
            self.assertEqual({"DIAGNOSTIC_CAPTURE"}, {record.category for record in records})
            self.assertEqual({"capture_timeline_frames"}, {record.producer for record in records})

    def test_capture_does_not_prune_older_registered_or_unregistered_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            diagnostics = root / "diagnostics"
            diagnostics.mkdir()
            for index in range(65):
                (diagnostics / f"ARPHE_FRAME_OLD_{index:03d}.jpg").write_bytes(b"old")
            capture_timeline_frames(
                FakeResolve(), FakeProject(), FakeTimeline(), self._config(root), FakeRegistry(), [0]
            )
            self.assertEqual(66, len(list(diagnostics.glob("*.jpg"))))

    def test_registration_failure_removes_only_new_capture_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            diagnostics = root / "diagnostics"
            diagnostics.mkdir()
            existing = diagnostics / "ARPHE_FRAME_EXISTING.jpg"
            existing.write_bytes(b"keep")
            failing_store = SimpleNamespace(register_path=lambda *args, **kwargs: (_ for _ in ()).throw(OSError("registry locked")))
            with patch("bridge.diagnostic_tools.artifact_store_for", return_value=failing_store):
                with self.assertRaisesRegex(OSError, "registry locked"):
                    capture_timeline_frames(
                        FakeResolve(), FakeProject(), FakeTimeline(), self._config(root), FakeRegistry(), [0, 2]
                    )
            self.assertTrue(existing.is_file())
            self.assertEqual([existing], list(diagnostics.glob("*.jpg")))


if __name__ == "__main__":
    unittest.main()
