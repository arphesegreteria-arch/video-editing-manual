from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.media_verification import (MediaProbe, RenderExpectation, probe_media,
                                       verify_and_promote_batch, verify_media)  # noqa: E402
from bridge.registry import Registry  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402
from tests.test_render_batches import configured, fixtures  # noqa: E402
from bridge.render_batches import create_render_batch  # noqa: E402


CARRIER = ROOT / "assets" / "arphe_fusion_carrier_5m.mp4"


class MediaVerificationTests(unittest.TestCase):
    def test_probe_reads_existing_video_fixture_without_decoding_frames(self):
        probe = probe_media(CARRIER)
        self.assertEqual(("mp4", "h264", 64, 64, Fraction(30), Fraction(300), None),
                         (probe.container, probe.video_codec, probe.width, probe.height,
                          probe.frame_rate, probe.duration_seconds, probe.audio_codec))

    def test_probe_distinguishes_mov_from_mp4_by_delivery_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            mov = Path(directory) / "master.mov"; shutil.copy2(CARRIER, mov)
            self.assertEqual("mov", probe_media(mov).container)

    def test_fractional_frame_rate_compares_rationally(self):
        probe = MediaProbe("mp4", "h264", 1920, 1080, Fraction(30000, 1001), Fraction(10), "aac", 48000)
        expected = RenderExpectation("mp4", "h264", 1920, 1080, Fraction(30000, 1001), Fraction(10), True, "aac", 48000)
        self.assertEqual([], verify_media(probe, expected))

    def test_wrong_resolution_codec_duration_or_missing_audio_blocks_delivery(self):
        expected = RenderExpectation("mp4", "h264", 1920, 1080, Fraction(30), Fraction(10), True, "aac", 48000,
                                     video_profile="High")
        probe = MediaProbe("mov", "hevc", 1280, 720, Fraction(25), Fraction(12), None, None,
                           video_profile="Main")
        issues = verify_media(probe, expected)
        for label in ("container", "video_codec", "video_profile", "resolution", "frame_rate", "duration", "audio"):
            self.assertTrue(any(label in issue for issue in issues), issues)

    def _rendering_batch(self, root: Path):
        registry = Registry(root / "state.json")
        batch = create_render_batch(*fixtures(), "ARPHE_PROJECT", ("ARPHE_MAIN",), ("ARPHE_OUTPUT",), "PC_PERSONALE")
        staging = root / "renders" / "staging" / batch.batch_id; staging.mkdir(parents=True)
        batch = replace(batch, status="RENDERING", created_job_ids=("job-1",),
                        expected_outputs=("ARPHE_OUTPUT.mp4",), staging_directory=str(staging),
                        evidence={"expected_duration_seconds": "300"})
        registry.save_render_batch(batch)
        shutil.copy2(CARRIER, staging / "ARPHE_OUTPUT.mp4")
        project = type("Project", (), {
            "GetRenderJobList": lambda self: [{"JobId": "job-1"}],
            "GetRenderJobStatus": lambda self, job_id: {"JobId": job_id, "JobStatus": "Complete"},
        })()
        return registry, batch, project

    def test_failed_verify_retains_staging_and_marks_batch_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); registry, batch, project = self._rendering_batch(root)
            with self.assertRaises(ValidationError):
                verify_and_promote_batch(project, configured(root), registry, batch.batch_id)
            self.assertTrue(Path(batch.staging_directory).exists())
            self.assertEqual("FAILED_VERIFY", registry.render_batch(batch.batch_id).status)

    def test_verified_file_moves_atomically_and_collision_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); registry, batch, project = self._rendering_batch(root)
            good = MediaProbe("mp4", "h264", 1920, 1080, Fraction(30000, 1001), Fraction(300), "aac", 48000,
                              video_profile="High")
            with patch("bridge.media_verification.probe_media", return_value=good):
                result = verify_and_promote_batch(project, configured(root), registry, batch.batch_id)
            self.assertTrue(result["ok"])
            self.assertTrue((root / "renders" / "publishable" / "ARPHE_OUTPUT.mp4").is_file())
            self.assertEqual("VERIFIED", registry.render_batch(batch.batch_id).status)
            registry2, batch2, project2 = self._rendering_batch(root)
            with patch("bridge.media_verification.probe_media", return_value=good):
                with self.assertRaisesRegex(ValidationError, "Collisione"):
                    verify_and_promote_batch(project2, configured(root), registry2, batch2.batch_id)
            self.assertTrue((Path(batch2.staging_directory) / "ARPHE_OUTPUT.mp4").is_file())

    def test_restart_can_verify_existing_rendering_batch_without_requeue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); registry, batch, project = self._rendering_batch(root)
            restarted = Registry(registry.path)
            good = MediaProbe("mp4", "h264", 1920, 1080, Fraction(30000, 1001), Fraction(300), "aac", 48000,
                              video_profile="High")
            with patch("bridge.media_verification.probe_media", return_value=good):
                self.assertTrue(verify_and_promote_batch(project, configured(root), restarted, batch.batch_id)["ok"])

    def test_multi_file_promotion_rolls_back_if_second_move_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); registry, batch, project = self._rendering_batch(root)
            staging = Path(batch.staging_directory)
            shutil.copy2(staging / "ARPHE_OUTPUT.mp4", staging / "SECOND.mp4")
            batch = replace(batch, expected_outputs=("ARPHE_OUTPUT.mp4", "SECOND.mp4"))
            batch = replace(batch, status="VERIFYING")
            registry.save_render_batch(batch)
            good = MediaProbe("mp4", "h264", 1920, 1080, Fraction(30000, 1001), Fraction(300), "aac", 48000,
                              video_profile="High")
            real_replace = __import__("os").replace
            calls = 0
            def fail_second(source, target):
                nonlocal calls
                calls += 1
                if calls == 2: raise PermissionError("locked")
                return real_replace(source, target)
            with patch("bridge.media_verification.probe_media", return_value=good), \
                 patch("bridge.media_verification.os.replace", side_effect=fail_second), \
                 patch("bridge.media_verification.shutil.copy2", side_effect=PermissionError("locked")):
                with self.assertRaises(PermissionError):
                    verify_and_promote_batch(project, configured(root), registry, batch.batch_id)
            self.assertTrue((staging / "ARPHE_OUTPUT.mp4").exists())
            self.assertFalse((root / "renders" / "publishable" / "ARPHE_OUTPUT.mp4").exists())


if __name__ == "__main__":
    unittest.main()
