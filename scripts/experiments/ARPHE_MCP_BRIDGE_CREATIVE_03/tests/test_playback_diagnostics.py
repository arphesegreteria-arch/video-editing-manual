from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.playback_diagnostics import collect_playback_diagnostics  # noqa: E402


class FakeMediaPoolItem:
    def __init__(self, properties):
        self.properties = properties

    def GetClipProperty(self):
        return self.properties


class FakeTimelineItem:
    def __init__(self, properties):
        self.media_pool_item = FakeMediaPoolItem(properties)

    def GetMediaPoolItem(self):
        return self.media_pool_item


class FakeTimeline:
    def GetName(self):
        return "Timeline 1"

    def GetSetting(self):
        return {
            "timelineFrameRate": "30",
            "timelinePlaybackFrameRate": "30",
            "timelineResolutionWidth": "1920",
            "timelineResolutionHeight": "1080",
            "unrelatedSecret": "must-not-leak",
        }

    def GetTrackCount(self, track_type):
        return 1 if track_type in {"video", "audio"} else 0

    def GetItemListInTrack(self, track_type, index):
        if track_type != "video" or index != 1:
            return []
        return [
            FakeTimelineItem({
                "File Name": "example.mp4",
                "File Path": "C:/Users/private/Videos/example.mp4",
                "Video Codec": "H.264 High L4.1",
                "Audio Codec": "AAC",
                "Resolution": "1920x1080",
                "FPS": "30",
                "Audio Sample Rate": "48000",
                "privateMetadata": "must-not-leak",
            })
        ]


class FakeProject:
    def GetName(self):
        return "Project 1"

    def GetSetting(self):
        return {
            "timelineFrameRate": "30",
            "timelinePlaybackFrameRate": "30",
            "timelineResolutionWidth": "1920",
            "timelineResolutionHeight": "1080",
            "proxyMediaFormat": "DNxHR SQ",
            "secretSetting": "must-not-leak",
        }


class FakeResolve:
    def GetProductName(self):
        return "DaVinci Resolve Studio"

    def GetVersionString(self):
        return "21.0.4.5"

    def GetCurrentPage(self):
        return "edit"


class PlaybackDiagnosticTests(unittest.TestCase):
    def test_collects_portable_resolve_and_clip_diagnostics_without_paths(self):
        result = collect_playback_diagnostics(
            FakeResolve(), FakeProject(), FakeTimeline(), "PC_PERSONALE",
            executable_finder=lambda _name: None,
        )

        self.assertTrue(result["ok"])
        self.assertEqual("PC_PERSONALE", result["workstation_id"])
        self.assertEqual("DaVinci Resolve Studio", result["resolve"]["product_name"])
        self.assertEqual("30", result["timeline"]["settings"]["timelinePlaybackFrameRate"])
        self.assertEqual("H.264 High L4.1", result["media_samples"][0]["Video Codec"])
        self.assertNotIn("File Path", result["media_samples"][0])
        self.assertNotIn("privateMetadata", result["media_samples"][0])
        self.assertNotIn("secretSetting", result["project"]["settings"])

    def test_reports_optional_nvidia_probe_without_assuming_nvidia_exists(self):
        missing = collect_playback_diagnostics(
            FakeResolve(), FakeProject(), FakeTimeline(), "PC_SEGRETERIA",
            executable_finder=lambda _name: None,
        )
        self.assertFalse(missing["system"]["nvidia_smi"]["available"])
        self.assertEqual("executable_not_found", missing["system"]["nvidia_smi"]["reason"])

        def runner(command, timeout):
            self.assertEqual(3.0, timeout)
            self.assertTrue(command[1].startswith("--query-gpu=name,driver_version,memory.total"))
            return "NVIDIA GeForce RTX 3060 Ti, 581.29, 8192, 4, 0\n"

        present = collect_playback_diagnostics(
            FakeResolve(), FakeProject(), FakeTimeline(), "PC_PERSONALE",
            executable_finder=lambda name: "C:/NVIDIA/nvidia-smi.exe" if name == "nvidia-smi" else None,
            command_runner=runner,
        )
        self.assertTrue(present["system"]["nvidia_smi"]["available"])
        self.assertEqual(
            "NVIDIA GeForce RTX 3060 Ti",
            present["system"]["nvidia_smi"]["gpus"][0]["name"],
        )
        self.assertEqual(
            "581.29",
            present["system"]["nvidia_smi"]["gpus"][0]["driver_version"],
        )

    def test_declares_preferences_that_resolve_scripting_cannot_read(self):
        result = collect_playback_diagnostics(
            FakeResolve(), FakeProject(), FakeTimeline(), "PC_PERSONALE",
            executable_finder=lambda _name: None,
        )

        unavailable = result["not_exposed_by_resolve_api"]
        self.assertIn("gpu_processing_mode", unavailable)
        self.assertIn("decode_h264_h265_hardware_acceleration", unavailable)
        self.assertIn("audio_output_device_and_buffer", unavailable)
        self.assertFalse(result["writes_performed"])


if __name__ == "__main__":
    unittest.main()
