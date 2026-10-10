from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.carabellese_transcription import (  # noqa: E402
    get_carabellese_transcription_job,
    start_carabellese_transcription,
)
from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402
from bridge.transcription_worker import run_job, transcribe_checkpointed  # noqa: E402


def config(root: Path, workstation: str = "PC_PERSONALE") -> CreativeConfig:
    media = root / "media"
    transcripts = root / "transcripts"
    for path in (media, transcripts):
        path.mkdir(parents=True)
    flags = dict(DEFAULT_FLAGS)
    flags["CAP_CARABELLESE_CLEANUP"] = True
    return CreativeConfig(
        path=root / "config.json", asset_root=root / "assets", render_root=root / "renders",
        state_path=root / "state.json", audit_log_path=root / "audit.jsonl",
        palette=dict(DEFAULT_PALETTE), flags=flags, allowed_projects=frozenset(),
        allowed_timelines=frozenset(), render_format="mp4", render_codec="H264",
        media_roots=(media,), transcript_root=transcripts, workstation_id=workstation,
    )


def source(cfg: CreativeConfig, content: bytes = b"podcast-carabellese") -> Path:
    result = cfg.media_roots[0] / "podcast.mov"
    result.write_bytes(content)
    return result


class CarabelleseTranscriptionJobTests(unittest.TestCase):
    def test_outside_media_and_wrong_fingerprint_fail_before_process_creation(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            cfg = config(root)
            media = source(cfg)
            outside = root / "outside.mov"
            outside.write_bytes(b"outside")
            with patch("bridge.carabellese_transcription.subprocess.Popen") as launch:
                with self.assertRaises(ValidationError):
                    start_carabellese_transcription(cfg, str(outside), hashlib.sha256(b"outside").hexdigest())
                with self.assertRaisesRegex(ValidationError, "fingerprint"):
                    start_carabellese_transcription(cfg, str(media), "f" * 64)
            launch.assert_not_called()

    def test_model_and_language_are_allowlisted_before_process_creation(self):
        with tempfile.TemporaryDirectory() as raw_root:
            cfg = config(Path(raw_root))
            media = source(cfg)
            fingerprint = hashlib.sha256(media.read_bytes()).hexdigest()
            with patch("bridge.carabellese_transcription.subprocess.Popen") as launch:
                with self.assertRaisesRegex(ValidationError, "modello"):
                    start_carabellese_transcription(cfg, str(media), fingerprint, model="../../cmd")
                with self.assertRaisesRegex(ValidationError, "lingua"):
                    start_carabellese_transcription(cfg, str(media), fingerprint, language="it;calc")
            launch.assert_not_called()

    def test_start_creates_workstation_local_manifest_and_uses_safe_worker_command(self):
        with tempfile.TemporaryDirectory() as raw_root:
            cfg = config(Path(raw_root))
            media = source(cfg)
            fingerprint = hashlib.sha256(media.read_bytes()).hexdigest()
            with patch("bridge.carabellese_transcription.subprocess.Popen") as launch:
                launch.return_value.pid = 4321
                result = start_carabellese_transcription(cfg, str(media), fingerprint)

            self.assertRegex(result["job_id"], r"^carabellese_tx_[0-9a-f]{16}$")
            job_root = cfg.transcript_root / ".carabellese_jobs" / "PC_PERSONALE"
            manifest_path = job_root / f"{result['job_id']}.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            output = Path(manifest["output_path"])
            self.assertTrue(output.is_relative_to(cfg.transcript_root.resolve()))
            self.assertEqual("PC_PERSONALE", manifest["workstation_id"])
            self.assertEqual(fingerprint, manifest["source_fingerprint"])
            command = launch.call_args.args[0]
            self.assertEqual(sys.executable, command[0])
            self.assertEqual(["-m", "bridge.transcription_worker", "--job", str(manifest_path.resolve())], command[1:])
            self.assertNotIn("shell", launch.call_args.kwargs)

    def test_retry_reuses_owned_running_or_complete_job_without_launching(self):
        for status in ("QUEUED", "RUNNING", "COMPLETED"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as raw_root:
                cfg = config(Path(raw_root))
                media = source(cfg)
                fingerprint = hashlib.sha256(media.read_bytes()).hexdigest()
                with patch("bridge.carabellese_transcription.subprocess.Popen") as launch:
                    launch.return_value.pid = 4321
                    first = start_carabellese_transcription(cfg, str(media), fingerprint)
                    manifest_path = (cfg.transcript_root / ".carabellese_jobs" /
                                     cfg.workstation_id / f"{first['job_id']}.json")
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest["status"] = status
                    if status == "RUNNING":
                        manifest["pid"] = os.getpid()
                    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                    launch.reset_mock()
                    retried = start_carabellese_transcription(cfg, str(media), fingerprint)
                self.assertEqual(first["job_id"], retried["job_id"])
                self.assertEqual(status, retried["status"])
                launch.assert_not_called()

    def test_interrupted_manifest_relaunches_same_owned_job(self):
        with tempfile.TemporaryDirectory() as raw_root:
            cfg = config(Path(raw_root))
            media = source(cfg)
            fingerprint = hashlib.sha256(media.read_bytes()).hexdigest()
            with patch("bridge.carabellese_transcription.subprocess.Popen") as launch:
                launch.return_value.pid = 4321
                first = start_carabellese_transcription(cfg, str(media), fingerprint)
                manifest_path = (cfg.transcript_root / ".carabellese_jobs" /
                                 cfg.workstation_id / f"{first['job_id']}.json")
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["status"] = "INTERRUPTED"
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                launch.reset_mock()
                resumed = start_carabellese_transcription(cfg, str(media), fingerprint)

            self.assertEqual(first["job_id"], resumed["job_id"])
            self.assertEqual("QUEUED", resumed["status"])
            self.assertEqual(1, launch.call_count)

    def test_dead_running_process_is_treated_as_interrupted_and_relaunched(self):
        with tempfile.TemporaryDirectory() as raw_root:
            cfg = config(Path(raw_root))
            media = source(cfg)
            fingerprint = hashlib.sha256(media.read_bytes()).hexdigest()
            with patch("bridge.carabellese_transcription.subprocess.Popen") as launch:
                launch.return_value.pid = 4321
                first = start_carabellese_transcription(cfg, str(media), fingerprint)
                manifest_path = (cfg.transcript_root / ".carabellese_jobs" /
                                 cfg.workstation_id / f"{first['job_id']}.json")
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest.update(status="RUNNING", pid=99999999)
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                launch.reset_mock()
                resumed = start_carabellese_transcription(cfg, str(media), fingerprint)

            self.assertEqual(first["job_id"], resumed["job_id"])
            self.assertEqual("QUEUED", resumed["status"])
            self.assertEqual(1, launch.call_count)

    def test_status_is_sanitized_and_rejects_foreign_workstation_manifest(self):
        with tempfile.TemporaryDirectory() as raw_root:
            cfg = config(Path(raw_root))
            media = source(cfg)
            fingerprint = hashlib.sha256(media.read_bytes()).hexdigest()
            with patch("bridge.carabellese_transcription.subprocess.Popen") as launch:
                launch.return_value.pid = 4321
                started = start_carabellese_transcription(cfg, str(media), fingerprint)
            manifest_path = (cfg.transcript_root / ".carabellese_jobs" /
                             cfg.workstation_id / f"{started['job_id']}.json")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["transcript_content"] = "dato privato"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            status = get_carabellese_transcription_job(cfg, started["job_id"])
            serialized = json.dumps(status)
            self.assertNotIn(str(media.resolve()), serialized)
            self.assertNotIn(str(Path(manifest["output_path"])), serialized)
            self.assertNotIn("dato privato", serialized)
            self.assertEqual(media.name, status["source_name"])
            self.assertEqual(Path(manifest["output_path"]).name, status["output_name"])

            manifest["workstation_id"] = "PC_SEGRETERIA"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "workstation"):
                get_carabellese_transcription_job(cfg, started["job_id"])


class CheckpointedTranscriptionTests(unittest.TestCase):
    def test_worker_rejects_tampered_model_before_transcription(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            media_root = root / "media"
            transcript_root = root / "transcripts"
            media_root.mkdir()
            transcript_root.mkdir()
            media = media_root / "source.mov"
            media.write_bytes(b"source")
            manifest_path = root / "job.json"
            manifest_path.write_text(json.dumps({
                "schema": "ARPHE_CARABELLESE_TRANSCRIPTION_JOB_V1",
                "job_id": "carabellese_tx_0123456789abcdef",
                "workstation_id": "PC_PERSONALE", "status": "QUEUED",
                "source_path": str(media), "source_name": media.name,
                "source_fingerprint": hashlib.sha256(media.read_bytes()).hexdigest(),
                "media_root": str(media_root), "output_path": str(transcript_root / "out.json"),
                "transcript_root": str(transcript_root), "model": "../../foreign-model",
                "language": "it", "progress_percent": 0, "created_at": "now",
                "updated_at": "now", "error": None,
            }), encoding="utf-8")
            with patch("bridge.transcription_worker.transcribe_checkpointed") as transcribe:
                with self.assertRaisesRegex(ValueError, "modello"):
                    run_job(manifest_path)
            transcribe.assert_not_called()

    def test_existing_running_transcript_resumes_after_last_checkpoint_without_schema_change(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            media = root / "source.mov"
            media.write_bytes(b"source")
            output = root / "source.transcript.json"
            fingerprint = hashlib.sha256(media.read_bytes()).hexdigest()
            output.write_text(json.dumps({
                "schema": "ARPHE_TRANSCRIPT_V1", "status": "running",
                "source": {"name": media.name, "path": str(media), "size_bytes": 6,
                           "fingerprint": fingerprint, "duration_seconds": 60.0},
                "transcription": {"engine": "faster-whisper", "model": "small",
                                  "device": "cpu", "compute_type": "int8",
                                  "requested_language": "it", "detected_language": None,
                                  "language_probability": None, "word_timestamps": True},
                "segments": [{"id": 0, "start": 0.0, "end": 12.5, "text": "prima",
                              "words": [{"start": 0.0, "end": 0.5, "word": "prima",
                                         "probability": 0.9}]}],
                "created_at": "2026-10-09T00:00:00Z", "updated_at": None,
            }), encoding="utf-8")
            calls: list[dict[str, object]] = []

            class FakeModel:
                def transcribe(self, _source: str, **kwargs: object):
                    calls.append(kwargs)
                    word = SimpleNamespace(start=13.0, end=13.5, word="dopo", probability=0.95)
                    segment = SimpleNamespace(id=1, start=13.0, end=14.0, text="dopo", words=[word])
                    return iter([segment]), SimpleNamespace(language="it", language_probability=0.99)

            transcribe_checkpointed(
                media, output, "small", "it", expected_source_fingerprint=fingerprint,
                model_factory=lambda *_args, **_kwargs: FakeModel(), duration_reader=lambda _path: 60.0,
            )
            result = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual("ARPHE_TRANSCRIPT_V1", result["schema"])
        self.assertEqual("complete", result["status"])
        self.assertEqual([0, 1], [segment["id"] for segment in result["segments"]])
        self.assertEqual("12.5", calls[0]["clip_timestamps"])


if __name__ == "__main__":
    unittest.main()
