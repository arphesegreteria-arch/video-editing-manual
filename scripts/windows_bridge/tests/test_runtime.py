from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

from arphe_bridge_runtime import SecretRedactor, load_config  # noqa: E402
from health import check_ready  # noqa: E402
from secret_store import delete_secret, load_secret, store_secret  # noqa: E402


class FakeResponse:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int):
        return self._body


class RuntimeTests(unittest.TestCase):
    def test_redacts_exact_secret_and_common_key_formats(self):
        redact = SecretRedactor("super-secret-value").redact
        text = redact("super-secret-value CONTROL_PLANE_API_KEY=abc Authorization: Bearer xyz sk-1234567890abcdef")
        self.assertNotIn("super-secret-value", text)
        self.assertNotIn("abc", text)
        self.assertNotIn("xyz", text)
        self.assertNotIn("sk-123", text)
        self.assertGreaterEqual(text.count("[REDACTED]"), 4)

    @patch("health.urlopen", return_value=FakeResponse(200, b"ready\n"))
    def test_ready_requires_200_ready(self, _urlopen):
        self.assertTrue(check_ready("http://127.0.0.1:8080/readyz").ready)

    @patch("health.urlopen", return_value=FakeResponse(200, b"starting"))
    def test_ready_rejects_unexpected_body(self, _urlopen):
        self.assertFalse(check_ready("http://127.0.0.1:8080/readyz").ready)

    def test_config_is_locked_to_segreteria(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = root / "tunnel.exe"
            client.write_bytes(b"")
            config = {
                "runtime_id": "ARPHE_WINDOWS_BRIDGE_RUNTIME_V1",
                "workstation_id": "PC_PERSONALE",
                "tunnel_id": "tunnel_test",
                "tunnel_client_path": str(client),
                "mcp_command": "ignored",
                "ready_url": "http://127.0.0.1:8080/readyz",
                "log_dir": str(root / "logs"),
                "secret_path": str(root / "secret"),
                "state_path": str(root / "state"),
                "stop_request_path": str(root / "stop"),
            }
            path = root / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "PC_SEGRETERIA"):
                load_config(path)

    def test_config_accepts_windows_powershell_utf8_bom(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = root / "tunnel.exe"
            client.write_bytes(b"")
            config = {
                "runtime_id": "ARPHE_WINDOWS_BRIDGE_RUNTIME_V1",
                "workstation_id": "PC_SEGRETERIA",
                "tunnel_id": "tunnel_test",
                "tunnel_client_path": str(client),
                "mcp_command": "test bridge",
                "ready_url": "http://127.0.0.1:8080/readyz",
                "log_dir": str(root / "logs"),
                "secret_path": str(root / "secret"),
                "state_path": str(root / "state"),
                "stop_request_path": str(root / "stop"),
            }
            path = root / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8-sig")
            self.assertEqual("PC_SEGRETERIA", load_config(path)["workstation_id"])

    @unittest.skipUnless(os.name == "nt", "DPAPI is Windows-only")
    def test_dpapi_round_trip_uses_ciphertext(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.dpapi"
            secret = "fake-test-runtime-key"
            try:
                store_secret(path, secret)
            except OSError as exc:
                # Some CI/sandbox tokens intentionally have no loaded Windows
                # user profile and therefore cannot access CurrentUser DPAPI.
                self.skipTest(f"CurrentUser DPAPI unavailable in this test token: {exc}")
            self.assertNotIn(secret.encode("utf-8"), path.read_bytes())
            self.assertEqual(secret, load_secret(path))
            self.assertTrue(delete_secret(path))


if __name__ == "__main__":
    unittest.main()
