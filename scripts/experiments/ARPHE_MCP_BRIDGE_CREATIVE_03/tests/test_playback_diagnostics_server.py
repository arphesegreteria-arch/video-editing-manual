from __future__ import annotations

from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge import server  # noqa: E402


class PlaybackDiagnosticServerTests(unittest.TestCase):
    def test_tool_uses_current_workstation_and_resolve_context(self):
        resolve = object()
        project = object()
        timeline = object()
        config = types.SimpleNamespace(workstation_id="PC_SEGRETERIA")
        runtime = (resolve, object(), project, timeline, config, object(), None)
        expected = {
            "ok": True,
            "action": "get_playback_diagnostics",
            "workstation_id": "PC_SEGRETERIA",
            "writes_performed": False,
        }

        with patch.object(server, "_runtime", return_value=runtime), patch.object(
            server, "do_collect_playback_diagnostics", return_value=expected
        ) as collect:
            result = server.get_playback_diagnostics()

        self.assertEqual(expected, result)
        collect.assert_called_once_with(resolve, project, timeline, "PC_SEGRETERIA")

    def test_tool_preserves_workstation_identity_on_connection_error(self):
        config = types.SimpleNamespace(workstation_id="PC_PERSONALE")
        error = {"ok": False, "stage": "connect", "error": "Resolve non raggiungibile"}
        runtime = (None, None, None, None, config, object(), error)

        with patch.object(server, "_runtime", return_value=runtime):
            result = server.get_playback_diagnostics()

        self.assertEqual("PC_PERSONALE", result["workstation_id"])
        self.assertEqual(error["error"], result["error"])


if __name__ == "__main__":
    unittest.main()
