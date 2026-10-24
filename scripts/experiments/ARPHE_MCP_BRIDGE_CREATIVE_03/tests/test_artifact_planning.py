from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.artifact_planning import (  # noqa: E402
    inventory_roots,
    plan_legacy_migration,
    scan_artifacts,
    simulate_maintenance,
)
from bridge.artifact_records import ArtifactStore, load_artifact_policy  # noqa: E402
from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402


UTC = timezone.utc


def config_for(root: Path) -> CreativeConfig:
    return CreativeConfig(
        path=root / "profile" / "creative.json", asset_root=root / "assets",
        render_root=root / "renders", media_roots=(root / "media",),
        transcript_root=root / "transcripts", audio_root=root / "audio",
        audio_jobs_root=root / "audio_jobs", state_path=root / "profile" / "state.json",
        audit_log_path=root / "profile" / "audit.jsonl", palette=dict(DEFAULT_PALETTE),
        flags=dict(DEFAULT_FLAGS), allowed_projects=frozenset(), allowed_timelines=frozenset(),
        render_format="mp4", render_codec="H264", workstation_id="PC_PERSONALE",
        artifact_policy_path=ROOT / "artifact_retention.json",
        artifact_registry_path=root / "profile" / "artifact_registry.json",
        runtime_log_root=root / "runtime_logs",
        colorist_jobs_path=root / "profile" / "colorist_jobs.json",
        resolve_archive_root=root / "resolve_archives",
    )


class ArtifactPlanningTests(unittest.TestCase):
    def test_inventory_lists_cleanup_and_reference_only_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            roots = {item["root_id"]: item["mode"]
                     for item in inventory_roots(config_for(Path(directory)))}

            self.assertEqual("SCAN_DISPOSABLE", roots["render_root"])
            self.assertEqual("SCAN_PROTECTED", roots["audio_root"])
            self.assertEqual("SCAN_PROTECTED", roots["audio_jobs_root"])
            self.assertEqual("REFERENCE_ONLY", roots["asset_root"])
            self.assertEqual("REFERENCE_ONLY", roots["media_root_0"])
            self.assertEqual("REFERENCE_ONLY", roots["resolve_archive_root"])
            self.assertEqual("REFERENCE_ONLY_UNCONFIGURED", roots["backup_evidence"])

    def test_unknown_audio_is_protected_and_never_a_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = config_for(root)
            cfg.audio_root.mkdir(parents=True)
            unknown = cfg.audio_root / "mystery.wav"
            unknown.write_bytes(b"unknown")
            store = ArtifactStore(cfg.artifact_registry_path, cfg.workstation_id)

            report = scan_artifacts(cfg, store)
            simulation = simulate_maintenance(
                cfg, store, load_artifact_policy(cfg.artifact_policy_path),
                datetime(2026, 10, 24, tzinfo=UTC), active_job_ids=(),
            )

            item = next(value for value in report["items"] if value["display_path"].endswith("mystery.wav"))
            self.assertEqual("UNCLASSIFIED_PROTECTED", item["state"])
            self.assertEqual([], simulation["quarantine_candidates"])

    def test_simulation_blocks_hash_drift_dependencies_active_jobs_and_purge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = config_for(root)
            cfg.render_root.mkdir(parents=True)
            store = ArtifactStore(cfg.artifact_registry_path, cfg.workstation_id)
            now = datetime(2026, 10, 24, tzinfo=UTC)
            files = []
            for name in ("eligible", "changed", "active"):
                path = cfg.render_root / f"{name}.tmp"
                path.write_bytes(name.encode())
                files.append(path)
            eligible = store.register_path(
                files[0], "file", "TEMP_REPORT", "test", "render_root",
                created_at=now - timedelta(days=3),
            )
            changed = store.register_path(
                files[1], "file", "TEMP_REPORT", "test", "render_root",
                created_at=now - timedelta(days=3),
            )
            active = store.register_path(
                files[2], "file", "RENDER_STAGING", "test", "render_root",
                batch_id="batch-active", created_at=now - timedelta(days=3),
            )
            files[1].write_bytes(b"tampered")
            store.replace(replace(eligible, eligible_at=now - timedelta(days=1)))
            store.replace(replace(changed, eligible_at=now - timedelta(days=1)))
            store.replace(replace(active, eligible_at=now - timedelta(days=1)))
            quarantined = store.register_path(
                cfg.render_root / "eligible.tmp", "file", "TEMP_REPORT", "test", "render_root"
            )
            store.replace(replace(
                quarantined, state="QUARANTINED", purge_after=now - timedelta(seconds=1),
                quarantine_path=str(files[0]), original_path=str(files[0]),
            ))

            report = simulate_maintenance(
                cfg, store, load_artifact_policy(cfg.artifact_policy_path), now,
                active_job_ids=("batch-active",),
            )

            states = {item["display_path"]: item["state"] for item in report["items"]}
            self.assertIn("BLOCKED_HASH_DRIFT", states.values())
            self.assertIn("HELD_ACTIVE_JOB", states.values())
            self.assertIn("PURGE_DISABLED", states.values())
            self.assertEqual([], report["purge_candidates"])

    def test_legacy_migration_is_dry_run_and_validates_fingerprints(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = config_for(root)
            cfg.audio_root.mkdir(parents=True)
            cfg.audio_jobs_root.mkdir(parents=True)
            output = cfg.audio_root / "natural.wav"
            output.write_bytes(b"natural")
            digest = hashlib.sha256(output.read_bytes()).hexdigest()
            manifest = cfg.audio_jobs_root / "audio_0123456789abcdef.json"
            manifest.write_text(json.dumps({
                "schema": "ARPHE_AUDIO_JOB_V2", "status": "COMPLETED",
                "source_fingerprint": "a" * 64, "output_path": str(output),
                "output_sha256": digest,
            }), encoding="utf-8")

            report = plan_legacy_migration(cfg)

            self.assertEqual(2, len(report["proposals"]))
            self.assertEqual([], report["errors"])
            self.assertFalse(cfg.artifact_registry_path.exists())
            self.assertEqual(digest, hashlib.sha256(output.read_bytes()).hexdigest())

    def test_listening_variant_migration_proposes_output_without_touching_a_or_v5(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = config_for(root)
            cfg.audio_root.mkdir(parents=True)
            cfg.audio_jobs_root.mkdir(parents=True)
            source = cfg.audio_root / "A.wav"
            v5 = cfg.audio_root / "V5.wav"
            variant = cfg.audio_root / "PIU_NATURALE.wav"
            source.write_bytes(b"source")
            v5.write_bytes(b"v5")
            variant.write_bytes(b"natural")
            manifest = cfg.audio_jobs_root / "piu_naturale.json"
            manifest.write_text(json.dumps({
                "schema": "ARPHE_LISTENING_VARIANT_V1", "status": "COMPLETED",
                "source": {"path": str(source), "sha256": hashlib.sha256(b"source").hexdigest()},
                "reference_v5": {"path": str(v5), "sha256": hashlib.sha256(b"v5").hexdigest()},
                "output": {"path": str(variant), "sha256": hashlib.sha256(b"natural").hexdigest()},
            }), encoding="utf-8")

            report = plan_legacy_migration(cfg)

            names = {item["display_path"] for item in report["proposals"]}
            self.assertIn("audio_root:A.wav", names)
            self.assertIn("audio_root:V5.wav", names)
            self.assertIn("audio_root:PIU_NATURALE.wav", names)
            self.assertIn("audio_jobs_root:piu_naturale.json", names)
            self.assertEqual([], report["errors"])
            self.assertFalse(cfg.artifact_registry_path.exists())


if __name__ == "__main__":
    unittest.main()
