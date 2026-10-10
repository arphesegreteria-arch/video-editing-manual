from __future__ import annotations
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class BrandedLongformToolsTests(unittest.TestCase):
    def test_complete_tool_surface_is_exposed(self):
        from bridge import server
        from bridge.tool_catalog import EXPOSED_TOOL_NAMES
        expected = {
            "inspect_branded_longform", "create_branded_longform_cleanup",
            "propose_branded_longform_editorial", "approve_branded_longform_batch",
            "apply_branded_longform_batch", "verify_branded_longform_job",
        }
        self.assertTrue(expected.issubset(EXPOSED_TOOL_NAMES))
        self.assertTrue(all(callable(getattr(server, name, None)) for name in expected))
