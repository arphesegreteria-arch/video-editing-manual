from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.config import DEFAULT_FLAGS
from bridge.tool_catalog import EXPOSED_TOOL_NAMES
import bridge.server as server


class VerticalSocialToolTests(unittest.TestCase):
    def config(self, root: Path, enabled=False):
        flags = dict(DEFAULT_FLAGS)
        flags["CAP_VERTICAL_SOCIAL"] = enabled
        return SimpleNamespace(
            flags=flags, workstation_id="PC_PERSONALE",
            vertical_social_plans_path=root / "plans.json",
            audit_log_path=root / "audit.jsonl",
        )

    def test_catalog_exposes_closed_vertical_social_surface(self):
        required = {"inspect_vertical_social", "prepare_vertical_social_plan",
                    "approve_vertical_social_plan", "inspect_vertical_social_plan",
                    "mark_vertical_social_picture_lock", "advance_vertical_social_action"}
        self.assertTrue(required.issubset(EXPOSED_TOOL_NAMES))
        for name in required:
            self.assertTrue(callable(getattr(server, name)))

    def test_inspection_works_off_and_mutation_fails_before_runtime(self):
        with tempfile.TemporaryDirectory() as raw:
            cfg = self.config(Path(raw), False)
            with patch("bridge.server.load_config", return_value=cfg),                  patch("bridge.server._runtime", side_effect=AssertionError("runtime touched")):
                status = server.inspect_vertical_social()
                prepared = server.prepare_vertical_social_plan(
                    {"project": "ARPHE", "timeline": "ADV", "fps": "30"}, [])
        self.assertTrue(status["ok"])
        self.assertFalse(status["capability_enabled"])
        self.assertFalse(prepared["ok"])
        self.assertIn("CAP_VERTICAL_SOCIAL", prepared["error"])


if __name__ == "__main__":
    unittest.main()

