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

from bridge.artifact_hygiene import inspect_artifacts, validate_managed_path  # noqa: E402
from bridge.artifact_records import ArtifactStore, load_artifact_policy  # noqa: E402
from tests.test_artifact_records import POLICY_PATH, config_for  # noqa: E402


UTC = timezone.utc


class Batch:
    def __init__(self, status: str):
        self.status = status


class ProjectRegistry:
    def __init__(self, statuses: dict[str, str] | None = None):
        self.statuses = statuses or {}

    def render_batch(self, batch_id: str):
        status = self.statuses.get(batch_id)
        return None if status is None else Batch(status)


def report_for(root: Path, now: datetime, statuses: dict[str, str] | None = None):
    config = config_for(root)
    return inspect_artifacts(
        config,
        ArtifactStore(config.artifact_registry_path, config.workstation_id),
        ProjectRegistry(statuses),
        load_artifact_policy(POLICY_PATH),
        now,
    )


class ArtifactInventoryTests(unittest.TestCase):
    def test_registered_diagnostic_becomes_eligible_after_24_hours(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = config_for(root)
            capture = config.render_root / "diagnostics" / "ARPHE_FRAME_known.jpg"
            capture.parent.mkdir(parents=True)
            capture.write_bytes(b"known")
            created = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)
            store = ArtifactStore(config.artifact_registry_path, config.workstation_id)
            record = store.register_path(
                capture,
                kind="file",
                category="DIAGNOSTIC_CAPTURE",
                producer="capture_timeline_frames",
                managed_root_id="render_root",
                created_at=created,
            )

            report = report_for(root, created + timedelta(hours=24))

            item = next(value for value in report["items"] if value["artifact_id"] == record.artifact_id)
            self.assertEqual("ELIGIBLE", item["state"])
            self.assertEqual("render_root:diagnostics/ARPHE_FRAME_known.jpg", item["display_path"])
            self.assertNotIn(str(root), json.dumps(report))

    def test_unregistered_arphe_jpeg_is_report_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = config_for(root).render_root / "diagnostics" / "ARPHE_FRAME_old.jpg"
            capture.parent.mkdir(parents=True)
            capture.write_bytes(b"old")

            report = report_for(root, datetime(2026, 10, 8, tzinfo=UTC))

            self.assertEqual(1, report["summary"]["UNCLASSIFIED"]["count"])
            self.assertTrue(capture.exists())
            self.assertEqual("UNCLASSIFIED", report["items"][0]["state"])

    def test_publishable_master_and_source_locations_are_not_scanned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = config_for(root)
            for relative in ("publishable/final.mp4", "master/master.mov", "source/source.mov"):
                path = config.render_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"protected")

            report = report_for(root, datetime(2026, 10, 8, tzinfo=UTC))

            self.assertEqual([], report["items"])

    def test_active_batch_staging_is_protected_regardless_of_age(self):
        active_states = ("DRAFT", "CONFIRMED", "PREPARED", "APPROVED", "RENDERING", "VERIFYING")
        for status in active_states:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = config_for(root)
                staging = config.render_root / "staging" / f"batch-{status.lower()}"
                staging.mkdir(parents=True)
                store = ArtifactStore(config.artifact_registry_path, config.workstation_id)
                record = store.register_path(
                    staging,
                    kind="directory",
                    category="RENDER_STAGING",
                    producer="prepare_render_batch",
                    managed_root_id="render_root",
                    batch_id=f"batch-{status.lower()}",
                    created_at=datetime(2026, 1, 1, tzinfo=UTC),
                )

                report = report_for(root, datetime(2026, 10, 8, tzinfo=UTC), {record.batch_id: status})
                item = next(value for value in report["items"] if value["artifact_id"] == record.artifact_id)
                self.assertEqual("PROTECTED", item["state"])

    def test_terminal_batch_without_frozen_manifest_waits_for_maintenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = config_for(root)
            staging = config.render_root / "staging" / "batch-terminal"
            staging.mkdir(parents=True)
            store = ArtifactStore(config.artifact_registry_path, config.workstation_id)
            record = store.register_path(
                staging,
                kind="directory",
                category="RENDER_STAGING",
                producer="prepare_render_batch",
                managed_root_id="render_root",
                batch_id="batch-terminal",
            )

            report = report_for(root, datetime(2026, 10, 8, tzinfo=UTC), {"batch-terminal": "VERIFIED"})

            item = next(value for value in report["items"] if value["artifact_id"] == record.artifact_id)
            self.assertEqual("AWAITING_TERMINAL_SNAPSHOT", item["state"])

    def test_terminal_snapshot_uses_failed_render_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = config_for(root)
            staging = config.render_root / "staging" / "batch-failed"
            staging.mkdir(parents=True)
            (staging / "failed.mp4").write_bytes(b"failed")
            observed = datetime(2026, 10, 1, tzinfo=UTC)
            store = ArtifactStore(config.artifact_registry_path, config.workstation_id)
            record = store.register_path(
                staging,
                kind="directory",
                category="RENDER_STAGING",
                producer="prepare_render_batch",
                managed_root_id="render_root",
                batch_id="batch-failed",
            )
            store.replace(replace(
                record,
                category="FAILED_RENDER_STAGING",
                terminal_observed_at=observed,
                eligible_at=observed + timedelta(days=7),
                size_bytes=6,
                sha256="a" * 64,
            ))

            before = report_for(root, observed + timedelta(days=7) - timedelta(seconds=1),
                                {"batch-failed": "FAILED_VERIFY"})
            at_boundary = report_for(root, observed + timedelta(days=7),
                                     {"batch-failed": "FAILED_VERIFY"})

            self.assertEqual("ACTIVE", before["items"][0]["state"])
            self.assertEqual("ELIGIBLE", at_boundary["items"][0]["state"])

    def test_missing_batch_is_error_not_disposable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = config_for(root)
            staging = config.render_root / "staging" / "unknown-batch"
            staging.mkdir(parents=True)
            ArtifactStore(config.artifact_registry_path, config.workstation_id).register_path(
                staging,
                kind="directory",
                category="RENDER_STAGING",
                producer="prepare_render_batch",
                managed_root_id="render_root",
                batch_id="missing",
            )

            report = report_for(root, datetime(2026, 10, 8, tzinfo=UTC))

            self.assertEqual("ERROR", report["items"][0]["state"])

    def test_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            managed = root / "managed"
            outside = root / "outside"
            managed.mkdir()
            outside.mkdir()
            link = managed / "escape"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symlink unavailable: {exc}")

            with self.assertRaisesRegex(ValueError, "symlink|reparse|root"):
                validate_managed_path(link / "file.txt", managed, allow_directory=False)


if __name__ == "__main__":
    unittest.main()
