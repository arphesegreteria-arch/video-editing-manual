from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.config import DEFAULT_FLAGS  # noqa: E402
import bridge.server as server  # noqa: E402


class WorkflowControlToolTests(unittest.TestCase):
    def test_snapshot_is_useful_offline_and_performs_no_write(self):
        with tempfile.TemporaryDirectory() as raw:
            cfg = SimpleNamespace(workstation_id="PC_PERSONALE", flags=dict(DEFAULT_FLAGS),
                                  workflow_control_jobs_path=Path(raw) / "jobs.json")
            with patch("bridge.server.load_config", return_value=cfg), \
                 patch("bridge.server._runtime", return_value=(None, None, None, None, cfg, None, {"ok": False, "error": "offline"})):
                card = server.inspect_workstation_control_plane()
            self.assertEqual("PC_PERSONALE", card["workstation_id"])
            self.assertFalse(card["resolve"]["connected"])
            self.assertFalse((Path(raw) / "jobs.json").exists())

    def test_mutation_rejects_disabled_flag_before_runtime(self):
        cfg = SimpleNamespace(workstation_id="PC_PERSONALE", flags=dict(DEFAULT_FLAGS))
        with patch("bridge.server.load_config", return_value=cfg), \
             patch("bridge.server._runtime", side_effect=AssertionError("runtime touched")):
            result = server.prepare_workflow_job("PODCAST_REELS", "editorial_0123456789abcdef", {"project_name": "A", "timeline_name": "T"})
        self.assertFalse(result["ok"])
        self.assertIn("CAP_WORKFLOW_CONTROL_PLANE", result["error"])

    def test_inspect_job_is_read_only_and_approve_is_flag_gated(self):
        cfg = SimpleNamespace(workstation_id="PC_PERSONALE", flags=dict(DEFAULT_FLAGS),
                              workflow_control_jobs_path=Path("unused.json"))
        with patch("bridge.server.load_config", return_value=cfg), \
             patch("bridge.server._runtime", side_effect=AssertionError("runtime touched")):
            approved = server.approve_workflow_job("workflow_0123456789abcdef", "a" * 64, "SECRETARY")
        self.assertFalse(approved["ok"])
        self.assertIn("CAP_WORKFLOW_CONTROL_PLANE", approved["error"])


if __name__ == "__main__":
    unittest.main()
