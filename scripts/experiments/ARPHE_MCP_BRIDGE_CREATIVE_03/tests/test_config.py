from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bridge.config import DEFAULT_FLAGS, load_config


class TimelineElementConfigTests(unittest.TestCase):
    def write_config(self, root: Path, **changes):
        raw = {
            "runtime_id": "ARPHE_MCP_BRIDGE_CREATIVE_03",
            "workstation_id": "PC_PERSONALE",
        }
        raw.update(changes)
        path = root / "creative_config.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        return path

    def test_timeline_element_control_defaults_are_disabled_and_workstation_local(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = load_config(self.write_config(root))
            self.assertIn("CAP_TIMELINE_ELEMENT_CONTROL", DEFAULT_FLAGS)
            self.assertFalse(config.flags["CAP_TIMELINE_ELEMENT_CONTROL"])
            self.assertEqual((root / "timeline_element_control.json").resolve(),
                             config.timeline_element_control_path)
            self.assertEqual(300, config.timeline_element_handle_ttl_seconds)
            self.assertEqual(600, config.timeline_element_removal_ttl_seconds)

    def test_timeline_element_ttls_reject_bool_noninteger_and_out_of_bounds(self):
        cases = (
            {"timeline_element_handle_ttl_seconds": True},
            {"timeline_element_handle_ttl_seconds": "300"},
            {"timeline_element_handle_ttl_seconds": 29},
            {"timeline_element_handle_ttl_seconds": 901},
            {"timeline_element_removal_ttl_seconds": False},
            {"timeline_element_removal_ttl_seconds": 59},
            {"timeline_element_removal_ttl_seconds": 1801},
        )
        for changes in cases:
            with self.subTest(changes=changes), TemporaryDirectory() as directory:
                with self.assertRaisesRegex(ValueError, "TTL|ttl"):
                    load_config(self.write_config(Path(directory), **changes))

    def test_timeline_element_ttls_accept_conservative_boundaries(self):
        with TemporaryDirectory() as directory:
            config = load_config(self.write_config(
                Path(directory),
                timeline_element_handle_ttl_seconds=30,
                timeline_element_removal_ttl_seconds=1800,
            ))
            self.assertEqual(30, config.timeline_element_handle_ttl_seconds)
            self.assertEqual(1800, config.timeline_element_removal_ttl_seconds)


if __name__ == "__main__":
    unittest.main()
