from __future__ import annotations

from pathlib import Path
import sys
import threading
import time
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge import resolve_connection  # noqa: E402
from bridge import server  # noqa: E402


class ResolveConnectionTests(unittest.TestCase):
    def test_context_serializes_native_fusionscript_access(self):
        active = 0
        active_lock = threading.Lock()

        def scriptapp(_name):
            nonlocal active
            with active_lock:
                active += 1
                overlapping = active > 1
            time.sleep(0.05)
            with active_lock:
                active -= 1
            if overlapping:
                raise RuntimeError("concurrent fusionscript access")
            return object()

        fake_module = types.SimpleNamespace(scriptapp=scriptapp)
        start = threading.Barrier(3)
        results = []

        def call_context():
            start.wait()
            results.append(resolve_connection.context())

        with patch.object(resolve_connection, "configure_api", return_value={}), \
             patch.dict(sys.modules, {"DaVinciResolveScript": fake_module}):
            threads = [threading.Thread(target=call_context) for _ in range(2)]
            for thread in threads:
                thread.start()
            start.wait()
            for thread in threads:
                thread.join()

        self.assertEqual(2, len(results))
        self.assertTrue(all(result[4] is None for result in results), results)

    def test_status_and_feature_flags_serialize_complete_resolve_reads(self):
        active = 0
        active_lock = threading.Lock()

        def guarded(value):
            nonlocal active
            with active_lock:
                active += 1
                overlapping = active > 1
            time.sleep(0.05)
            with active_lock:
                active -= 1
            if overlapping:
                raise RuntimeError("concurrent Resolve read")
            return value

        config = types.SimpleNamespace(workstation_id="PC_PERSONALE")
        runtime = (object(), object(), object(), None, config, object(), None)
        start = threading.Barrier(3)
        results = []

        def call(operation):
            start.wait()
            results.append(operation())

        with patch.object(server, "_runtime", return_value=runtime), \
             patch.object(server, "safe_call", side_effect=lambda *_args: guarded("21.0.4.5")), \
             patch.object(server, "feature_report", side_effect=lambda *_args: guarded({"CAP_PROJECT": {"active": True}})):
            threads = [
                threading.Thread(target=call, args=(server.resolve_status,)),
                threading.Thread(target=call, args=(server.get_feature_flags,)),
            ]
            for thread in threads:
                thread.start()
            start.wait()
            for thread in threads:
                thread.join()

        self.assertEqual(2, len(results))
        self.assertTrue(all(result.get("ok") is True for result in results), results)

    def test_read_only_identity_tools_report_the_configured_workstation(self):
        config = types.SimpleNamespace(workstation_id="PC_PERSONALE", flags={})
        runtime = (object(), object(), None, None, config, object(), None)

        with patch.object(server, "load_config", return_value=config), \
             patch.object(server, "_runtime", return_value=runtime), \
             patch.object(server, "safe_call", return_value="21.0.4.5"), \
             patch.object(server, "feature_report", return_value={}):
            results = (server.ping(), server.resolve_status(), server.get_feature_flags())

        self.assertTrue(all(result["workstation_id"] == "PC_PERSONALE" for result in results), results)

    def test_resolve_status_error_still_reports_the_configured_workstation(self):
        config = types.SimpleNamespace(workstation_id="PC_PERSONALE")
        connection_error = {"ok": False, "stage": "connect", "error": "Resolve non raggiungibile"}
        runtime = (None, None, None, None, config, object(), connection_error)

        with patch.object(server, "_runtime", return_value=runtime):
            result = server.resolve_status()

        self.assertEqual("PC_PERSONALE", result["workstation_id"])
        self.assertEqual(connection_error["error"], result["error"])


if __name__ == "__main__":
    unittest.main()
