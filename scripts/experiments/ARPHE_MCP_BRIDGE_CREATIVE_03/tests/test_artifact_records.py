from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.artifact_records import (  # noqa: E402
    ArtifactStore,
    artifact_store_for,
    load_artifact_policy,
)
from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402


POLICY_PATH = ROOT / "artifact_retention.json"
UTC = timezone.utc


def config_for(root: Path, workstation: str = "PC_PERSONALE") -> CreativeConfig:
    return CreativeConfig(
        path=root / "creative.json",
        asset_root=root / "assets",
        render_root=root / "renders",
        state_path=root / "state.json",
        audit_log_path=root / "audit.jsonl",
        palette=dict(DEFAULT_PALETTE),
        flags=dict(DEFAULT_FLAGS),
        allowed_projects=frozenset(),
        allowed_timelines=frozenset(),
        render_format="mp4",
        render_codec="H264",
        workstation_id=workstation,
        artifact_policy_path=POLICY_PATH,
        artifact_registry_path=root / "artifact-registry.json",
        runtime_log_root=root / "runtime-logs",
    )


class ArtifactPolicyTests(unittest.TestCase):
    def test_production_policy_uses_exact_retention_and_categories(self):
        policy = load_artifact_policy(POLICY_PATH)

        self.assertEqual("ARPHE_ARTIFACT_RETENTION_V1", policy.policy_version)
        self.assertEqual(604800, policy.quarantine_seconds)
        self.assertEqual(86400, policy.rules["DIAGNOSTIC_CAPTURE"].active_seconds)
        self.assertEqual(86400, policy.rules["TEMP_REPORT"].active_seconds)
        self.assertEqual(604800, policy.rules["TECHNICAL_PREVIEW"].active_seconds)
        self.assertEqual(86400, policy.rules["RENDER_STAGING"].active_seconds)
        self.assertEqual(604800, policy.rules["FAILED_RENDER_STAGING"].active_seconds)
        self.assertEqual(604800, policy.rules["ROTATED_LOG"].active_seconds)
        self.assertEqual(
            {"VERIFIED", "CANCELLED", "FAILED_PREPARE"},
            set(policy.rules["RENDER_STAGING"].terminal_batch_states),
        )

    def test_policy_rejects_unknown_category(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
            raw["rules"]["ARBITRARY_USER_FILE"] = {
                "active_seconds": 1,
                "terminal_batch_states": [],
            }
            path = Path(directory) / "policy.json"
            path.write_text(json.dumps(raw), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "categor"):
                load_artifact_policy(path)


class ArtifactStoreTests(unittest.TestCase):
    def test_register_file_persists_digest_and_workstation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "renders" / "diagnostics" / "frame.jpg"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"frame")
            store = ArtifactStore(root / "registry.json", "PC_PERSONALE")
            created = datetime(2026, 10, 8, 10, 0, tzinfo=UTC)

            record = store.register_path(
                source,
                kind="file",
                category="DIAGNOSTIC_CAPTURE",
                producer="capture_timeline_frames",
                managed_root_id="render_root",
                created_at=created,
            )

            reloaded = ArtifactStore(store.path, "PC_PERSONALE").records()[0]
            self.assertEqual(record.artifact_id, reloaded.artifact_id)
            self.assertEqual("PC_PERSONALE", reloaded.workstation_id)
            self.assertEqual(5, reloaded.size_bytes)
            self.assertEqual(64, len(reloaded.sha256 or ""))
            self.assertEqual("ACTIVE", reloaded.state)

    def test_active_directory_may_be_registered_before_digest_is_frozen(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staging = root / "renders" / "staging" / "batch-1"
            staging.mkdir(parents=True)
            store = ArtifactStore(root / "registry.json", "PC_PERSONALE")

            record = store.register_path(
                staging,
                kind="directory",
                category="RENDER_STAGING",
                producer="prepare_render_batch",
                managed_root_id="render_root",
                batch_id="batch-1",
            )

            self.assertIsNone(record.sha256)
            self.assertIsNone(record.size_bytes)

    def test_existing_registry_cannot_be_opened_as_another_workstation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            ArtifactStore(path, "PC_PERSONALE").set_maintenance_state(
                last_attempt_at=datetime(2026, 10, 8, tzinfo=UTC), last_result="ok"
            )

            with self.assertRaisesRegex(ValueError, "workstation"):
                ArtifactStore(path, "PC_SEGRETERIA").records()

    def test_corrupt_existing_registry_fails_closed_and_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            path.write_text("{broken", encoding="utf-8")

            with self.assertRaises((ValueError, json.JSONDecodeError)):
                ArtifactStore(path, "PC_PERSONALE").records()

            self.assertEqual("{broken", path.read_text(encoding="utf-8"))

    def test_maintenance_clock_cannot_move_backwards(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            store = ArtifactStore(path, "PC_PERSONALE")
            later = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
            store.set_maintenance_state(last_attempt_at=later, last_result="ok")
            store.set_maintenance_state(last_attempt_at=later - timedelta(hours=1), last_result="error")

            state = store.maintenance_state()
            self.assertEqual(later, state.last_attempt_at)
            self.assertEqual("error", state.last_result)

    def test_replace_preserves_identity_and_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "frame.jpg"
            source.write_bytes(b"frame")
            store = ArtifactStore(root / "registry.json", "PC_PERSONALE")
            record = store.register_path(
                source,
                kind="file",
                category="DIAGNOSTIC_CAPTURE",
                producer="capture_timeline_frames",
                managed_root_id="render_root",
            )

            store.replace(replace(record, state="ELIGIBLE"))

            self.assertEqual("ELIGIBLE", store.records()[0].state)

    def test_artifact_store_for_uses_profile_owned_path(self):
        with tempfile.TemporaryDirectory() as directory:
            config = config_for(Path(directory))
            store = artifact_store_for(config)

            self.assertEqual(config.artifact_registry_path, store.path)
            self.assertEqual("PC_PERSONALE", store.workstation_id)


if __name__ == "__main__":
    unittest.main()
