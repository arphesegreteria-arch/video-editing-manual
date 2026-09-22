from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
INSTALLER = REPO_ROOT / "scripts" / "install_workstation_profile.ps1"
COMMON = REPO_ROOT / "scripts" / "windows_bridge" / "common.ps1"
POWERSHELL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"


class ProfileInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.local_app_data = self.root / "localappdata"
        self.local_config_path = (
            self.local_app_data
            / "ARPHE"
            / "WindowsBridgeRuntimeV1"
            / "PC_PERSONALE"
            / "bridge_config.json"
        )
        self.local_secret_path = self.local_config_path.with_name("runtime_api_key.dpapi")
        self.legacy_config_path = self.local_app_data / "ARPHE" / "WindowsBridgeRuntimeV1" / "bridge_config.json"
        self.legacy_secret_path = self.legacy_config_path.with_name("runtime_api_key.dpapi")
        self.tunnel_client = self.root / "tunnel-client.exe"
        self.tunnel_client.write_bytes(b"test")
        self.profile_path = self.root / "pc_personale.local.json"
        self.profile = {
            "schema_version": 1,
            "workstation_id": "PC_PERSONALE",
            "tunnel_name": "ARPHE-RESOLVE-PERSONALE",
            "tunnel_id": "tunnel_personal_test",
            "python_path": str(Path(sys.executable)),
            "pythonw_path": str(Path(sys.executable)),
            "python_version": platform.python_version(),
            "tunnel_client_path": str(self.tunnel_client),
            "install_root": str(self.root / "install"),
            "log_dir": str(self.root / "logs"),
            "creative_destination": str(self.root / "creative"),
            "mcp_entrypoint": str(self.root / "creative" / "ARPHE_MCP_BRIDGE_CREATIVE_03.py"),
            "requirements_path": str(REPO_ROOT / "scripts" / "experiments" / "ARPHE_MCP_BRIDGE_CREATIVE_03" / "requirements.txt"),
            "venv_root": str(self.root / "venv"),
            "feature_flags": {"CAP_PROJECT": True, "CAP_TIMELINE": True},
        }
        self.profile_path.write_text(json.dumps(self.profile), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def run_preflight(self):
        env = os.environ.copy()
        env["LOCALAPPDATA"] = str(self.local_app_data)
        return subprocess.run(
            [
                str(POWERSHELL),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(INSTALLER),
                "-ProfilePath",
                str(self.profile_path),
                "-PreflightOnly",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

    def run_common(self):
        local_value = str(self.local_app_data).replace("'", "''")
        common_value = str(COMMON).replace("'", "''")
        command = (
            f"$env:LOCALAPPDATA='{local_value}'; "
            f". '{common_value}' -WorkstationId PC_PERSONALE; "
            "Write-Output $script:ArpheDataDir; "
            "Write-Output $script:ArpheConfigPath; "
            "Write-Output $script:ArpheSecretPath"
        )
        return subprocess.run(
            [str(POWERSHELL), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            text=True,
            check=False,
        )

    def run_legacy_secret_migration(self):
        local_value = str(self.local_app_data).replace("'", "''")
        common_value = str(COMMON).replace("'", "''")
        command = (
            f"$env:LOCALAPPDATA='{local_value}'; "
            f". '{common_value}' -WorkstationId PC_PERSONALE; "
            "Copy-ArpheLegacySecretForWorkstation | Out-Null"
        )
        return subprocess.run(
            [str(POWERSHELL), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            text=True,
            check=False,
        )

    @unittest.skipUnless(os.name == "nt" and POWERSHELL.is_file(), "PowerShell test is Windows-only")
    def test_common_uses_workstation_specific_data_directory(self):
        result = self.run_common()
        self.assertEqual(0, result.returncode, result.stderr)
        lines = [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]
        workstation_dir = self.local_app_data / "ARPHE" / "WindowsBridgeRuntimeV1" / "PC_PERSONALE"
        self.assertEqual(
            [
                workstation_dir,
                workstation_dir / "bridge_config.json",
                workstation_dir / "runtime_api_key.dpapi",
            ],
            lines,
        )

    @unittest.skipUnless(os.name == "nt" and POWERSHELL.is_file(), "PowerShell test is Windows-only")
    def test_matching_legacy_secret_migrates_to_workstation_directory(self):
        self.legacy_config_path.parent.mkdir(parents=True)
        self.legacy_config_path.write_text(
            json.dumps({"workstation_id": "PC_PERSONALE", "tunnel_id": "tunnel_old_personal"}),
            encoding="utf-8",
        )
        self.legacy_secret_path.write_bytes(b"encrypted-test-blob")
        result = self.run_legacy_secret_migration()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(b"encrypted-test-blob", self.local_secret_path.read_bytes())

    @unittest.skipUnless(os.name == "nt" and POWERSHELL.is_file(), "PowerShell preflight is Windows-only")
    def test_preflight_prints_identity_without_writing_config(self):
        result = self.run_preflight()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("PC_PERSONALE", result.stdout)
        self.assertIn("ARPHE-RESOLVE-PERSONALE", result.stdout)
        self.assertIn(platform.python_version(), result.stdout)
        self.assertFalse(self.local_config_path.exists())

    @unittest.skipUnless(os.name == "nt" and POWERSHELL.is_file(), "PowerShell preflight is Windows-only")
    def test_preflight_rejects_existing_config_for_other_workstation(self):
        self.local_config_path.parent.mkdir(parents=True)
        self.local_config_path.write_text(
            json.dumps({"workstation_id": "PC_SEGRETERIA", "tunnel_id": "tunnel_office_test"}),
            encoding="utf-8",
        )
        result = self.run_preflight()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("belongs to PC_SEGRETERIA", result.stderr)
        saved = json.loads(self.local_config_path.read_text(encoding="utf-8"))
        self.assertEqual("PC_SEGRETERIA", saved["workstation_id"])


if __name__ == "__main__":
    unittest.main()
