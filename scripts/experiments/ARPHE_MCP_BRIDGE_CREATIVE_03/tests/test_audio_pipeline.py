from __future__ import annotations

import json
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
from bridge.audio_worker import process_audio  # noqa: E402
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
            job.write_text(json.dumps({"status": "QUEUED"}), encoding="utf-8")
            process_audio(source, output, job)
            state = json.loads(job.read_text(encoding="utf-8"))
            self.assertEqual("COMPLETED", state["status"])
            self.assertAlmostEqual(1.0, state["output_duration_seconds"], places=2)
            self.assertTrue(output.is_file())

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


if __name__ == "__main__":
    unittest.main()
