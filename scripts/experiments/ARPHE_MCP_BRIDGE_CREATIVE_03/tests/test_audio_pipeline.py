from __future__ import annotations

import json
import hashlib
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import wave


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.audio_tools import allowed_audio, audio_job  # noqa: E402
from bridge.audio_provenance import file_sha256, media_fingerprint, verify_audio_manifest  # noqa: E402
from bridge.audio_worker import DISTANT_PRESET, LEVEL_PRESET, NATURAL_PRESET, process_audio  # noqa: E402
from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402


def config(root: Path) -> CreativeConfig:
    media = root / "media"
    transcripts = root / "transcripts"
    audio = root / "audio"
    jobs = root / "jobs"
    for path in (media, transcripts, audio, jobs):
        path.mkdir()
    flags = dict(DEFAULT_FLAGS)
    flags["CAP_LONGFORM"] = True
    return CreativeConfig(
        path=root / "config.json", asset_root=root / "assets", render_root=root / "renders",
        state_path=root / "state.json", audit_log_path=root / "audit.jsonl",
        palette=dict(DEFAULT_PALETTE), flags=flags, allowed_projects=frozenset(),
        allowed_timelines=frozenset(), render_format="mp4", render_codec="H264",
        media_roots=(media,), transcript_root=transcripts, audio_root=audio, audio_jobs_root=jobs,
    )


def write_worker_job(job: Path, source: Path, output: Path, preset: str) -> None:
    job.write_text(json.dumps({
        "schema": "ARPHE_AUDIO_JOB_V2",
        "job_id": "audio_0123456789abcdef",
        "status": "QUEUED",
        "progress_percent": 0,
        "preset": preset,
        "source_name": source.name,
        "source_fingerprint": hashlib.sha256(source.read_bytes()).hexdigest(),
        "output_path": str(output),
    }), encoding="utf-8")


class AudioPipelineTests(unittest.TestCase):
    def test_worker_creates_synchronized_pcm_wav(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output, job = root / "source.wav", root / "output.wav", root / "job.json"
            with wave.open(str(source), "wb") as handle:
                handle.setnchannels(2)
                handle.setsampwidth(2)
                handle.setframerate(48000)
                samples = []
                for index in range(48000):
                    value = int(3000 * math.sin(2 * math.pi * 440 * index / 48000))
                    samples.append(struct.pack("<hh", value, value))
                handle.writeframes(b"".join(samples))
            write_worker_job(job, source, output, "ARPHE_DIALOGUE_CLEAN_V1")
            process_audio(source, output, job)
            state = json.loads(job.read_text(encoding="utf-8"))
            self.assertEqual("ARPHE_AUDIO_JOB_V2", state["schema"])
            self.assertEqual("COMPLETED", state["status"])
            self.assertAlmostEqual(1.0, state["output_duration_seconds"], places=2)
            self.assertAlmostEqual(0.0, state["sync_delta_seconds"], places=2)
            self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), state["output_sha256"])
            self.assertTrue(output.is_file())

    def test_level_preset_reduces_strong_weak_dialogue_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output, job = root / "source.wav", root / "output.wav", root / "job.json"
            with wave.open(str(source), "wb") as handle:
                handle.setnchannels(2)
                handle.setsampwidth(2)
                handle.setframerate(48000)
                samples = []
                for index in range(48000 * 6):
                    amplitude = 12000 if index < 48000 * 3 else 1500
                    value = int(amplitude * math.sin(2 * math.pi * 220 * index / 48000))
                    samples.append(struct.pack("<hh", value, value))
                handle.writeframes(b"".join(samples))
            write_worker_job(job, source, output, LEVEL_PRESET)
            process_audio(source, output, job, LEVEL_PRESET)
            with wave.open(str(output), "rb") as handle:
                data = handle.readframes(handle.getnframes())
            values = struct.unpack("<" + "h" * (len(data) // 2), data)
            mono = values[::2]
            midpoint = len(mono) // 2
            strong = math.sqrt(sum(value * value for value in mono[:midpoint]) / midpoint)
            weak = math.sqrt(sum(value * value for value in mono[midpoint:]) / (len(mono) - midpoint))
            self.assertLess(strong / weak, 5.0)
            state = json.loads(job.read_text(encoding="utf-8"))
            self.assertAlmostEqual(6.0, state["output_duration_seconds"], places=2)

    def test_distant_preset_recovers_more_quiet_dialogue_than_level_v2(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.wav"
            with wave.open(str(source), "wb") as handle:
                handle.setnchannels(2)
                handle.setsampwidth(2)
                handle.setframerate(48000)
                samples = []
                for index in range(48000 * 6):
                    amplitude = 10000 if index < 48000 * 3 else 900
                    value = int(amplitude * math.sin(2 * math.pi * 220 * index / 48000))
                    samples.append(struct.pack("<hh", value, value))
                handle.writeframes(b"".join(samples))

            quiet_rms = {}
            for preset in (LEVEL_PRESET, DISTANT_PRESET):
                output, job = root / f"{preset}.wav", root / f"{preset}.json"
                write_worker_job(job, source, output, preset)
                process_audio(source, output, job, preset)
                with wave.open(str(output), "rb") as handle:
                    data = handle.readframes(handle.getnframes())
                values = struct.unpack("<" + "h" * (len(data) // 2), data)[::2]
                quiet = values[len(values) // 2:]
                quiet_rms[preset] = math.sqrt(sum(value * value for value in quiet) / len(quiet))
                if preset == DISTANT_PRESET:
                    self.assertLessEqual(max(abs(value) for value in values), int(32768 * 0.81))

            self.assertGreater(quiet_rms[DISTANT_PRESET], quiet_rms[LEVEL_PRESET] * 1.15)

    def test_natural_preset_preserves_sync_without_hard_limiting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output, job = root / "source.wav", root / "output.wav", root / "job.json"
            with wave.open(str(source), "wb") as handle:
                handle.setnchannels(2)
                handle.setsampwidth(2)
                handle.setframerate(48000)
                samples = []
                for index in range(48000 * 2):
                    value = int(9000 * math.sin(2 * math.pi * 440 * index / 48000))
                    samples.append(struct.pack("<hh", value, value))
                handle.writeframes(b"".join(samples))
            write_worker_job(job, source, output, NATURAL_PRESET)
            process_audio(source, output, job, NATURAL_PRESET)
            state = json.loads(job.read_text(encoding="utf-8"))
            self.assertEqual("COMPLETED", state["status"])
            self.assertAlmostEqual(2.0, state["output_duration_seconds"], places=2)

    def test_audio_and_job_paths_are_allowlisted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = config(root)
            audio = cfg.audio_root / "clean.wav"
            audio.write_bytes(b"RIFF")
            self.assertEqual(audio.resolve(), allowed_audio(str(audio), cfg))
            outside = root / "outside.wav"
            outside.write_bytes(b"RIFF")
            with self.assertRaises(ValidationError):
                allowed_audio(str(outside), cfg)
            job_id = "audio_0123456789abcdef"
            (cfg.audio_jobs_root / f"{job_id}.json").write_text(
                json.dumps({"job_id": job_id, "status": "COMPLETED"}), encoding="utf-8")
            self.assertTrue(audio_job(cfg, job_id)["ok"])
            with self.assertRaises(ValidationError):
                audio_job(cfg, "../escape")

    def test_verified_audio_requires_complete_matching_v2_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = config(root)
            source = cfg.media_roots[0] / "source.mov"
            source.write_bytes(b"source-media")
            output = cfg.audio_root / "clean.wav"
            output.write_bytes(b"RIFF-valid-audio")
            job_id = "audio_0123456789abcdef"
            manifest = {
                "schema": "ARPHE_AUDIO_JOB_V2", "job_id": job_id,
                "status": "COMPLETED", "preset": NATURAL_PRESET,
                "source_fingerprint": hashlib.sha256(b"source-media").hexdigest(),
                "output_path": str(output.resolve()),
                "output_sha256": hashlib.sha256(b"RIFF-valid-audio").hexdigest(),
                "source_duration_seconds": 60.0,
                "output_duration_seconds": 60.0,
                "sync_delta_seconds": 0.0,
                "sample_rate": 48000, "channels": 2,
            }
            (cfg.audio_jobs_root / f"{job_id}.json").write_text(
                json.dumps(manifest), encoding="utf-8")

            verified = verify_audio_manifest(cfg, job_id, media_fingerprint(source))
            expected_output_hash = file_sha256(output)

        self.assertEqual(output.resolve(), verified.path)
        self.assertEqual(job_id, verified.audio_job_id)
        self.assertEqual(expected_output_hash, verified.output_sha256)

    def test_verified_audio_exposes_validated_silence_windows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = config(root)
            source = cfg.media_roots[0] / "source.mov"
            source.write_bytes(b"source-media")
            output = cfg.audio_root / "clean.wav"
            output.write_bytes(b"RIFF-valid-audio")
            job_id = "audio_0123456789abcdef"
            manifest = {
                "schema": "ARPHE_AUDIO_JOB_V2", "job_id": job_id, "status": "COMPLETED",
                "preset": NATURAL_PRESET, "source_fingerprint": media_fingerprint(source),
                "output_path": str(output), "output_sha256": file_sha256(output),
                "source_duration_seconds": 60.0, "output_duration_seconds": 60.0,
                "sync_delta_seconds": 0.0, "sample_rate": 48000, "channels": 2,
                "silence_windows": [{"start": 1.0, "end": 2.0}, {"start": 4.0, "end": 5.5}],
            }
            (cfg.audio_jobs_root / f"{job_id}.json").write_text(json.dumps(manifest), encoding="utf-8")
            verified = verify_audio_manifest(cfg, job_id, media_fingerprint(source))
            self.assertEqual(((1.0, 2.0), (4.0, 5.5)), verified.silence_windows)

            manifest["silence_windows"] = [{"start": 2.0, "end": 1.0}]
            (cfg.audio_jobs_root / f"{job_id}.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "silence"):
                verify_audio_manifest(cfg, job_id, media_fingerprint(source))

    def test_invalid_audio_provenance_blocks_before_downstream_mutation(self):
        mutations: list[str] = []
        cases = ("foreign_source", "changed_wav", "excessive_sync", "legacy", "wrong_job_id", "missing")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                cfg = config(root)
                source = cfg.media_roots[0] / "source.mov"
                source.write_bytes(b"source-media")
                output = cfg.audio_root / "clean.wav"
                output.write_bytes(b"RIFF-valid-audio")
                job_id = "audio_0123456789abcdef"
                manifest = {
                    "schema": "ARPHE_AUDIO_JOB_V2", "job_id": job_id,
                    "status": "COMPLETED", "preset": NATURAL_PRESET,
                    "source_fingerprint": media_fingerprint(source),
                    "output_path": str(output.resolve()),
                    "output_sha256": file_sha256(output),
                    "source_duration_seconds": 60.0,
                    "output_duration_seconds": 60.0,
                    "sync_delta_seconds": 0.0,
                    "sample_rate": 48000, "channels": 2,
                }
                if case == "foreign_source":
                    manifest["source_fingerprint"] = "f" * 64
                elif case == "changed_wav":
                    manifest["output_sha256"] = "e" * 64
                elif case == "excessive_sync":
                    manifest["sync_delta_seconds"] = 0.04
                elif case == "legacy":
                    manifest["schema"] = "ARPHE_AUDIO_JOB_V1"
                elif case == "wrong_job_id":
                    manifest["job_id"] = "audio_fedcba9876543210"
                elif case == "missing":
                    output.unlink()
                (cfg.audio_jobs_root / f"{job_id}.json").write_text(
                    json.dumps(manifest), encoding="utf-8")

                with self.assertRaises(ValidationError):
                    verify_audio_manifest(cfg, job_id, media_fingerprint(source))
                self.assertEqual([], mutations)


if __name__ == "__main__":
    unittest.main()
