from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.playback_diagnostics import (  # noqa: E402
    _windows_cpu_reader,
    collect_playback_diagnostics,
    collect_windows_audio_diagnostics,
    sample_playback_performance,
)


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
            "timelinePlaybackFrameRate": "24",
            "timelineResolutionWidth": "1920",
            "timelineResolutionHeight": "1080",
            "videoMonitorFormat": "HD 1080p 24",
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
    def test_default_windows_cpu_reader_can_be_constructed(self):
        reader = _windows_cpu_reader()
        self.assertTrue(callable(reader))
        self.assertIsNone(reader())

    def test_collects_portable_resolve_and_clip_diagnostics_without_paths(self):
        result = collect_playback_diagnostics(
            FakeResolve(), FakeProject(), FakeTimeline(), "PC_PERSONALE",
            executable_finder=lambda _name: None,
        )

        self.assertTrue(result.get("ok"))
        self.assertEqual("PC_PERSONALE", result["workstation_id"])
        self.assertEqual("DaVinci Resolve Studio", result["resolve"]["product_name"])
        self.assertEqual("24", result["timeline"]["settings"]["timelinePlaybackFrameRate"])
        self.assertTrue(result["likely_cause_found"])
        self.assertEqual("TIMELINE_PLAYBACK_RATE_MISMATCH", result["findings"][0]["code"])
        self.assertEqual(24.0, result["findings"][1]["evidence"]["monitor_fps"])
        self.assertEqual("H.264 High L4.1", result["media_samples"][0]["Video Codec"])
        self.assertNotIn("File Path", result["media_samples"][0])
        self.assertNotIn("privateMetadata", result["media_samples"][0])
        self.assertNotIn("secretSetting", result["project"]["settings"])

    def test_reports_optional_nvidia_probe_without_assuming_nvidia_exists(self):
        missing = collect_playback_diagnostics(
            FakeResolve(), FakeProject(), FakeTimeline(), "PC_SEGRETERIA",
            executable_finder=lambda _name: None,
        )
        self.assertIn("system", missing)
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
        self.assertEqual("NVIDIA GeForce RTX 3060 Ti", present["system"]["nvidia_smi"]["gpus"][0]["name"])
        self.assertEqual("581.29", present["system"]["nvidia_smi"]["gpus"][0]["driver_version"])

    def test_declares_preferences_that_resolve_scripting_cannot_read(self):
        result = collect_playback_diagnostics(
            FakeResolve(), FakeProject(), FakeTimeline(), "PC_PERSONALE",
            executable_finder=lambda _name: None,
        )

        self.assertIn("not_exposed_by_resolve_api", result)
        unavailable = result["not_exposed_by_resolve_api"]
        self.assertIn("gpu_processing_mode", unavailable)
        self.assertIn("decode_h264_h265_hardware_acceleration", unavailable)
        self.assertIn("audio_output_device_and_buffer", unavailable)
        self.assertFalse(result["writes_performed"])

    def test_samples_edit_playback_and_returns_compact_aggregates(self):
        now = [0.0]
        cpu_values = iter([10.0, 30.0, 20.0])
        memory_values = iter([40.0, 42.0, 41.0])
        gpu_values = iter([
            {"gpu_percent": 5.0, "decoder_percent": 0.0},
            {"gpu_percent": 25.0, "decoder_percent": 45.0},
            {"gpu_percent": 15.0, "decoder_percent": 30.0},
        ])

        def clock():
            return now[0]

        def sleeper(seconds):
            now[0] += seconds

        result = sample_playback_performance(
            FakeResolve(),
            "PC_PERSONALE",
            expected_page="edit",
            duration_seconds=1.0,
            interval_seconds=0.5,
            clock=clock,
            sleeper=sleeper,
            cpu_reader=lambda: next(cpu_values),
            memory_reader=lambda: next(memory_values),
            gpu_reader=lambda: next(gpu_values),
        )

        self.assertTrue(result.get("ok"))
        self.assertEqual("edit", result["scenario"])
        self.assertEqual(3, result["sample_count"])
        self.assertEqual(20.0, result["cpu_percent"]["average"])
        self.assertEqual(30.0, result["cpu_percent"]["maximum"])
        self.assertEqual(45.0, result["nvidia_decoder_percent"]["maximum"])
        self.assertEqual([], result["findings"])
        self.assertNotIn("samples", result)
        self.assertFalse(result["writes_performed"])

    def test_rejects_sampling_when_resolve_is_on_the_wrong_page(self):
        with self.assertRaises(ValueError):
            sample_playback_performance(
                FakeResolve(),
                "PC_PERSONALE",
                expected_page="fairlight",
                duration_seconds=1.0,
                interval_seconds=0.5,
                clock=lambda: 0.0,
                sleeper=lambda _seconds: None,
                cpu_reader=lambda: 0.0,
                memory_reader=lambda: 0.0,
                gpu_reader=lambda: None,
            )

    def test_collects_windows_audio_inventory_without_claiming_resolve_preferences(self):
        payload = (
            '{"audio_devices":[{"Name":"Realtek Audio","Status":"OK",'
            '"Manufacturer":"Realtek"}],"dpc_percent":2}'
        )

        def runner(command, timeout):
            self.assertEqual(5.0, timeout)
            self.assertIn("-NoProfile", command)
            return payload

        result = collect_windows_audio_diagnostics(
            executable_finder=lambda name: "powershell.exe" if name == "powershell" else None,
            command_runner=runner,
        )

        self.assertTrue(result.get("available"))
        self.assertEqual("Realtek Audio", result["devices"][0]["name"])
        self.assertEqual(2, result["dpc_percent_snapshot"])
        self.assertFalse(result["resolve_audio_preferences_available"])
        self.assertNotIn("command", result)


if __name__ == "__main__":
    unittest.main()

