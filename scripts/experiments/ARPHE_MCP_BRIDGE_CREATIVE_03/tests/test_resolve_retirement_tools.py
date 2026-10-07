from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.server import mcp
from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE


def configured(root: Path, enabled: bool) -> CreativeConfig:
    flags = {**DEFAULT_FLAGS, "CAP_RESOLVE_RETIREMENT": enabled}
    return CreativeConfig(
        path=root / "creative.json", asset_root=root / "assets", render_root=root / "renders",
        state_path=root / "state.json", audit_log_path=root / "audit.jsonl",
        palette=dict(DEFAULT_PALETTE), flags=flags, allowed_projects=frozenset(),
        allowed_timelines=frozenset(), render_format="mp4", render_codec="H264",
        workstation_id="PC_PERSONALE", resolve_archive_root=root / "archives",
        resolve_retirement_registry_path=root / "retirements.json",
    )


class ResolveRetirementToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_inspection_works_with_gate_off_but_mutations_do_not_touch_resolve(self):
        with tempfile.TemporaryDirectory() as directory:
            config = configured(Path(directory), False)
            with patch("bridge.server.load_config", return_value=config), \
                 patch("bridge.server._runtime", side_effect=AssertionError("Resolve must not be touched")):
                inspection = await mcp.call_tool("inspect_resolve_retirements", {})
                prepare = await mcp.call_tool("prepare_resolve_retirement", {
                    "kind": "timeline", "project_name": "ARPHE_TEST",
                    "timeline_name": "ARPHE_OLD",
                })
            self.assertTrue(inspection.structured_content["ok"])
            self.assertFalse(prepare.structured_content["ok"])
            self.assertIn("CAP_RESOLVE_RETIREMENT", prepare.structured_content["error"])

    async def test_prepare_uses_profile_store_and_accepts_no_path(self):
        with tempfile.TemporaryDirectory() as directory:
            config = configured(Path(directory), True)
            runtime = (object(), object(), object(), object(), config, object(), None)
            expected = {"ok": True, "retirement_id": "ret-1", "status": "PREPARED"}
            with patch("bridge.server.load_config", return_value=config), \
                 patch("bridge.server._runtime", return_value=runtime), \
                 patch("bridge.server.do_prepare_resolve_retirement", return_value=expected) as operation:
                result = await mcp.call_tool("prepare_resolve_retirement", {
                    "kind": "project", "project_name": "ARPHE_TEST", "timeline_name": None,
                })
            self.assertEqual(expected, result.structured_content)
            self.assertEqual(config.resolve_retirement_registry_path,
                             operation.call_args.args[4].path)


if __name__ == "__main__":
    unittest.main()
