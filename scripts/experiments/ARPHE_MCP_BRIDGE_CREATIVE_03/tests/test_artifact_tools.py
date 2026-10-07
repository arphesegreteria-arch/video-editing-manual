from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.server import mcp  # noqa: E402
from tests.test_artifact_records import config_for  # noqa: E402


class ArtifactToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_inspection_works_while_mutation_gate_is_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            config = config_for(Path(directory))
            with patch("bridge.server.load_config", return_value=config):
                inspection = await mcp.call_tool("inspect_artifact_hygiene", {})
                maintenance = await mcp.call_tool("run_artifact_maintenance", {})
                restore = await mcp.call_tool("restore_quarantined_artifact", {"artifact_id": "unknown"})
            self.assertTrue(inspection.structured_content["ok"])
            self.assertFalse(maintenance.structured_content["ok"])
            self.assertFalse(restore.structured_content["ok"])
            self.assertIn("CAP_ARTIFACT_MAINTENANCE", maintenance.structured_content["error"])
            self.assertIn("CAP_ARTIFACT_MAINTENANCE", restore.structured_content["error"])

    async def test_inspection_report_discloses_only_managed_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = config_for(root)
            capture = config.render_root / "diagnostics" / "ARPHE_FRAME_unknown.jpg"
            capture.parent.mkdir(parents=True)
            capture.write_bytes(b"unknown")
            with patch("bridge.server.load_config", return_value=config):
                result = await mcp.call_tool("inspect_artifact_hygiene", {})
            payload = result.structured_content
            self.assertNotIn(str(root), str(payload))
            self.assertEqual("render_root:diagnostics/ARPHE_FRAME_unknown.jpg",
                             payload["items"][0]["display_path"])

    async def test_enabled_maintenance_uses_fixed_profile_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            config = config_for(Path(directory))
            config = replace(config, flags={**config.flags, "CAP_ARTIFACT_MAINTENANCE": True})
            with patch("bridge.server.load_config", return_value=config):
                result = await mcp.call_tool("run_artifact_maintenance", {})
            self.assertTrue(result.structured_content["ok"])
            self.assertEqual(config.workstation_id, result.structured_content["workstation_id"])


if __name__ == "__main__":
    unittest.main()
