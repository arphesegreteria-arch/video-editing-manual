from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.artifact_producers import (  # noqa: E402
    register_colorist_state,
    register_completed_audio_job,
)
from bridge.artifact_records import ArtifactStore  # noqa: E402
from bridge.colorist_jobs import new_colorist_job  # noqa: E402
from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402


def config_for(root: Path) -> CreativeConfig:
    return CreativeConfig(
        path=root / "creative.json", asset_root=root / "assets",
        render_root=root / "renders", media_roots=(root / "media",),
        transcript_root=root / "transcripts", audio_root=root / "audio",
        audio_jobs_root=root / "audio_jobs", state_path=root / "state.json",
        audit_log_path=root / "audit.jsonl", palette=dict(DEFAULT_PALETTE),
        flags=dict(DEFAULT_FLAGS), allowed_projects=frozenset(),
        allowed_timelines=frozenset(), render_format="mp4", render_codec="H264",
        workstation_id="PC_PERSONALE", artifact_registry_path=root / "artifact_registry.json",
        colorist_jobs_path=root / "profile" / "colorist_jobs.json",
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ArtifactProducerTests(unittest.TestCase):
    def test_completed_dialogue_job_registers_a_v5_and_manifests_as_protected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = config_for(root)
            owned = cfg.audio_root / "timeline-dialogue-cleanup" / "PC_PERSONALE" / "job"
            owned.mkdir(parents=True)
            source = owned / "source.wav"
            output = owned / "natural_v5.wav"
            source.write_bytes(b"source-a")
            output.write_bytes(b"processed-v5")
            jobs = cfg.audio_jobs_root / "timeline-dialogue-cleanup" / "PC_PERSONALE"
            jobs.mkdir(parents=True)
            worker = jobs / "job.audio.json"
            worker.write_text(json.dumps({
                "schema": "ARPHE_AUDIO_JOB_V2", "status": "COMPLETED",
                "workstation_id": "PC_PERSONALE",
                "source_fingerprint": digest(source), "output_path": str(output),
                "output_sha256": digest(output),
            }), encoding="utf-8")
            parent = jobs / "job.json"
            parent.write_text(json.dumps({
                "schema": "ARPHE_TIMELINE_DIALOGUE_CLEANUP_JOB_V1",
                "status": "COMPLETED", "workstation_id": "PC_PERSONALE",
                "source_path": str(source),
                "processed_path": str(output), "source_fingerprint": digest(source),
                "output_fingerprint": digest(output), "audio_worker_manifest": str(worker),
                "timeline_source": {"timeline_edit_fingerprint": "f" * 64},
            }), encoding="utf-8")

            records = register_completed_audio_job(cfg, parent)

            self.assertEqual(4, len(records))
            stored = ArtifactStore(cfg.artifact_registry_path, cfg.workstation_id).records()
            self.assertEqual(
                {"AUDIO_SOURCE", "AUDIO_DERIVATIVE", "AUDIO_MANIFEST"},
                {record.category for record in stored},
            )
            self.assertTrue(all(record.protection_class == "PROTECTED" for record in stored))
            derivative = next(record for record in stored if record.category == "AUDIO_DERIVATIVE")
            self.assertIn("fingerprint:" + digest(source), derivative.dependencies)
            self.assertTrue(any(value.startswith("manifest-sha256:")
                                for value in derivative.dependencies))
            self.assertEqual("PENDING", derivative.review_state)
            self.assertIn("HUMAN_LISTENING_REVIEW", derivative.hold_reasons)

    def test_active_audio_job_is_not_registered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = config_for(root)
            cfg.audio_jobs_root.mkdir(parents=True)
            manifest = cfg.audio_jobs_root / "active.json"
            manifest.write_text(json.dumps({
                "schema": "ARPHE_AUDIO_JOB_V2", "status": "RUNNING",
            }), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "completato"):
                register_completed_audio_job(cfg, manifest)

            self.assertFalse(cfg.artifact_registry_path.exists())

    def test_colorist_state_refreshes_hash_and_keeps_review_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = config_for(root)
            cfg.colorist_jobs_path.parent.mkdir(parents=True)
            job = new_colorist_job(
                workstation_id="PC_PERSONALE", project_name="ARPHE_GATE",
                timeline_name="ARPHE_REVIEW", timeline_identity="timeline-1",
                clip_ids=("clip-1",), reference_clip_id=None, adjustments={},
                preset_name="ARPHE_CLEAN_NEUTRAL", drx_preset_name=None,
                drx_asset_identity=None,
                before_versions={"clip-1": {"versionName": "V1", "versionType": 0}},
                cdl={
                    "NodeIndex": "1", "Slope": "1 1 1", "Offset": "0 0 0",
                    "Power": "1 1 1", "Saturation": "1",
                },
            )

            cfg.colorist_jobs_path.write_text(json.dumps({
                "schema": "ARPHE_COLORIST_JOBS_V1", "workstation_id": "PC_PERSONALE",
                "jobs": {job.colorist_job_id: asdict(job)},
            }), encoding="utf-8")
            first = register_colorist_state(cfg)
            applied = replace(job, state="APPLIED")
            cfg.colorist_jobs_path.write_text(json.dumps({
                "schema": "ARPHE_COLORIST_JOBS_V1", "workstation_id": "PC_PERSONALE",
                "jobs": {job.colorist_job_id: asdict(applied)},
            }), encoding="utf-8")
            second = register_colorist_state(cfg)

            self.assertEqual(first.artifact_id, second.artifact_id)
            self.assertNotEqual(first.sha256, second.sha256)
            self.assertEqual("PENDING", second.review_state)
            self.assertIn("HUMAN_COLOR_REVIEW", second.hold_reasons)
            self.assertTrue(any(value.startswith("resolve-project:") for value in second.dependencies))


if __name__ == "__main__":
    unittest.main()
