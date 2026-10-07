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
RUNTIME_INSTALLER = REPO_ROOT / "scripts" / "windows_bridge" / "install_autostart.ps1"
COMMON = REPO_ROOT / "scripts" / "windows_bridge" / "common.ps1"
CREATIVE_INSTALLER = REPO_ROOT / "scripts" / "experiments" / "ARPHE_MCP_BRIDGE_CREATIVE_03" / "install_on_segreteria.ps1"
RUNTIME_SWITCH = REPO_ROOT / "scripts" / "experiments" / "ARPHE_MCP_BRIDGE_CREATIVE_03" / "switch_runtime_bridge.ps1"
BACKUP = REPO_ROOT / "scripts" / "backup" / "backup_arphe.ps1"
SET_FEATURE_FLAG = REPO_ROOT / "scripts" / "experiments" / "ARPHE_MCP_BRIDGE_CREATIVE_03" / "set_feature_flag.ps1"
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
        self.profile_runtime_config_path = (
            self.root / "install" / "runtime-configs" / "PC_PERSONALE" / "bridge_config.json"
        )
        self.legacy_config_path = self.local_app_data / "ARPHE" / "WindowsBridgeRuntimeV1" / "bridge_config.json"
        self.legacy_secret_path = self.legacy_config_path.with_name("runtime_api_key.dpapi")
        self.legacy_creative_config_path = (
            self.local_app_data / "ARPHE" / "CreativeBridge03" / "creative_config.json"
        )
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
            "safe_write_entrypoint": str(self.root / "safe" / "ARPHE_MCP_BRIDGE_SAFE_WRITE_02.py"),
            "requirements_path": str(REPO_ROOT / "scripts" / "experiments" / "ARPHE_MCP_BRIDGE_CREATIVE_03" / "requirements.txt"),
            "venv_root": str(self.root / "venv"),
            "feature_flags": {"CAP_PROJECT": True, "CAP_TIMELINE": True},
        }
        self.safe_write_entrypoint = Path(self.profile["safe_write_entrypoint"])
        self.safe_write_entrypoint.parent.mkdir(parents=True)
        self.safe_write_entrypoint.write_text("# safe-write rollback bridge\n", encoding="utf-8")
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

    def run_creative_dry_run(self, config_path: Path):
        env = os.environ.copy()
        env["LOCALAPPDATA"] = str(self.local_app_data)
        return subprocess.run(
            [
                str(POWERSHELL), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                str(CREATIVE_INSTALLER), "-WorkstationId", "PC_PERSONALE",
                "-Destination", str(self.root / "creative"),
                "-ConfigPath", str(config_path), "-WhatIf",
            ], capture_output=True, text=True, check=False, env=env,
        )

    def write_profile_runtime_config(self, *, create_target=True):
        creative_config = self.profile_runtime_config_path.with_name("creative_config.json")
        creative_state = self.profile_runtime_config_path.with_name("creative_state.json")
        audit_log = self.profile_runtime_config_path.with_name("audit.jsonl")
        creative_config.parent.mkdir(parents=True, exist_ok=True)
        creative_config.write_text(json.dumps({
            "workstation_id": "PC_PERSONALE",
            "state_path": str(creative_state),
            "audit_log_path": str(audit_log),
            "feature_flags": {"CAP_MOTION": False},
        }), encoding="utf-8")
        target = self.root / "creative" / "bridge.py"
        if create_target:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# test bridge\n", encoding="utf-8")
        command = f'"{sys.executable}" "{target}"'
        self.profile_runtime_config_path.write_text(json.dumps({
            "workstation_id": "PC_PERSONALE",
            "creative_config_path": str(creative_config),
            "python_path": sys.executable,
            "bridge_commands": {"Creative03": command},
            "mcp_command": command,
        }), encoding="utf-8")
        return creative_config, command

    def run_switch_dry_run(self):
        env = os.environ.copy()
        env["LOCALAPPDATA"] = str(self.local_app_data)
        return subprocess.run([
            str(POWERSHELL), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(RUNTIME_SWITCH), "-Mode", "Creative03", "-WorkstationId", "PC_PERSONALE", "-WhatIf",
            "-ProfilePath", str(self.profile_path),
        ], capture_output=True, text=True, check=False, env=env)

    def run_backup_preflight(self):
        env = os.environ.copy()
        env["LOCALAPPDATA"] = str(self.local_app_data)
        return subprocess.run([
            str(POWERSHELL), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(BACKUP), "-DestinationRoot", str(self.root), "-WorkstationId", "PC_PERSONALE",
            "-ProfilePath", str(self.profile_path), "-AllowSystemDrive", "-PreflightOnly",
        ], capture_output=True, text=True, check=False, env=env)

    def run_feature_flag_dry_run(self):
        env = os.environ.copy()
        env["LOCALAPPDATA"] = str(self.local_app_data)
        script = str(SET_FEATURE_FLAG).replace("'", "''")
        profile = str(self.profile_path).replace("'", "''")
        command = (
            f"& '{script}' -WorkstationId PC_PERSONALE -ProfilePath '{profile}' "
            "-Name CAP_MOTION -Enabled $true -WhatIf"
        )
        return subprocess.run([
            str(POWERSHELL), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command,
        ], capture_output=True, text=True, check=False, env=env)

    def run_creative_install(self, config_path: Path):
        env = os.environ.copy()
        env["LOCALAPPDATA"] = str(self.local_app_data)
        return subprocess.run([
            str(POWERSHELL), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(CREATIVE_INSTALLER), "-WorkstationId", "PC_PERSONALE",
            "-Destination", str(self.root / "creative-install"),
            "-AssetRoot", str(self.root / "assets"), "-RenderRoot", str(self.root / "renders"),
            "-ConfigPath", str(config_path),
        ], capture_output=True, text=True, check=False, env=env)

    def run_runtime_installer_what_if(self, mcp_command: str):
        env = os.environ.copy()
        env["LOCALAPPDATA"] = str(self.local_app_data)
        return subprocess.run([
            str(POWERSHELL), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(RUNTIME_INSTALLER), "-WorkstationId", "PC_PERSONALE",
            "-TunnelId", "tunnel_personal_test", "-TunnelClientPath", str(self.tunnel_client),
            "-McpCommand", mcp_command, "-PythonPath", sys.executable,
            "-PythonwPath", sys.executable, "-WhatIf",
        ], capture_output=True, text=True, check=False, env=env)

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
    def test_common_resolves_runtime_config_from_explicit_profile(self):
        local_value = str(self.local_app_data).replace("'", "''")
        common_value = str(COMMON).replace("'", "''")
        profile_value = str(self.profile_path).replace("'", "''")
        command = (
            f"$env:LOCALAPPDATA='{local_value}'; "
            f". '{common_value}' -WorkstationId PC_PERSONALE -ProfilePath '{profile_value}'; "
            "Write-Output $script:ArpheConfigPath"
        )
        result = subprocess.run(
            [str(POWERSHELL), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(self.profile_runtime_config_path, Path(result.stdout.strip()))

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
    def test_preflight_rejects_missing_safe_write_rollback_target(self):
        self.safe_write_entrypoint.unlink()
        result = self.run_preflight()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("safe-write rollback entrypoint", result.stderr.lower())
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

    @unittest.skipUnless(os.name == "nt" and POWERSHELL.is_file(), "PowerShell preflight is Windows-only")
    def test_preflight_rejects_foreign_legacy_creative_config_before_writes(self):
        self.legacy_creative_config_path.parent.mkdir(parents=True)
        self.legacy_creative_config_path.write_text(json.dumps({
            "workstation_id": "PC_SEGRETERIA",
            "feature_flags": {},
        }), encoding="utf-8")
        result = self.run_preflight()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("creative", result.stderr.lower())
        self.assertIn("PC_SEGRETERIA", result.stderr)
        self.assertFalse(self.profile_runtime_config_path.parent.exists())
        self.assertFalse(Path(self.profile["venv_root"]).exists())

    @unittest.skipUnless(os.name == "nt" and POWERSHELL.is_file(), "PowerShell test is Windows-only")
    def test_creative_dry_run_reports_explicit_profile_config_path(self):
        config_path = self.root / "install" / "runtime-configs" / "PC_PERSONALE" / "creative_config.json"
        result = self.run_creative_dry_run(config_path)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(str(config_path), result.stdout)

    @unittest.skipUnless(os.name == "nt" and POWERSHELL.is_file(), "PowerShell test is Windows-only")
    def test_switch_uses_profile_command_without_python_alias(self):
        _creative_config, command = self.write_profile_runtime_config()
        result = self.run_switch_dry_run()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(command, result.stdout)
        self.assertNotIn("py -3", result.stdout)

    @unittest.skipUnless(os.name == "nt" and POWERSHELL.is_file(), "PowerShell test is Windows-only")
    def test_switch_rejects_registered_command_with_missing_target(self):
        self.write_profile_runtime_config(create_target=False)
        result = self.run_switch_dry_run()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("target", result.stderr.lower())

    @unittest.skipUnless(os.name == "nt" and POWERSHELL.is_file(), "PowerShell test is Windows-only")
    def test_low_level_installer_rejects_generic_python_alias(self):
        result = self.run_runtime_installer_what_if("py -3 C:/ARPHE/bridge.py")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("absolute", result.stderr.lower())

    @unittest.skipUnless(os.name == "nt" and POWERSHELL.is_file(), "PowerShell test is Windows-only")
    def test_backup_preflight_resolves_profile_runtime_and_creative_config(self):
        creative_config, _command = self.write_profile_runtime_config()
        result = self.run_backup_preflight()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(str(creative_config), result.stdout)
        self.assertIn(str(self.profile_runtime_config_path), result.stdout)
        self.assertNotIn(str(self.local_config_path), result.stdout)

    @unittest.skipUnless(os.name == "nt" and POWERSHELL.is_file(), "PowerShell test is Windows-only")
    def test_feature_flag_uses_profile_creative_config(self):
        creative_config, _command = self.write_profile_runtime_config()
        result = self.run_feature_flag_dry_run()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(str(creative_config), result.stdout)

    @unittest.skipUnless(os.name == "nt" and POWERSHELL.is_file(), "PowerShell test is Windows-only")
    def test_creative_install_keeps_state_and_audit_inside_profile_directory(self):
        config_path = self.root / "install" / "runtime-configs" / "PC_PERSONALE" / "creative_config.json"
        result = self.run_creative_install(config_path)
        self.assertEqual(0, result.returncode, result.stderr)
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(config_path.parent / "creative_state.json", Path(config["state_path"]))
        self.assertEqual(config_path.parent / "audit.jsonl", Path(config["audit_log_path"]))

    @unittest.skipUnless(os.name == "nt" and POWERSHELL.is_file(), "PowerShell test is Windows-only")
    def test_creative_install_copies_workflow_and_render_registries(self):
        config_path = self.root / "install" / "runtime-configs" / "PC_PERSONALE" / "creative_config.json"
        result = self.run_creative_install(config_path)
        self.assertEqual(0, result.returncode, result.stderr)
        destination = self.root / "creative-install"
        for name in ("editorial_workflows.json", "render_profiles.json"):
            self.assertEqual(
                (CREATIVE_INSTALLER.parent / name).read_bytes(),
                (destination / name).read_bytes(),
            )

    @unittest.skipUnless(os.name == "nt" and POWERSHELL.is_file(), "PowerShell test is Windows-only")
    def test_creative_install_migrates_matching_legacy_config_without_deleting_source(self):
        legacy_state = self.legacy_creative_config_path.with_name("creative_state.json")
        legacy_audit = self.legacy_creative_config_path.with_name("audit.jsonl")
        self.legacy_creative_config_path.parent.mkdir(parents=True)
        legacy_state.write_text('{"legacy": true}', encoding="utf-8")
        legacy_audit.write_text('{"event": "legacy"}\n', encoding="utf-8")
        self.legacy_creative_config_path.write_text(json.dumps({
            "workstation_id": "PC_PERSONALE",
            "state_path": str(legacy_state),
            "audit_log_path": str(legacy_audit),
            "feature_flags": {"CAP_MOTION": True},
            "media_roots": [],
        }), encoding="utf-8")
        config_path = self.profile_runtime_config_path.with_name("creative_config.json")
        result = self.run_creative_install(config_path)
        self.assertEqual(0, result.returncode, result.stderr)
        migrated = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertTrue(migrated["feature_flags"]["CAP_MOTION"])
        self.assertEqual('{"legacy": true}', (config_path.parent / "creative_state.json").read_text(encoding="utf-8"))
        self.assertTrue((config_path.parent / "audit.jsonl").is_file())
        self.assertTrue(self.legacy_creative_config_path.is_file())

    @unittest.skipUnless(os.name == "nt" and POWERSHELL.is_file(), "PowerShell test is Windows-only")
    def test_creative_install_rejects_foreign_legacy_config(self):
        self.legacy_creative_config_path.parent.mkdir(parents=True)
        self.legacy_creative_config_path.write_text(json.dumps({
            "workstation_id": "PC_SEGRETERIA",
            "feature_flags": {},
        }), encoding="utf-8")
        config_path = self.profile_runtime_config_path.with_name("creative_config.json")
        result = self.run_creative_install(config_path)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("PC_SEGRETERIA", result.stderr)
        self.assertFalse(config_path.exists())


if __name__ == "__main__":
    unittest.main()
