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

from bridge.artifact_hygiene import (  # noqa: E402
    inspect_artifacts,
    restore_artifact,
    run_maintenance,
    validate_managed_path,
)
from bridge.artifact_records import ArtifactStore, load_artifact_policy  # noqa: E402
from tests.test_artifact_records import POLICY_PATH, config_for  # noqa: E402


UTC = timezone.utc


class Batch:
    def __init__(self, status: str, expected_outputs: tuple[str, ...] = ()):
        self.status = status
        self.expected_outputs = expected_outputs


class ProjectRegistry:
    def __init__(self, statuses: dict[str, str | tuple[str, tuple[str, ...]]] | None = None):
        self.statuses = statuses or {}

    def render_batch(self, batch_id: str):
        value = self.statuses.get(batch_id)
        if value is None:
            return None
        if isinstance(value, tuple):
            return Batch(value[0], value[1])
        return Batch(value)


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


class ArtifactLifecycleTests(unittest.TestCase):
    def _diagnostic(self, root: Path, created: datetime):
        config = config_for(root)
        path = config.render_root / "diagnostics" / "frame.jpg"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"frame")
        store = ArtifactStore(config.artifact_registry_path, config.workstation_id)
        record = store.register_path(
            path,
            kind="file",
            category="DIAGNOSTIC_CAPTURE",
            producer="capture_timeline_frames",
            managed_root_id="render_root",
            created_at=created,
            policy_version="ARPHE_ARTIFACT_RETENTION_V1",
        )
        return config, store, record, path

    def _run(self, config, store, now, registry=None):
        return run_maintenance(
            config,
            store,
            registry or ProjectRegistry(),
            load_artifact_policy(POLICY_PATH),
            now,
        )

    def test_quarantine_starts_at_exact_active_retention_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            created = datetime(2026, 10, 1, tzinfo=UTC)
            config, store, record, original = self._diagnostic(root, created)

            before = self._run(config, store, created + timedelta(hours=24) - timedelta(seconds=1))
            self.assertEqual([], before["quarantined"])
            self.assertTrue(original.exists())

            at_boundary = self._run(config, store, created + timedelta(hours=24))
            current = store.records()[0]
            self.assertEqual([record.artifact_id], at_boundary["quarantined"])
            self.assertFalse(original.exists())
            self.assertEqual("QUARANTINED", current.state)
            self.assertTrue(Path(current.quarantine_path or "").exists())

    def test_purge_requires_seven_complete_days_in_quarantine(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            created = datetime(2026, 10, 1, tzinfo=UTC)
            config, store, record, _ = self._diagnostic(root, created)
            quarantined_at = created + timedelta(days=1)
            self._run(config, store, quarantined_at)

            before = self._run(config, store, quarantined_at + timedelta(days=7) - timedelta(seconds=1))
            self.assertEqual([], before["purged"])
            self.assertTrue(Path(store.records()[0].quarantine_path or "").exists())

            at_boundary = self._run(config, store, quarantined_at + timedelta(days=7))
            self.assertEqual([record.artifact_id], at_boundary["purged"])
            self.assertEqual("PURGED", store.records()[0].state)

    def test_restore_returns_exact_item_and_collision_changes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            created = datetime(2026, 10, 1, tzinfo=UTC)
            config, store, record, original = self._diagnostic(root, created)
            self._run(config, store, created + timedelta(days=1))

            restored = restore_artifact(
                config, store, record.artifact_id, load_artifact_policy(POLICY_PATH),
                created + timedelta(days=2),
            )
            self.assertTrue(restored["ok"])
            self.assertEqual(b"frame", original.read_bytes())
            self.assertEqual("RESTORED", store.records()[0].state)

            # Quarantine again after the category's active retention, then create a collision.
            self._run(config, store, created + timedelta(days=3))
            quarantined = store.records()[0]
            original.write_bytes(b"new content")
            result = restore_artifact(
                config, store, record.artifact_id, load_artifact_policy(POLICY_PATH),
                created + timedelta(days=4),
            )
            self.assertFalse(result["ok"])
            self.assertEqual("RESTORE_COLLISION", result["error_code"])
            self.assertEqual(b"new content", original.read_bytes())
            self.assertTrue(Path(quarantined.quarantine_path or "").exists())

    def test_changed_digest_is_marked_error_and_not_moved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            created = datetime(2026, 10, 1, tzinfo=UTC)
            config, store, _, original = self._diagnostic(root, created)
            original.write_bytes(b"changed")

            result = self._run(config, store, created + timedelta(days=1))

            self.assertEqual([], result["quarantined"])
            self.assertTrue(original.exists())
            self.assertEqual("ERROR", store.records()[0].state)
            self.assertEqual("CONTENT_CHANGED", store.records()[0].last_error)

    def test_terminal_staging_freezes_manifest_before_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = config_for(root)
            staging = config.render_root / "staging" / "batch-1"
            staging.mkdir(parents=True)
            (staging / "output.mp4").write_bytes(b"render")
            store = ArtifactStore(config.artifact_registry_path, config.workstation_id)
            record = store.register_path(
                staging,
                kind="directory",
                category="RENDER_STAGING",
                producer="prepare_render_batch",
                managed_root_id="render_root",
                batch_id="batch-1",
            )
            observed = datetime(2026, 10, 8, tzinfo=UTC)
            registry = ProjectRegistry({"batch-1": ("CANCELLED", ("output.mp4",))})

            first = self._run(config, store, observed, registry)
            frozen = store.records()[0]
            self.assertEqual([], first["quarantined"])
            self.assertEqual(observed, frozen.terminal_observed_at)
            self.assertEqual(observed + timedelta(days=1), frozen.eligible_at)
            self.assertEqual(6, frozen.size_bytes)
            self.assertEqual(64, len(frozen.sha256 or ""))

            second = self._run(config, store, observed + timedelta(days=1), registry)
            self.assertEqual([record.artifact_id], second["quarantined"])

    def test_unexpected_staging_descendant_blocks_quarantine(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = config_for(root)
            staging = config.render_root / "staging" / "batch-1"
            staging.mkdir(parents=True)
            (staging / "output.mp4").write_bytes(b"render")
            (staging / "foreign.txt").write_text("foreign", encoding="utf-8")
            store = ArtifactStore(config.artifact_registry_path, config.workstation_id)
            store.register_path(
                staging,
                kind="directory",
                category="RENDER_STAGING",
                producer="prepare_render_batch",
                managed_root_id="render_root",
                batch_id="batch-1",
            )

            result = self._run(
                config, store, datetime(2026, 10, 8, tzinfo=UTC),
                ProjectRegistry({"batch-1": ("CANCELLED", ("output.mp4",))}),
            )

            self.assertEqual([], result["quarantined"])
            self.assertEqual("ERROR", store.records()[0].state)
            self.assertEqual("UNEXPECTED_STAGING_CONTENT", store.records()[0].last_error)

    def test_existing_lock_refuses_concurrent_cycle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, store, _, original = self._diagnostic(root, datetime(2026, 10, 1, tzinfo=UTC))
            lock = store.path.with_suffix(store.path.suffix + ".maintenance.lock")
            lock.parent.mkdir(parents=True, exist_ok=True)
            lock.write_text("busy", encoding="utf-8")

            result = self._run(config, store, datetime(2026, 10, 8, tzinfo=UTC))

            self.assertFalse(result["ok"])
            self.assertEqual("MAINTENANCE_LOCKED", result["error_code"])
            self.assertTrue(original.exists())

    def test_pending_move_is_reconciled_after_registry_write_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            created = datetime(2026, 10, 1, tzinfo=UTC)
            config, store, record, original = self._diagnostic(root, created)
            real_replace = store.replace
            calls = 0

            def fail_once(value):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise OSError("registry unavailable")
                return real_replace(value)

            store.replace = fail_once  # type: ignore[method-assign]
            failed = self._run(config, store, created + timedelta(days=1))
            self.assertFalse(failed["ok"])
            self.assertFalse(original.exists())

            restarted = ArtifactStore(store.path, store.workstation_id)
            recovered = self._run(config, restarted, created + timedelta(days=1, seconds=1))
            current = restarted.records()[0]
            self.assertTrue(recovered["ok"])
            self.assertEqual(record.artifact_id, current.artifact_id)
            self.assertEqual("QUARANTINED", current.state)


if __name__ == "__main__":
    unittest.main()
