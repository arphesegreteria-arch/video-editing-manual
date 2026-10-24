from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.artifact_records import ArtifactStore  # noqa: E402
from bridge.maintenance_scheduler import run_if_due, start_lazy_maintenance  # noqa: E402
from tests.test_artifact_records import config_for  # noqa: E402


UTC = timezone.utc


class MaintenanceSchedulerTests(unittest.TestCase):
    def _enabled(self, root: Path):
        config = config_for(root)
        return replace(config, flags={**config.flags, "CAP_ARTIFACT_MAINTENANCE": True})

    def test_run_if_due_runs_at_most_once_per_twenty_four_hours(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self._enabled(Path(directory))
            first = datetime(2026, 10, 8, 8, 0, tzinfo=UTC)
            self.assertTrue(run_if_due(config, now_utc=first)["ran"])
            self.assertFalse(run_if_due(config, now_utc=first + timedelta(hours=23, minutes=59))["ran"])
            self.assertTrue(run_if_due(config, now_utc=first + timedelta(hours=24))["ran"])

    def test_disabled_gate_never_runs_or_updates_maintenance_state(self):
        with tempfile.TemporaryDirectory() as directory:
            config = config_for(Path(directory))
            result = run_if_due(config, now_utc=datetime(2026, 10, 8, tzinfo=UTC))
            self.assertFalse(result["ran"])
            self.assertEqual("disabled", result["reason"])
            state = ArtifactStore(config.artifact_registry_path, config.workstation_id).maintenance_state()
            self.assertIsNone(state.last_attempt_at)

    def test_background_startup_failure_does_not_start_a_worker(self):
        loader = Mock(side_effect=RuntimeError("secret path must not escape"))
        thread = start_lazy_maintenance(loader, delay_seconds=0, max_cycles=1)
        self.assertIsNone(thread)
        self.assertEqual(1, loader.call_count)

    def test_disabled_gate_does_not_start_a_worker_or_write_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            config = config_for(Path(directory))
            loader = Mock(return_value=config)
            with patch("bridge.maintenance_scheduler.write_audit") as audit:
                thread = start_lazy_maintenance(loader, delay_seconds=0, max_cycles=1)
            self.assertIsNone(thread)
            self.assertEqual(1, loader.call_count)
            audit.assert_not_called()

    def test_enabled_background_loop_uses_initial_config_then_reloads(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self._enabled(Path(directory))
            loader = Mock(return_value=config)

            thread = start_lazy_maintenance(
                loader, delay_seconds=0, interval_seconds=0.01, max_cycles=2
            )
            self.assertIsNotNone(thread)
            thread.join(timeout=2)

            self.assertFalse(thread.is_alive())
            self.assertEqual(2, loader.call_count)

    def test_background_loop_rechecks_without_an_os_scheduler(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self._enabled(Path(directory))
            loader = Mock(return_value=config)

            thread = start_lazy_maintenance(
                loader, delay_seconds=0, interval_seconds=0.01, max_cycles=2
            )
            self.assertIsNotNone(thread)
            thread.join(timeout=2)

            self.assertFalse(thread.is_alive())
            self.assertEqual(2, loader.call_count)

    def test_server_run_reaches_mcp_even_if_lazy_start_fails(self):
        from bridge import server
        with patch("bridge.server.start_lazy_maintenance", side_effect=RuntimeError("thread unavailable")), \
             patch.object(server.mcp, "run") as mcp_run:
            server.run()
        mcp_run.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
